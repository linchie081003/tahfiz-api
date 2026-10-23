import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app import models
from app.database import get_db
from app.deps import require_member_id
from app.services import daily_sessions, tanda

router = APIRouter(tags=["tanda"])


class MarkIn(BaseModel):
    surah_id: int = Field(ge=1, le=114)
    ayah_number: int = Field(ge=1, le=286)
    word_start: int | None = Field(None, ge=0)
    word_end: int | None = Field(None, ge=0)
    reason: str | None = Field(None, max_length=200)


class MarkOut(BaseModel):
    id: uuid.UUID
    surah_id: int
    ayah_number: int
    word_start: int | None
    word_end: int | None
    word_text: str | None
    source: str
    created_by_role: str
    streak: int
    reason: str | None

    model_config = {"from_attributes": True}


class ResultIn(BaseModel):
    surah_id: int = Field(ge=1, le=114)
    ayah_number: int = Field(ge=1, le=286)
    result: str


class PracticeIn(BaseModel):
    kind: str = Field(pattern="^(murajaah|ziyadah|penguatan)$")
    results: list[ResultIn] = Field(min_length=1, max_length=100)


class SambungAnswerIn(BaseModel):
    surah_id: int = Field(ge=1, le=114)
    ayah_from: int = Field(ge=1, le=285)
    mode: str
    result: str | None = None
    chosen_surah_id: int | None = None
    chosen_ayah: int | None = None


@router.get("/tanda", response_model=list[MarkOut])
async def list_marks(surah_id: int | None = None, member_id=Depends(require_member_id), db: AsyncSession = Depends(get_db)):
    return await tanda.active_marks(db, member_id, surah_id)


@router.post("/tanda", response_model=MarkOut, status_code=201)
async def add_mark(payload: MarkIn, member_id=Depends(require_member_id), db: AsyncSession = Depends(get_db)):
    return await tanda.create_mark(
        db, member_id, payload.surah_id, payload.ayah_number,
        word_start=payload.word_start, word_end=payload.word_end, reason=payload.reason,
    )


@router.post("/tanda/{mark_id}/nonaktif")
async def remove_mark(mark_id: uuid.UUID, member_id=Depends(require_member_id), db: AsyncSession = Depends(get_db)):
    await tanda.deactivate_mark(db, member_id, mark_id)
    return {"ok": True}


@router.post("/latihan")
async def practice(payload: PracticeIn, member_id=Depends(require_member_id), db: AsyncSession = Depends(get_db)):
    """Hasil latihan mandiri per ayat. Hanya memengaruhi tanda dan prioritas, tidak kelulusan."""
    triples = [(r.surah_id, r.ayah_number, r.result) for r in payload.results]
    if payload.kind == "penguatan":  # divalidasi terhadap sampel Sesi 3 hari ini; ditolak bila tidak sah
        member = await db.get(models.Member, member_id)
        _, res = await daily_sessions.complete_sesi3(db, member, triples)
        return res
    return await tanda.record_results(db, member_id, payload.kind, triples)


@router.get("/sambung")
async def sambung_questions(member_id=Depends(require_member_id), db: AsyncSession = Depends(get_db)):
    member = await db.get(models.Member, member_id)
    return {"questions": await tanda.build_questions(db, member)}


@router.post("/sambung/jawab")
async def sambung_answer(payload: SambungAnswerIn, member_id=Depends(require_member_id), db: AsyncSession = Depends(get_db)):
    return await tanda.answer_sambung(
        db, member_id, payload.surah_id, payload.ayah_from, payload.mode, payload.result, payload.chosen_surah_id, payload.chosen_ayah,
    )
