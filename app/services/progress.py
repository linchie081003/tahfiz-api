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


async def get_active_surah(db: AsyncSession, member_id: uuid.UUID) -> MemberSurahProgress | None:
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
