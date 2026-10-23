"""Pengingat murojaah harian via Web Push (anak + orang tua).

Aturan: pada jam `reminder_hour` (zona waktu keluarga) kirim satu pengingat per anak per hari,
hanya bila ada murojaah jatuh tempo. Idempoten lewat ReminderLog.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.surah_translit import surah_name
from app import models
from app.config import settings

logger = logging.getLogger(__name__)

# sender(subscription_info, payload) -> True terkirim | False gagal sementara | "gone" langganan tidak berlaku
Sender = Callable[[dict, dict], Awaitable[object]]


def endpoint_hash(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode()).hexdigest()


def reminder_message(name: str, surah_names: list[str], total: int) -> dict:
    shown = ", ".join(surah_names[:3]) + ("…" if total > 3 else "")
    return {
        "title": f"Waktunya murojaah, {name}!",
        "body": f"{total} surat menunggu: {shown}",
        "url": "/murojaah",
        "tag": "murojaah-harian",
    }


async def webpush_sender(sub: dict, payload: dict) -> object:
    """Pengirim bawaan (pywebpush). Dijalankan di thread karena sinkron."""
    if not settings.vapid_private_key:
        return False
    from pywebpush import WebPushException, webpush

    def _send():
        try:
            webpush(
                subscription_info=sub,
                data=json.dumps(payload, ensure_ascii=False),
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": settings.vapid_claims_email},
                ttl=6 * 3600,
            )
            return True
        except WebPushException as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            return "gone" if status in (404, 410) else False
        except Exception:
            return False

    return await asyncio.to_thread(_send)


async def _due_surah_names(db: AsyncSession, member_id, local_day) -> list[str]:
    rows = (
        await db.execute(
            select(models.Surah.id, models.Surah.name_id)
            .join(models.MurojaahItem, models.MurojaahItem.surah_id == models.Surah.id)
            .where(
                models.MurojaahItem.member_id == member_id,
                models.MurojaahItem.completed.is_(False),
                models.MurojaahItem.due_date <= local_day,
            )
            .order_by(models.MurojaahItem.weak_score.desc(), models.MurojaahItem.due_date)
        )
    ).all()
    names: list[str] = []
    for r in rows:
        n = surah_name(r[0], r[1])
        if n not in names:
            names.append(n)
    return names


async def run_reminders(db: AsyncSession, now: datetime | None = None, sender: Sender = webpush_sender) -> dict:
    now = now or datetime.now(timezone.utc)
    tz = ZoneInfo(settings.reminder_timezone)
    local = now.astimezone(tz)
    stats = {"members_notified": 0, "sent": 0, "removed": 0}

    fams = (await db.execute(select(models.FamilySettings).where(models.FamilySettings.reminder_hour == local.hour))).scalars().all()
    for fs in fams:
        members = (await db.execute(select(models.Member).where(models.Member.family_id == fs.family_id))).scalars().all()
        parent_subs = (
            await db.execute(
                select(models.PushSubscription)
                .join(models.ParentUser, models.ParentUser.id == models.PushSubscription.parent_user_id)
                .where(models.ParentUser.family_id == fs.family_id)
            )
        ).scalars().all()
        for m in members:
            done = (
                await db.execute(
                    select(models.ReminderLog.id).where(models.ReminderLog.member_id == m.id, models.ReminderLog.day == local.date())
                )
            ).first()
            if done:
                continue
            names = await _due_surah_names(db, m.id, local.date())
            if not names:
                continue
            msg = reminder_message(m.name, names, len(names))
            member_subs = (
                await db.execute(select(models.MemberPushSubscription).where(models.MemberPushSubscription.member_id == m.id))
            ).scalars().all()
            gone: list = []
            for sub in [*member_subs, *parent_subs]:
                info = {"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}}
                res = await sender(info, msg)
                if res is True:
                    stats["sent"] += 1
                elif res == "gone":
                    gone.append(sub)
            for sub in gone:
                await db.delete(sub)
                stats["removed"] += 1
            db.add(models.ReminderLog(member_id=m.id, day=local.date()))
            await db.flush()
            stats["members_notified"] += 1
    return stats
