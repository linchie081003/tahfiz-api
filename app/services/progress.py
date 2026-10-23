import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Member, MemberSettings, MemberSurahProgress, Surah, SurahProgressStatus, TahsinStatus


async def init_member_progress(db: AsyncSession, member_id: uuid.UUID):
    surahs = (
        await db.execute(select(Surah).where(Surah.juz_number == 30).order_by(Surah.curriculum_order))
    ).scalars().all()
    for i, surah in enumerate(surahs):
        status = SurahProgressStatus.in_progress if i == 0 else SurahProgressStatus.locked
        db.add(MemberSurahProgress(member_id=member_id, surah_id=surah.id, status=status, current_ayah=1))


async def can_access_ziyadah(member: Member) -> bool:
    return member.tahsin_status == TahsinStatus.passed


async def hafalan_unlocked(db: AsyncSession, member: Member) -> bool:
    """Hafalan dan murajaah terbuka jika 3 Pulau wajib tahsin lulus, atau jika diatur paralel (orang tua atau guru)."""
    if member.tahsin_status == TahsinStatus.passed:
        return True
    ms = (await db.execute(select(MemberSettings).where(MemberSettings.member_id == member.id))).scalar_one_or_none()
    return bool(ms and ms.parallel_hafalan)


async def effective_track(db: AsyncSession, member_id: uuid.UUID) -> str:
    ms = (await db.execute(select(MemberSettings).where(MemberSettings.member_id == member_id))).scalar_one_or_none()
    return "mushaf" if ms and ms.coverage == "all" and ms.hafalan_track == "mushaf" else "juz30"


async def track_surahs(db: AsyncSession, track: str, *, local: bool = False) -> list[Surah]:
    """Urutan surat jalur hafalan: juz30 = kurikulum Amma; mushaf = Al-Fatihah sampai An-Nas (nomor surat)."""
    from app.services.juz30 import list_juz30_surahs
    from app.services.quran_com_import import ensure_chapter_catalog

    if local:  # tanpa memuat katalog dari luar (dipakai di tengah transaksi penilaian)
        q = select(Surah).where(Surah.juz_number == 30).order_by(Surah.curriculum_order, Surah.id) if track != "mushaf" else select(Surah).order_by(Surah.id)
        return list((await db.execute(q)).scalars().all())
    if track != "mushaf":
        return await list_juz30_surahs(db)
    await ensure_chapter_catalog(db)
    return list((await db.execute(select(Surah).order_by(Surah.id))).scalars().all())


async def set_track(db: AsyncSession, member_id: uuid.UUID, track: str) -> None:
    """Pindah jalur hafalan: surat yang sudah lulus tetap, surat aktif pindah ke yang pertama belum lulus di jalur baru."""
    surahs = await track_surahs(db, track, local=True)
    rows = {r.surah_id: r for r in (await db.execute(select(MemberSurahProgress).where(MemberSurahProgress.member_id == member_id))).scalars().all()}
    first_open = None
    for s_ in surahs:
        r = rows.get(s_.id)
        if r is None:
            r = MemberSurahProgress(member_id=member_id, surah_id=s_.id, status=SurahProgressStatus.locked, current_ayah=1)
            db.add(r)
            rows[s_.id] = r
        if r.status != SurahProgressStatus.passed and first_open is None:
            first_open = s_.id
    in_track = {s_.id for s_ in surahs}
    for sid, r in rows.items():
        if r.status == SurahProgressStatus.passed:
            continue
        r.status = SurahProgressStatus.in_progress if sid == first_open and sid in in_track else SurahProgressStatus.locked
    await db.flush()


SHORT_SURAH_MAX = 10  # surat sependek ini disetor sekaligus utuh


def plan_range(ayah_count: int, current_ayah: int, daily_ayahs: int) -> tuple[int, int, str]:
    """Rentang setoran berikutnya. Surat pendek: seluruh sisa ayat sekaligus. Surat panjang: sebanyak target harian."""
    start = min(max(current_ayah, 1), max(ayah_count, 1))
    if ayah_count <= SHORT_SURAH_MAX:
        return start, ayah_count, "seluruh_surat"
    return start, min(start + max(daily_ayahs, 1) - 1, ayah_count), "target_harian"


async def get_settings(db: AsyncSession, member_id: uuid.UUID) -> MemberSettings | None:
    return (await db.execute(select(MemberSettings).where(MemberSettings.member_id == member_id))).scalar_one_or_none()


async def setor_plan(db: AsyncSession, member_id: uuid.UUID) -> dict | None:
    active = await get_active_surah(db, member_id)
    if not active:
        return None
    surah = await db.get(Surah, active.surah_id)
    if not surah:
        return None
    ms = await get_settings(db, member_id)
    start, end, mode = plan_range(surah.ayah_count, active.current_ayah, ms.daily_ayahs if ms else 1)
    return {"surah_id": surah.id, "name_id": surah.name_id, "ayah_count": surah.ayah_count, "ayah_start": start,
            "ayah_end": end, "mode": mode, "done_ayahs": max(start - 1, 0)}


async def choose_surah(db: AsyncSession, member_id: uuid.UUID, surah_id: int) -> None:
    """Mode bebas: pilih surat yang dihafal sekarang (boleh loncat). Mode berurutan menolak."""
    from fastapi import HTTPException

    ms = await get_settings(db, member_id)
    if not ms or ms.hafalan_order != "free":
        raise HTTPException(409, "Urutan hafalan diatur berurutan. Minta orang tua atau guru membuka mode bebas.")
    surahs = await track_surahs(db, await effective_track(db, member_id), local=True)
    if surah_id not in {s_.id for s_ in surahs}:
        raise HTTPException(404, "Surat tidak ada di jalur hafalan")
    row = (await db.execute(select(MemberSurahProgress).where(MemberSurahProgress.member_id == member_id, MemberSurahProgress.surah_id == surah_id))).scalar_one_or_none()
    if row is None:
        row = MemberSurahProgress(member_id=member_id, surah_id=surah_id, status=SurahProgressStatus.in_progress, current_ayah=1)
        db.add(row)
    elif row.status == SurahProgressStatus.passed:
        raise HTTPException(409, "Surat ini sudah hafal. Ulangi lewat murajaah.")
    elif row.status == SurahProgressStatus.locked:
        row.status = SurahProgressStatus.in_progress
    ms.focus_surah_id = surah_id
    await db.flush()


async def get_active_surah(db: AsyncSession, member_id: uuid.UUID) -> MemberSurahProgress | None:
    ms = await get_settings(db, member_id)
    if ms and ms.hafalan_order == "free" and ms.focus_surah_id:
        focus = (await db.execute(select(MemberSurahProgress).where(
            MemberSurahProgress.member_id == member_id, MemberSurahProgress.surah_id == ms.focus_surah_id,
            MemberSurahProgress.status.in_([SurahProgressStatus.in_progress, SurahProgressStatus.needs_retry])))).scalar_one_or_none()
        if focus:
            return focus
    q = (
        select(MemberSurahProgress)
        .where(
            MemberSurahProgress.member_id == member_id,
            MemberSurahProgress.status.in_([SurahProgressStatus.in_progress, SurahProgressStatus.needs_retry]),
        )
        .order_by(MemberSurahProgress.id)
        .limit(1)
    )
    return (await db.execute(q)).scalar_one_or_none()


async def unlock_next_surah(db: AsyncSession, member_id: uuid.UUID, current_surah_id: int):
    ms = await get_settings(db, member_id)
    if ms and ms.hafalan_order == "free":
        if ms.focus_surah_id == current_surah_id:
            ms.focus_surah_id = None  # surat selesai; anak memilih surat berikutnya sendiri
        return
    surahs = await track_surahs(db, await effective_track(db, member_id), local=True)
    ids = [x.id for x in surahs]
    if current_surah_id not in ids or ids.index(current_surah_id) + 1 >= len(ids):
        return
    next_surah = surahs[ids.index(current_surah_id) + 1]
    prog = await db.execute(
        select(MemberSurahProgress).where(
            MemberSurahProgress.member_id == member_id, MemberSurahProgress.surah_id == next_surah.id
        )
    )
    row = prog.scalar_one_or_none()
    if row and row.status == SurahProgressStatus.locked:
        row.status = SurahProgressStatus.in_progress
