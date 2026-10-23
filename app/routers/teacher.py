"""API guru: daftar, masuk, dokumen, murid, antrean, penilaian, pesan."""
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, ratelimit, schemas, security
from app.config import settings
from app.database import get_db
from app.deps import require_teacher
from app.routers.member_progress import DAILY_AYAHS, STRONG_DAYS, MemberSettingsIn, MemberSettingsOut, PlacementIn, get_member_settings
from app.services import corrections, setor_flow, storage, tahsin_points, teaching, verification

router = APIRouter(prefix="/teacher", tags=["teacher"])
NIL = uuid.UUID(int=0)


class TeacherRegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8)
    institution_code: str | None = None


class TeacherLoginIn(BaseModel):
    email: EmailStr
    password: str


class TeacherTokenOut(BaseModel):
    access_token: str
    role: str = "teacher"
    status: str
    kind: str


class TeacherOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    kind: str
    status: str
    invite_code: str
    grading_target_hours: int
    is_admin: bool
    institution_name: str | None = None


class DocIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    note: str | None = None


class RespondIn(BaseModel):
    accept: bool
    reason: str | None = None


class PointIn(BaseModel):
    score: float = Field(ge=0, le=10)
    approve_below_threshold: bool = False


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=1000)


class TargetIn(BaseModel):
    grading_target_hours: Literal[24, 48, 72]


def _token(t: models.Teacher) -> str:
    return security.create_token(
        subject=t.id, family_id=NIL, role="teacher", member_id=None,
        expires_minutes=settings.parent_token_expire_minutes, pwv=security.password_fingerprint(t.hashed_password),
    )


async def _out(db: AsyncSession, t: models.Teacher) -> TeacherOut:
    inst = await db.get(models.Institution, t.institution_id) if t.institution_id else None
    return TeacherOut(id=t.id, name=t.name, email=t.email, kind=t.kind, status=t.status, invite_code=t.invite_code,
                      grading_target_hours=t.grading_target_hours, is_admin=t.is_admin,
                      institution_name=inst.name if inst else None)


@router.post("/register", response_model=TeacherTokenOut, status_code=status.HTTP_201_CREATED)
async def register(request: Request, payload: TeacherRegisterIn, db: AsyncSession = Depends(get_db)):
    ratelimit.check_ip(request, "teacher-register", 10, 3600)
    if (await db.execute(select(models.Teacher).where(models.Teacher.email == payload.email))).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email sudah terdaftar")
    inst = None
    if payload.institution_code:
        inst = (
            await db.execute(select(models.Institution).where(models.Institution.invite_code == payload.institution_code))
        ).scalar_one_or_none()
        if not inst:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Kode instansi tidak ditemukan")
    t = models.Teacher(
        email=payload.email, hashed_password=security.hash_secret(payload.password), name=payload.name,
        kind="institution" if inst else "independent",
        status="verified" if inst else "pending",  # guru instansi diverifikasi instansi lewat kode
        institution_id=inst.id if inst else None, invite_code=teaching.new_code(),
    )
    db.add(t)
    await db.flush()
    return TeacherTokenOut(access_token=_token(t), status=t.status, kind=t.kind)


@router.post("/login", response_model=TeacherTokenOut)
async def login(request: Request, payload: TeacherLoginIn, db: AsyncSession = Depends(get_db)):
    ratelimit.check_ip(request, "teacher-login", 20, 600)
    t = (await db.execute(select(models.Teacher).where(models.Teacher.email == payload.email))).scalar_one_or_none()
    if not t or not security.verify_secret(payload.password, t.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email atau kata sandi salah")
    return TeacherTokenOut(access_token=_token(t), status=t.status, kind=t.kind)


@router.get("/me", response_model=TeacherOut)
async def me(t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    return await _out(db, t)


@router.put("/me/target", response_model=TeacherOut)
async def set_target(payload: TargetIn, t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    t.grading_target_hours = payload.grading_target_hours
    await db.flush()
    return await _out(db, t)


@router.get("/documents")
async def list_documents(t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(models.TeacherDocument).where(models.TeacherDocument.teacher_id == t.id))).scalars().all()
    return [{"id": d.id, "title": d.title, "note": d.note} for d in rows]


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def add_document(payload: DocIn, t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    d = models.TeacherDocument(teacher_id=t.id, title=payload.title, note=payload.note)
    db.add(d)
    await db.flush()
    return {"id": d.id, "title": d.title, "note": d.note}


async def _links(db: AsyncSession, t: models.Teacher, status_: str):
    return (
        await db.execute(
            select(models.TeacherLink).where(models.TeacherLink.teacher_id == t.id, models.TeacherLink.status == status_)
        )
    ).scalars().all()


@router.get("/requests")
async def requests(t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    out = []
    for l in await _links(db, t, "requested"):
        m = await db.get(models.Member, l.member_id)
        fam = await db.get(models.Family, l.family_id)
        out.append({"link_id": l.id, "member_id": l.member_id, "member_name": m.name if m else "", "family_name": fam.name if fam else ""})
    return out


@router.post("/requests/{link_id}/respond")
async def respond(link_id: uuid.UUID, payload: RespondIn, t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    link = await db.get(models.TeacherLink, link_id)
    if not link or link.teacher_id != t.id or link.status != "requested":
        raise HTTPException(404, "Permintaan tidak ditemukan")
    if payload.accept:
        if t.status != "verified":
            raise HTTPException(409, "Akun guru belum diverifikasi")
        if await teaching.active_link(db, link.member_id):
            raise HTTPException(409, "Anak ini sudah punya guru aktif")
        link.status = "active"
    else:
        link.status = "rejected"
        link.reject_reason = payload.reason
    await db.flush()
    return {"status": link.status}


async def _student_link(db: AsyncSession, t: models.Teacher, member_id: uuid.UUID) -> models.TeacherLink:
    link = await teaching.active_link(db, member_id)
    if not link or link.teacher_id != t.id:
        raise HTTPException(404, "Murid tidak ditemukan")
    return link


@router.get("/students")
async def students(t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    out = []
    for l in await _links(db, t, "active"):
        m = await db.get(models.Member, l.member_id)
        pending = (
            await db.execute(
                select(models.Submission).where(
                    models.Submission.member_id == l.member_id, models.Submission.status == models.SubmissionStatus.pending_eval
                )
            )
        ).scalars().all()
        out.append({
            "member_id": l.member_id, "name": m.name if m else "", "tahsin_status": m.tahsin_status.value if m else "",
            "recording_consent": l.recording_consent, "pending": len(pending),
            "overdue": sum(1 for s in pending if teaching.is_overdue(s, t)),
        })
    return out


@router.get("/queue")
async def queue(t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    member_ids = [l.member_id for l in await _links(db, t, "active")]
    if not member_ids:
        return []
    subs = (
        await db.execute(
            select(models.Submission)
            .where(models.Submission.member_id.in_(member_ids), models.Submission.status == models.SubmissionStatus.pending_eval)
            .order_by(models.Submission.created_at)
        )
    ).scalars().all()
    out = []
    for s in subs:
        m = await db.get(models.Member, s.member_id)
        link = await teaching.active_link(db, s.member_id)
        can_hear = bool(link and link.recording_consent and s.recording_deleted_at is None)
        out.append({
            "id": s.id, "context": s.context.value, "tahsin_point": s.tahsin_point, "member_id": s.member_id, "member_name": m.name if m else "",
            "reference_text": s.reference_text, "ai_insights": s.ai_insights, "created_at": s.created_at,
            "due_at": teaching.due_at(s, t), "overdue": teaching.is_overdue(s, t), "can_hear": can_hear,
        })
    return out


@router.get("/media/{submission_id}")
async def media(submission_id: uuid.UUID, t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    sub = await db.get(models.Submission, submission_id)
    if not sub or not await teaching.teacher_can_hear(db, t.id, sub.member_id):
        raise HTTPException(403, "Rekaman terkunci: izin dengar belum aktif")
    if sub.recording_deleted_at is not None:
        raise HTTPException(404, "Rekaman sudah dihapus")
    path = storage.local_recording_path(sub.family_id, sub.id)
    if not path.is_file():
        raise HTTPException(404, "File rekaman tidak ada")
    db.add(models.RecordingAccessLog(submission_id=sub.id, teacher_id=t.id, family_id=sub.family_id, member_id=sub.member_id))
    await db.flush()
    return FileResponse(path, media_type="audio/webm")


@router.post("/submissions/{submission_id}/evaluate")
async def evaluate(submission_id: uuid.UUID, payload: schemas.EvaluateSubmissionIn,
                   t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    sub = (
        await db.execute(select(models.Submission).where(models.Submission.id == submission_id).with_for_update())
    ).scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Setoran tidak ditemukan")
    await _student_link(db, t, sub.member_id)
    member = await db.get(models.Member, sub.member_id)
    if sub.status == models.SubmissionStatus.superseded:
        raise HTTPException(409, "Setoran ini sudah digantikan setoran yang lebih baru")
    if sub.status != models.SubmissionStatus.pending_eval:
        return {"status": sub.status.value}
    if await teaching.takeover_for(db, sub.id):
        raise HTTPException(409, "Setoran ini diambil alih orang tua")
    await setor_flow.apply_submission_evaluation(db, sub, member, payload, evaluator_id=t.id, evaluator_role="teacher")
    if payload.evaluator_notes:
        db.add(models.TeacherMessage(teacher_id=t.id, family_id=sub.family_id, member_id=sub.member_id,
                                     direction="to_parent", kind="note", body=payload.evaluator_notes))
    await db.flush()
    return {"status": sub.status.value}


@router.get("/submissions/{submission_id}/riwayat-penilaian")
async def evaluation_history(submission_id: uuid.UUID, t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    sub = await db.get(models.Submission, submission_id)
    if not sub:
        raise HTTPException(404, "Setoran tidak ditemukan")
    await _student_link(db, t, sub.member_id)
    evals = await corrections.history(db, sub.id)
    active = corrections.active_ids(evals)
    return [
        {"id": e.id, "result": e.result, "evaluator_role": e.evaluator_role, "notes": e.notes, "created_at": e.created_at,
         "corrects_id": e.corrects_id, "correction_reason": e.correction_reason, "active": e.id in active,
         "ayah_start": e.ayah_start, "ayah_end": e.ayah_end}
        for e in evals
    ]


@router.post("/submissions/{submission_id}/koreksi")
async def correct_evaluation(submission_id: uuid.UUID, payload: schemas.CorrectionIn, t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    """Koreksi oleh guru yang terhubung. Menambah riwayat; penilaian lama tidak ditimpa."""
    sub = (await db.execute(select(models.Submission).where(models.Submission.id == submission_id).with_for_update())).scalar_one_or_none()
    if not sub:
        raise HTTPException(404, "Setoran tidak ditemukan")
    await _student_link(db, t, sub.member_id)
    if await teaching.takeover_for(db, sub.id):
        raise HTTPException(409, "Setoran ini diambil alih orang tua")
    member = await db.get(models.Member, sub.member_id)
    ev = await corrections.correct(
        db, sub, member, evaluator_id=t.id, evaluator_role="teacher", status=payload.status,
        notes=payload.evaluator_notes, rubric_scores=payload.rubric_scores, reason=payload.reason,
        ayah_start=payload.ayah_start, ayah_end=payload.ayah_end,
    )
    return {"id": ev.id, "status": sub.status.value}


class VerifyIn(BaseModel):
    decision: str = Field(pattern="^(lulus|tolak)$")
    note: str = Field(min_length=1, max_length=500)


@router.get("/students/{member_id}/verifikasi")
async def student_verification(member_id: uuid.UUID, t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    """Hafalan lama murid tanpa bukti penilaian lulus, menunggu keputusan guru."""
    await _student_link(db, t, member_id)
    member = await db.get(models.Member, member_id)
    return await verification.as_dicts(db, member)


@router.post("/verifikasi/{range_id}")
async def verify_range(range_id: uuid.UUID, payload: VerifyIn, t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    rng = await db.get(models.MemorizedRange, range_id)
    if not rng:
        raise HTTPException(404, "Rentang tidak ditemukan")
    await _student_link(db, t, rng.member_id)
    r = await verification.resolve(db, rng, decision=payload.decision, note=payload.note, by=t.id, role="teacher")
    return {"id": r.id, "status": r.status}


@router.post("/students/{member_id}/points/{point}/result")
async def point_result(member_id: uuid.UUID, point: int, payload: PointIn,
                       t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    if point < 1 or point > 9:
        raise HTTPException(404, "Pulau tidak ditemukan")
    await _student_link(db, t, member_id)
    member = await db.get(models.Member, member_id)
    await tahsin_points.record_result(db, member, point, payload.score, "teacher", t.id, payload.approve_below_threshold)
    return await tahsin_points.overview(db, member_id)


@router.get("/students/{member_id}/points")
async def student_points(member_id: uuid.UUID, t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    await _student_link(db, t, member_id)
    return await tahsin_points.overview(db, member_id)


@router.get("/students/{member_id}/settings", response_model=MemberSettingsOut)
async def student_settings(member_id: uuid.UUID, t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    await _student_link(db, t, member_id)
    row = await get_member_settings(db, member_id)
    return MemberSettingsOut(coverage=row.coverage, daily_ayahs=row.daily_ayahs, murajaah_strong_days=row.murajaah_strong_days,
                             set_by=row.set_by, parallel_hafalan=bool(row.parallel_hafalan), hafalan_track=row.hafalan_track or "juz30", hafalan_order=row.hafalan_order or "sequential") if row else MemberSettingsOut()


@router.put("/students/{member_id}/settings", response_model=MemberSettingsOut)
async def set_student_settings(member_id: uuid.UUID, payload: MemberSettingsIn,
                               t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    await _student_link(db, t, member_id)
    if payload.daily_ayahs is not None and payload.daily_ayahs not in DAILY_AYAHS:
        raise HTTPException(422, "Kecepatan harus 1, 2, 3, atau 5 ayat per hari")
    if payload.murajaah_strong_days is not None and payload.murajaah_strong_days not in STRONG_DAYS:
        raise HTTPException(422, "Interval 'Kuat' harus 7 atau 14 hari")
    if payload.coverage == "all" or payload.hafalan_track == "mushaf":
        from app.services.quran_com_import import ensure_chapter_catalog

        await ensure_chapter_catalog(db)
    row = await get_member_settings(db, member_id)
    if not row:
        row = models.MemberSettings(member_id=member_id, coverage="juz30", daily_ayahs=1, murajaah_strong_days=14)
        db.add(row)
    for f in ("coverage", "daily_ayahs", "murajaah_strong_days", "parallel_hafalan", "hafalan_track", "hafalan_order"):
        v = getattr(payload, f)
        if v is not None:
            setattr(row, f, v)
    row.set_by = "teacher"
    await db.flush()
    if payload.hafalan_order == "sequential":
        row.focus_surah_id = None
    if payload.coverage is not None or payload.hafalan_track is not None or payload.hafalan_order == "sequential":
        from app.services import progress as _progress
        await _progress.set_track(db, member_id, await _progress.effective_track(db, member_id))
        await db.refresh(row)
    return MemberSettingsOut(coverage=row.coverage, daily_ayahs=row.daily_ayahs, murajaah_strong_days=row.murajaah_strong_days, set_by="teacher", parallel_hafalan=bool(row.parallel_hafalan), hafalan_track=row.hafalan_track or "juz30", hafalan_order=row.hafalan_order or "sequential")


@router.get("/students/{member_id}/placement")
async def student_placement(member_id: uuid.UUID, t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    await _student_link(db, t, member_id)
    row = await get_member_settings(db, member_id)
    return {"placement": row.placement if row else None}


@router.put("/students/{member_id}/placement")
async def set_student_placement(member_id: uuid.UUID, payload: PlacementIn, t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    await _student_link(db, t, member_id)
    row = await get_member_settings(db, member_id)
    if not row:
        row = models.MemberSettings(member_id=member_id, coverage="juz30", daily_ayahs=1, murajaah_strong_days=14)
        db.add(row)
    row.placement = payload.level
    row.set_by = "teacher"
    await db.flush()
    return {"placement": row.placement}


@router.post("/students/{member_id}/messages", status_code=status.HTTP_201_CREATED)
async def send_message(member_id: uuid.UUID, payload: MessageIn, t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    link = await _student_link(db, t, member_id)
    db.add(models.TeacherMessage(teacher_id=t.id, family_id=link.family_id, member_id=member_id,
                                 direction="to_parent", kind="note", body=payload.body))
    await db.flush()
    return {"ok": True}


@router.get("/inbox")
async def inbox(t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(models.TeacherMessage)
            .where(models.TeacherMessage.teacher_id == t.id, models.TeacherMessage.direction == "to_teacher")
            .order_by(models.TeacherMessage.created_at.desc())
        )
    ).scalars().all()
    return [{"id": r.id, "member_id": r.member_id, "kind": r.kind, "body": r.body, "created_at": r.created_at} for r in rows]
