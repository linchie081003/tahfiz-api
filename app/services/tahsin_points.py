"""Sembilan Pulau tahsin, ambang lulus, dan gerbang hafalan baru."""
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.models import TahsinStatus

PASS_THRESHOLD = 8.0  # dari 10; pemutus boleh meluluskan di bawahnya
MANDATORY = (1, 2, 3)

POINTS = [
    {"point": 1, "name": "Makharijul huruf", "mandatory": True},
    {"point": 2, "name": "Sifat huruf dasar", "mandatory": True},
    {"point": 3, "name": "Harakat dan mad", "mandatory": True},
    {"point": 4, "name": "Huruf yang mirip", "mandatory": False},
    {"point": 5, "name": "Nun sukun dan tanwin", "mandatory": False},
    {"point": 6, "name": "Mim sukun", "mandatory": False},
    {"point": 7, "name": "Mad panjang", "mandatory": False},
    {"point": 8, "name": "Lam dan ra'", "mandatory": False},
    {"point": 9, "name": "Waqaf dan ibtida'", "mandatory": False},
]


async def _rows(db: AsyncSession, member_id: uuid.UUID) -> dict[int, models.TahsinPointProgress]:
    rows = (
        await db.execute(select(models.TahsinPointProgress).where(models.TahsinPointProgress.member_id == member_id))
    ).scalars().all()
    return {r.point: r for r in rows}


def gate_open(rows: dict[int, models.TahsinPointProgress]) -> bool:
    return all(rows.get(p) is not None and rows[p].passed for p in MANDATORY)


async def overview(db: AsyncSession, member_id: uuid.UUID) -> dict:
    rows = await _rows(db, member_id)
    items = []
    for p in POINTS:
        r = rows.get(p["point"])
        items.append(
            {
                **p,
                "passed": bool(r and r.passed),
                "best_score": r.best_score if r else 0.0,
                "approved_below_threshold": bool(r and r.approved_below_threshold),
                "decided_by": r.decided_by if r else None,
            }
        )
    return {
        "points": items,
        "gate_open": gate_open(rows),
        "all_passed": all(i["passed"] for i in items),
        "threshold": PASS_THRESHOLD,
    }


async def record_result(
    db: AsyncSession,
    member: models.Member,
    point: int,
    score: float,
    decider_role: str,
    decider_id: uuid.UUID,
    approve_below: bool = False,
) -> models.TahsinPointProgress:
    """Skor dari pra-cek/penilai; kelulusan diputuskan manusia (guru atau orang tua)."""
    rows = await _rows(db, member.id)
    if point in MANDATORY and point > 1 and not (rows.get(point - 1) and rows[point - 1].passed):
        raise HTTPException(409, f"Pulau {point - 1} harus lulus dulu sebelum Pulau {point}")
    row = rows.get(point)
    if row is None:
        row = models.TahsinPointProgress(member_id=member.id, point=point, best_score=0.0, passed=False)
        db.add(row)
        rows[point] = row
    row.best_score = max(row.best_score or 0.0, score)
    if not row.passed and (score >= PASS_THRESHOLD or approve_below):
        row.passed = True
        row.approved_below_threshold = score < PASS_THRESHOLD
        row.decided_by = decider_role
        row.decider_id = decider_id
        row.passed_at = datetime.now(timezone.utc)
    await db.flush()
    if gate_open(rows) and member.tahsin_status != TahsinStatus.passed:
        member.tahsin_status = TahsinStatus.passed  # kompatibel dengan alur lama
    return row
