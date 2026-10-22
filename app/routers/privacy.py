"""Sisi keluarga: persetujuan rekaman, hubungan dengan guru, izin dengar, log akses, hapus, unduh, pesan, pindah instansi."""
import io
import json
import uuid
import zipfile
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models, ratelimit, security
from app.config import settings
from app.database import get_db
from app.deps import AuthContext, require_parent, require_teacher
from app.routers.family import require_owner
from app.services import storage, tahsin_points, teaching

router = APIRouter(prefix="/family", tags=["privacy"])
inst_router = APIRouter(prefix="/institution", tags=["institution"])


class ConnectIn(BaseModel):
    code: str
    member_id: uuid.UUID


class GrantIn(BaseModel):
    granted: bool


class ReviewIn(BaseModel):
    approve: bool


class DecideIn(BaseModel):
    approve: bool
    teacher_id: uuid.UUID | None = None


class DeleteIn(BaseModel):
    member_id: uuid.UUID | None = None
    pin: str | None = None


class PinIn(BaseModel):
    pin: str = Field(pattern=r"^\d{4}$")
    current_pin: str | None = None


class ReplyIn(BaseModel):
    member_id: uuid.UUID
    body: str = Field(min_length=1, max_length=1000)


class ExportIn(BaseModel):
    member_id: uuid.UUID


class TransferIn(BaseModel):
    institution_code: str


async def _member(db: AsyncSession, member_id: uuid.UUID, family_id: uuid.UUID) -> models.Member:
    m = await db.get(models.Member, member_id)
    if not m or m.family_id != family_id:
        raise HTTPException(404, "Anak tidak ditemukan")
    return m


async def _link(db: AsyncSession, link_id: uuid.UUID, family_id: uuid.UUID) -> models.TeacherLink:
    l = await db.get(models.TeacherLink, link_id)
    if not l or l.family_id != family_id:
        raise HTTPException(404, "Tautan guru tidak ditemukan")
    return l


# ---- persetujuan perekaman (terpisah dari syarat layanan)
@router.get("/consent/recording")
async def consent_status(ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    fam = await db.get(models.Family, ctx.family_id)
    return {"granted": fam.recording_consent_at is not None, "at": fam.recording_consent_at,
            "retention_days": settings.recording_retention_days}


@router.post("/consent/recording")
async def set_consent(payload: GrantIn, ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    fam = await db.get(models.Family, ctx.family_id)
    fam.recording_consent_at = datetime.now(timezone.utc) if payload.granted else None
    fam.recording_consent_by = ctx.subject_id if payload.granted else None
    await db.flush()
    return {"granted": payload.granted}


# ---- hubungkan guru
@router.post("/teachers/connect", status_code=status.HTTP_201_CREATED)
async def connect_teacher(payload: ConnectIn, ctx: AuthContext = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    await _member(db, payload.member_id, ctx.family_id)
    teacher = (await db.execute(select(models.Teacher).where(models.Teacher.invite_code == payload.code))).scalar_one_or_none()
    if not teacher or teacher.status == "rejected":
        raise HTTPException(404, "Kode guru tidak ditemukan")
    if await teaching.active_link(db, payload.member_id):
        raise HTTPException(409, "Anak ini sudah punya guru aktif. Cabut dulu untuk mengganti.")
    dup = (
        await db.execute(select(models.TeacherLink).where(
            models.TeacherLink.member_id == payload.member_id, models.TeacherLink.teacher_id == teacher.id,
            models.TeacherLink.status == "requested"))
    ).scalars().first()
    if dup:
        raise HTTPException(409, "Permintaan sudah dikirim")
    link = models.TeacherLink(teacher_id=teacher.id, family_id=ctx.family_id, member_id=payload.member_id,
                              requested_by=ctx.subject_id)
    db.add(link)
    await db.flush()
    return {"link_id": link.id, "needs_review": teacher.kind == "independent" and teacher.status == "pending"}


async def _teacher_summary(db: AsyncSession, t: models.Teacher, with_docs: bool) -> dict:
    out = {"id": t.id, "name": t.name, "kind": t.kind, "status": t.status}
    if with_docs:
        docs = (await db.execute(select(models.TeacherDocument).where(models.TeacherDocument.teacher_id == t.id))).scalars().all()
        out["documents"] = [{"id": d.id, "title": d.title, "note": d.note} for d in docs]
    return out


@router.get("/teachers/review")
async def review_queue(ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    """Guru mandiri yang menunggu tinjauan: orang tua melihat dokumen dasar (platform tidak memeriksa)."""
    links = (
        await db.execute(select(models.TeacherLink).where(models.TeacherLink.family_id == ctx.family_id,
                                                          models.TeacherLink.status == "requested"))
    ).scalars().all()
    out = []
    for l in links:
        t = await db.get(models.Teacher, l.teacher_id)
        if t and t.kind == "independent" and t.status == "pending":
            m = await db.get(models.Member, l.member_id)
            out.append({"link_id": l.id, "member_name": m.name if m else "", "teacher": await _teacher_summary(db, t, True)})
    return out


@router.post("/links/{link_id}/review")
async def review_teacher(link_id: uuid.UUID, payload: ReviewIn, ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    """Ayah atau Ibu boleh menyetujui/menolak guru mandiri yang diundang keluarga."""
    link = await _link(db, link_id, ctx.family_id)
    t = await db.get(models.Teacher, link.teacher_id)
    if t.kind != "independent":
        raise HTTPException(409, "Guru instansi diverifikasi oleh instansi")
    if t.status != "pending":
        raise HTTPException(409, "Guru ini sudah ditinjau")
    if payload.approve:
        t.status = "verified"
    else:
        t.status = "rejected"
        link.status = "rejected"
        link.reject_reason = "Ditolak orang tua saat tinjauan"
    await db.flush()
    return {"teacher_status": t.status, "link_status": link.status}


@router.get("/members/{member_id}/teacher")
async def member_teacher(member_id: uuid.UUID, ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    await _member(db, member_id, ctx.family_id)
    link = (
        await db.execute(select(models.TeacherLink).where(models.TeacherLink.member_id == member_id,
                         models.TeacherLink.status.in_(["active", "requested", "rejected"]))
                         .order_by(models.TeacherLink.created_at.desc()))
    ).scalars().first()
    if not link:
        return {"link": None}
    t = await db.get(models.Teacher, link.teacher_id)
    overdue = 0
    if link.status == "active":
        subs = (await db.execute(select(models.Submission).where(
            models.Submission.member_id == member_id, models.Submission.status == models.SubmissionStatus.pending_eval))).scalars().all()
        overdue = sum(1 for s in subs if teaching.is_overdue(s, t))
    return {"link": {"id": link.id, "status": link.status, "recording_consent": link.recording_consent,
                     "reject_reason": link.reject_reason, "teacher": await _teacher_summary(db, t, False),
                     "grading_target_hours": t.grading_target_hours, "overdue": overdue}}


@router.post("/links/{link_id}/consent")
async def link_consent(link_id: uuid.UUID, payload: GrantIn, ctx: AuthContext = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    link = await _link(db, link_id, ctx.family_id)
    if link.status != "active":
        raise HTTPException(409, "Guru belum aktif")
    fam = await db.get(models.Family, ctx.family_id)
    if payload.granted and fam.recording_consent_at is None:
        raise HTTPException(409, "Setujui perekaman suara anak dulu")
    link.recording_consent = payload.granted
    link.consent_at = datetime.now(timezone.utc) if payload.granted else None
    await db.flush()
    return {"recording_consent": link.recording_consent}


@router.post("/links/{link_id}/revoke")
async def revoke_link(link_id: uuid.UUID, ctx: AuthContext = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    """Mengganti guru: guru lama kehilangan akses rekaman; riwayat belajar tetap pada anak."""
    link = await _link(db, link_id, ctx.family_id)
    if link.status not in ("active", "requested"):
        raise HTTPException(409, "Tautan tidak aktif")
    link.status = "revoked"
    link.recording_consent = False
    await db.flush()
    return {"status": link.status}


@router.get("/access-log")
async def access_log(ctx: AuthContext = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(models.RecordingAccessLog).where(models.RecordingAccessLog.family_id == ctx.family_id)
                             .order_by(models.RecordingAccessLog.at.desc()).limit(200))).scalars().all()
    out = []
    for r in rows:
        t = await db.get(models.Teacher, r.teacher_id)
        m = await db.get(models.Member, r.member_id)
        out.append({"id": r.id, "teacher": t.name if t else "", "member": m.name if m else "", "at": r.at, "submission_id": r.submission_id})
    return out


# ---- hapus dan unduh
@router.get("/pin")
async def pin_status(ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    p = await db.get(models.ParentUser, ctx.subject_id)
    return {"has_pin": bool(p and p.settings_pin_hash)}


@router.put("/pin")
async def set_pin(payload: PinIn, ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    """PIN orang tua (4 angka) melindungi tindakan penghapusan. Mengganti PIN perlu PIN lama."""
    p = await db.get(models.ParentUser, ctx.subject_id)
    if p.settings_pin_hash and not (payload.current_pin and security.verify_secret(payload.current_pin, p.settings_pin_hash)):
        raise HTTPException(403, "PIN lama salah")
    p.settings_pin_hash = security.hash_secret(payload.pin)
    await db.flush()
    return {"has_pin": True}


async def _check_pin(db: AsyncSession, ctx: AuthContext, pin: str | None) -> None:
    ratelimit.check("pin", str(ctx.subject_id), 8, 600)
    p = await db.get(models.ParentUser, ctx.subject_id)
    if not p or not p.settings_pin_hash:
        raise HTTPException(409, "Buat PIN orang tua dulu")
    if not pin or not security.verify_secret(pin, p.settings_pin_hash):
        raise HTTPException(403, "PIN salah")


@router.get("/privacy-summary")
async def privacy_summary(member_id: uuid.UUID, ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    await _member(db, member_id, ctx.family_id)
    subs = (await db.execute(select(models.Submission).where(models.Submission.member_id == member_id,
            models.Submission.recording_deleted_at.is_(None)))).scalars().all()
    size, oldest = 0, None
    now = datetime.now(timezone.utc)
    kept = 0
    for s in subs:
        p = storage.local_recording_path(s.family_id, s.id)
        if p.is_file():
            kept += 1
            size += p.stat().st_size
            created = s.created_at if s.created_at.tzinfo else s.created_at.replace(tzinfo=timezone.utc)
            oldest = max(oldest or 0, (now - created).days)
    fam = await db.get(models.Family, ctx.family_id)
    link = await teaching.active_link(db, member_id)
    teacher = await db.get(models.Teacher, link.teacher_id) if link else None
    return {"recordings": kept, "size_mb": round(size / 1_048_576, 1), "oldest_days": oldest or 0,
            "retention_days": settings.recording_retention_days, "consent": fam.recording_consent_at is not None,
            "teacher": {"link_id": link.id, "name": teacher.name, "recording_consent": link.recording_consent} if link and teacher else None}


@router.post("/messages/reply", status_code=status.HTTP_201_CREATED)
async def reply_message(payload: ReplyIn, ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    await _member(db, payload.member_id, ctx.family_id)
    link = await teaching.active_link(db, payload.member_id)
    if not link:
        raise HTTPException(409, "Belum ada guru aktif")
    db.add(models.TeacherMessage(teacher_id=link.teacher_id, family_id=ctx.family_id, member_id=payload.member_id,
                                 direction="to_teacher", kind="note", body=payload.body))
    await db.flush()
    return {"ok": True}


@router.post("/recordings/delete")
async def delete_recordings(payload: DeleteIn, ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    await _check_pin(db, ctx, payload.pin)
    if payload.member_id:
        await _member(db, payload.member_id, ctx.family_id)
    req = await teaching.delete_recordings(db, ctx.family_id, ctx.subject_id, payload.member_id)
    return {"deleted": req.recording_count, "purge_due_at": req.purge_due_at,
            "message": "Hilang dari aplikasi sekarang; dihapus permanen dari penyimpanan dan cadangan dalam 7 hari."}


@router.get("/recordings/deletions")
async def deletions(ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(models.DeletionRequest).where(models.DeletionRequest.family_id == ctx.family_id)
                             .order_by(models.DeletionRequest.requested_at.desc()))).scalars().all()
    return [{"id": r.id, "member_id": r.member_id, "requested_at": r.requested_at, "purge_due_at": r.purge_due_at,
             "status": r.status, "recording_count": r.recording_count} for r in rows]


def _export_token(family_id: uuid.UUID, member_id: uuid.UUID) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=teaching.EXPORT_HOURS)
    return jwt.encode({"kind": "export", "family_id": str(family_id), "member_id": str(member_id), "exp": exp},
                      settings.jwt_secret, algorithm=settings.jwt_algorithm)


@router.post("/export")
async def create_export(payload: ExportIn, ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    await _member(db, payload.member_id, ctx.family_id)
    return {"token": _export_token(ctx.family_id, payload.member_id), "valid_hours": teaching.EXPORT_HOURS}


@router.get("/export/download")
async def download_export(request: Request, token: str, db: AsyncSession = Depends(get_db)):
    ratelimit.check_ip(request, "export", 20, 3600)
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        assert data.get("kind") == "export"
        family_id, member_id = uuid.UUID(data["family_id"]), uuid.UUID(data["member_id"])
    except (JWTError, AssertionError, KeyError, ValueError):
        raise HTTPException(410, "Tautan unduhan tidak valid atau sudah kedaluwarsa")
    member = await _member(db, member_id, family_id)
    subs = (await db.execute(select(models.Submission).where(models.Submission.member_id == member_id))).scalars().all()
    overview = await tahsin_points.overview(db, member_id)
    notes = (await db.execute(select(models.TeacherMessage).where(models.TeacherMessage.member_id == member_id,
             models.TeacherMessage.direction == "to_parent"))).scalars().all()
    meta = {
        "anak": member.name, "status_tahsin": member.tahsin_status.value, "pulau": overview["points"],
        "setoran": [{"id": str(s.id), "jenis": s.context.value, "status": s.status.value, "tanggal": s.created_at.isoformat(),
                     "nilai": s.rubric_scores, "catatan": s.evaluator_notes, "rekaman": s.recording_deleted_at is None}
                    for s in subs],
        "catatan_guru": [{"tanggal": n.created_at.isoformat(), "isi": n.body} for n in notes],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("data.json", json.dumps(meta, ensure_ascii=False, indent=2))
        for s in subs:
            if s.recording_deleted_at is None:
                p = storage.local_recording_path(s.family_id, s.id)
                if p.is_file():
                    z.write(p, f"rekaman/{s.id}.webm")
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="hafiz-{member.name}.zip"'})


# ---- pesan guru
@router.get("/messages")
async def messages(ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(models.TeacherMessage).where(models.TeacherMessage.family_id == ctx.family_id,
            models.TeacherMessage.direction == "to_parent").order_by(models.TeacherMessage.created_at.desc()))).scalars().all()
    out = []
    for r in rows:
        t = await db.get(models.Teacher, r.teacher_id)
        m = await db.get(models.Member, r.member_id) if r.member_id else None
        out.append({"id": r.id, "teacher": t.name if t else "", "member": m.name if m else "", "body": r.body,
                    "created_at": r.created_at, "read": r.read_at is not None})
    return {"messages": out, "unread": sum(1 for o in out if not o["read"])}


@router.post("/messages/read")
async def mark_read(ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(models.TeacherMessage).where(models.TeacherMessage.family_id == ctx.family_id,
            models.TeacherMessage.direction == "to_parent", models.TeacherMessage.read_at.is_(None)))).scalars().all()
    now = datetime.now(timezone.utc)
    for r in rows:
        r.read_at = now
    return {"marked": len(rows)}


@router.post("/members/{member_id}/remind-teacher")
async def remind_teacher(member_id: uuid.UUID, ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    await _member(db, member_id, ctx.family_id)
    link = await teaching.active_link(db, member_id)
    if not link:
        raise HTTPException(409, "Belum ada guru aktif")
    db.add(models.TeacherMessage(teacher_id=link.teacher_id, family_id=ctx.family_id, member_id=member_id,
                                 direction="to_teacher", kind="reminder", body="Orang tua mengingatkan: ada setoran menunggu dinilai."))
    await db.flush()
    return {"ok": True}


# ---- pindah instansi
@router.post("/transfer", status_code=status.HTTP_201_CREATED)
async def request_transfer(payload: TransferIn, ctx: AuthContext = Depends(require_owner), db: AsyncSession = Depends(get_db)):
    inst = (await db.execute(select(models.Institution).where(models.Institution.invite_code == payload.institution_code))).scalar_one_or_none()
    if not inst:
        raise HTTPException(404, "Kode instansi tidak ditemukan")
    pending = (await db.execute(select(models.TransferRequest).where(models.TransferRequest.family_id == ctx.family_id,
               models.TransferRequest.status == "pending"))).scalars().first()
    if pending:
        raise HTTPException(409, "Sudah ada permintaan pindah yang menunggu")
    req = models.TransferRequest(family_id=ctx.family_id, institution_id=inst.id, requested_by=ctx.subject_id)
    db.add(req)
    await db.flush()
    return {"id": req.id, "institution": inst.name, "status": req.status,
            "shared": ["Kemajuan tahsin dan hafalan", "Skor dan catatan penilaian", "Rekaman hanya bila izin guru instansi diberikan"]}


@router.get("/transfer")
async def transfer_status(ctx: AuthContext = Depends(require_parent), db: AsyncSession = Depends(get_db)):
    req = (await db.execute(select(models.TransferRequest).where(models.TransferRequest.family_id == ctx.family_id)
                            .order_by(models.TransferRequest.created_at.desc()))).scalars().first()
    if not req:
        return {"request": None}
    inst = await db.get(models.Institution, req.institution_id)
    return {"request": {"id": req.id, "institution": inst.name if inst else "", "status": req.status}}


# ---- instansi (admin)
class InstitutionIn(BaseModel):
    name: str


@inst_router.post("", status_code=status.HTTP_201_CREATED)
async def create_institution(payload: InstitutionIn, t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    if t.institution_id:
        raise HTTPException(409, "Sudah tergabung di instansi")
    inst = models.Institution(name=payload.name, invite_code=teaching.new_code())
    db.add(inst)
    await db.flush()
    t.institution_id, t.is_admin, t.kind, t.status = inst.id, True, "institution", "verified"
    await db.flush()
    return {"id": inst.id, "name": inst.name, "invite_code": inst.invite_code}


def _require_admin(t: models.Teacher) -> None:
    if not (t.is_admin and t.institution_id):
        raise HTTPException(403, "Hanya admin instansi")


@inst_router.get("/transfers")
async def list_transfers(t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    _require_admin(t)
    rows = (await db.execute(select(models.TransferRequest).where(models.TransferRequest.institution_id == t.institution_id,
            models.TransferRequest.status == "pending"))).scalars().all()
    out = []
    for r in rows:
        fam = await db.get(models.Family, r.family_id)
        kids = (await db.execute(select(models.Member).where(models.Member.family_id == r.family_id))).scalars().all()
        out.append({"id": r.id, "family": fam.name if fam else "", "created_at": r.created_at, "children": len(kids),
                    "has_teacher": any([await teaching.active_link(db, k.id) for k in kids])})
    return out


@inst_router.post("/transfers/{req_id}/decide")
async def decide_transfer(req_id: uuid.UUID, payload: DecideIn, t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    _require_admin(t)
    req = await db.get(models.TransferRequest, req_id)
    if not req or req.institution_id != t.institution_id or req.status != "pending":
        raise HTTPException(404, "Permintaan tidak ditemukan")
    req.status = "approved" if payload.approve else "rejected"
    req.decided_at = datetime.now(timezone.utc)
    if payload.approve:
        fam = await db.get(models.Family, req.family_id)
        fam.institution_id = req.institution_id
        links = (await db.execute(select(models.TeacherLink).where(models.TeacherLink.family_id == req.family_id,
                 models.TeacherLink.status == "active"))).scalars().all()
        for l in links:  # guru lama tidak lagi melihat data anak
            l.status, l.recording_consent = "revoked", False
        if payload.teacher_id:
            teacher = await db.get(models.Teacher, payload.teacher_id)
            if not teacher or teacher.institution_id != t.institution_id or teacher.status != "verified":
                raise HTTPException(422, "Guru tidak valid untuk instansi ini")
            members = (await db.execute(select(models.Member).where(models.Member.family_id == req.family_id))).scalars().all()
            for m in members:
                db.add(models.TeacherLink(teacher_id=teacher.id, family_id=req.family_id, member_id=m.id,
                                          requested_by=t.id, status="active"))
    await db.flush()
    return {"status": req.status}


async def _student_count(db: AsyncSession, teacher_id: uuid.UUID) -> int:
    return len((await db.execute(select(models.TeacherLink).where(models.TeacherLink.teacher_id == teacher_id,
                models.TeacherLink.status == "active"))).scalars().all())


@inst_router.get("/teachers")
async def institution_teachers(t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    _require_admin(t)
    rows = (await db.execute(select(models.Teacher).where(models.Teacher.institution_id == t.institution_id)
                             .order_by(models.Teacher.created_at))).scalars().all()
    return [{"id": r.id, "name": r.name, "status": r.status, "is_admin": r.is_admin, "created_at": r.created_at,
             "students": await _student_count(db, r.id)} for r in rows]


@inst_router.post("/teachers/{teacher_id}/verify")
async def verify_institution_teacher(teacher_id: uuid.UUID, payload: ReviewIn, t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    _require_admin(t)
    target = await db.get(models.Teacher, teacher_id)
    if not target or target.institution_id != t.institution_id or target.is_admin:
        raise HTTPException(404, "Guru tidak ditemukan")
    target.status = "verified" if payload.approve else "rejected"
    await db.flush()
    return {"status": target.status}


@inst_router.get("/families")
async def institution_families(t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    _require_admin(t)
    fams = (await db.execute(select(models.Family).where(models.Family.institution_id == t.institution_id))).scalars().all()
    out = []
    for f in fams:
        kids = (await db.execute(select(models.Member).where(models.Member.family_id == f.id))).scalars().all()
        out.append({"id": f.id, "name": f.name, "children": len(kids)})
    return out


@inst_router.get("/summary")
async def institution_summary(t: models.Teacher = Depends(require_teacher), db: AsyncSession = Depends(get_db)):
    """Ringkasan dan status saja. Admin tidak mendengar rekaman dan tidak melihat isi belajar anak."""
    _require_admin(t)
    inst = await db.get(models.Institution, t.institution_id)
    teachers = (await db.execute(select(models.Teacher).where(models.Teacher.institution_id == t.institution_id))).scalars().all()
    students = 0
    for x in teachers:
        students += await _student_count(db, x.id)
    fams = (await db.execute(select(models.Family).where(models.Family.institution_id == t.institution_id))).scalars().all()
    transfers = (await db.execute(select(models.TransferRequest).where(models.TransferRequest.institution_id == t.institution_id,
                 models.TransferRequest.status == "pending"))).scalars().all()
    return {"name": inst.name, "invite_code": inst.invite_code, "teachers": len([x for x in teachers if x.status == "verified"]),
            "students": students, "families": len(fams), "pending_teachers": len([x for x in teachers if x.status == "pending"]),
            "pending_transfers": len(transfers)}
