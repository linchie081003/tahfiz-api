"""Laporan mingguan orang tua: ringkasan 7 hari terakhir per anak."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.surah_translit import surah_name
from app import models
from app.models import SubmissionContext, SubmissionStatus, SurahProgressStatus

DAY_LABELS = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]


def _as_date(dt: datetime) -> date:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date()


def _note(active_days: int, ayat: int, overdue: int, empty_days: list[str]) -> str:
    if ayat == 0:
        return "Belum ada hafalan baru minggu ini. Mulai dengan satu ayat saja."
    parts = [f"Aktif {active_days} hari, {ayat} ayat baru."]
    if empty_days and active_days < 7:
        parts.append("Hari kosong: " + ", ".join(empty_days[:3]) + ". Coba jadwalkan setor di waktu yang sama tiap hari.")
    if overdue:
        parts.append(f"{overdue} murojaah menunggu diulang.")
    return " ".join(parts)


async def build_weekly_report(db: AsyncSession, family_id: uuid.UUID, member: models.Member, today: date) -> dict:
    start = today - timedelta(days=6)
    days = [start + timedelta(days=i) for i in range(7)]
    subs = (
        await db.execute(
            select(models.Submission).where(
                models.Submission.member_id == member.id,
                models.Submission.family_id == family_id,
                models.Submission.context == SubmissionContext.ziyadah,
                models.Submission.status == SubmissionStatus.passed,
                models.Submission.evaluated_at.is_not(None),
            )
        )
    ).scalars().all()

    per_day = {d: 0 for d in days}
    surah_ids: set[int] = set()
    for s in subs:
        d = _as_date(s.evaluated_at)
        if d not in per_day:
            continue
        end = s.ayah_end if s.ayah_end is not None else s.ayah_start
        if s.ayah_start is not None and end is not None and end >= s.ayah_start:
            per_day[d] += end - s.ayah_start + 1
        if s.surah_id:
            surah_ids.add(s.surah_id)

    finished = 0
    if surah_ids:
        rows = (
            await db.execute(
                select(models.MemberSurahProgress.surah_id).where(
                    models.MemberSurahProgress.member_id == member.id,
                    models.MemberSurahProgress.surah_id.in_(surah_ids),
                    models.MemberSurahProgress.status == SurahProgressStatus.passed,
                )
            )
        ).all()
        finished = len(rows)

    overdue_rows = (
        await db.execute(
            select(models.Surah.id, models.Surah.name_id)
            .join(models.MurojaahItem, models.MurojaahItem.surah_id == models.Surah.id)
            .join(models.MemberSurahProgress, (models.MemberSurahProgress.member_id == models.MurojaahItem.member_id) & (models.MemberSurahProgress.surah_id == models.MurojaahItem.surah_id))
            .where(
                models.MurojaahItem.member_id == member.id,
                models.MurojaahItem.completed.is_(False),
                models.MemberSurahProgress.status == models.SurahProgressStatus.passed,
                models.MurojaahItem.due_date <= today,
            )
            .order_by(models.MurojaahItem.due_date)
        )
    ).all()
    overdue_names = [surah_name(r[0], r[1]) for r in overdue_rows]

    ayat_total = sum(per_day.values())
    active_days = sum(1 for v in per_day.values() if v > 0)
    empty = [DAY_LABELS[d.weekday()] for d in days if per_day[d] == 0]
    return {
        "member_id": member.id,
        "member_name": member.name,
        "week_start": start,
        "week_end": today,
        "ayat_total": ayat_total,
        "active_days": active_days,
        "surahs_finished": finished,
        "daily": [{"date": d, "label": DAY_LABELS[d.weekday()], "ayat": per_day[d]} for d in days],
        "overdue_murojaah_count": len(overdue_names),
        "overdue_murojaah_surahs": overdue_names[:5],
        "note": _note(active_days, ayat_total, len(overdue_names), empty),
    }
