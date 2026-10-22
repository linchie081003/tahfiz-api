import enum
import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AgeMode(str, enum.Enum):
    paud = "paud"
    sd = "sd"
    teen = "teen"
    adult = "adult"


class EvaluatorType(str, enum.Enum):
    parent = "parent"
    teacher = "teacher"


class TahsinStatus(str, enum.Enum):
    not_started = "not_started"
    pending_eval = "pending_eval"
    failed = "failed"
    passed = "passed"


class SurahProgressStatus(str, enum.Enum):
    locked = "locked"
    in_progress = "in_progress"
    passed = "passed"
    needs_retry = "needs_retry"


class SubmissionContext(str, enum.Enum):
    tahsin = "tahsin"
    ziyadah = "ziyadah"
    ujian = "ujian"


class SubmissionStatus(str, enum.Enum):
    pending_ai = "pending_ai"
    pending_eval = "pending_eval"
    passed = "passed"
    needs_retry = "needs_retry"
    not_fluent = "not_fluent"


class Family(Base):
    __tablename__ = "families"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    access_code: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Persetujuan perekaman suara anak (terpisah dari syarat layanan). Kosong = belum setuju.
    recording_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recording_consent_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    institution_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)  # kosong = mandiri

    parents: Mapped[list["ParentUser"]] = relationship(back_populates="family")
    members: Mapped[list["Member"]] = relationship(back_populates="family")
    settings: Mapped["FamilySettings"] = relationship(back_populates="family", uselist=False)


class ParentUser(Base):
    __tablename__ = "parent_users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(120))
    settings_pin_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # "owner" = pendaftar pertama keluarga; "parent" = orang tua kedua (diundang).
    family_role: Mapped[str] = mapped_column(String(16), default="owner", server_default="owner")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    family: Mapped["Family"] = relationship(back_populates="parents")


class Member(Base):
    __tablename__ = "members"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    age_mode: Mapped[AgeMode] = mapped_column(Enum(AgeMode, native_enum=False), default=AgeMode.sd)
    pin_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    color: Mapped[str] = mapped_column(String(16), default="#4CAF50")
    tahsin_status: Mapped[TahsinStatus] = mapped_column(Enum(TahsinStatus, native_enum=False), default=TahsinStatus.not_started)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    family: Mapped["Family"] = relationship(back_populates="members")
    stats: Mapped["MemberStats"] = relationship(back_populates="member", uselist=False)


class FamilySettings(Base):
    __tablename__ = "family_settings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id"), unique=True)
    evaluator_type: Mapped[EvaluatorType] = mapped_column(Enum(EvaluatorType, native_enum=False), default=EvaluatorType.parent)
    daily_ziyadah_ayahs: Mapped[int] = mapped_column(Integer, default=3)
    daily_murojaah_cap: Mapped[int] = mapped_column(Integer, default=5)
    reminder_hour: Mapped[int] = mapped_column(Integer, default=17)
    celebrations_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    leaderboard_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    reciter_id: Mapped[str] = mapped_column(String(64), default="husary_muallim")
    playback_speed: Mapped[float] = mapped_column(Float, default=1.0)
    arabic_font_size: Mapped[str] = mapped_column(String(16), default="large")
    show_tajweed_colors: Mapped[bool] = mapped_column(Boolean, default=True)

    family: Mapped["Family"] = relationship(back_populates="settings")


class MissionType(Base):
    __tablename__ = "mission_types"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(120))


class Mission(Base):
    __tablename__ = "missions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("members.id"), index=True)
    mission_type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("mission_types.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Surah(Base):
    __tablename__ = "surahs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name_ar: Mapped[str] = mapped_column(String(64))
    name_id: Mapped[str] = mapped_column(String(64))
    ayah_count: Mapped[int] = mapped_column(Integer)
    juz_number: Mapped[int] = mapped_column(Integer, index=True)
    curriculum_order: Mapped[int] = mapped_column(Integer, index=True)


class Ayah(Base):
    __tablename__ = "ayahs"
    __table_args__ = (UniqueConstraint("surah_id", "ayah_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    surah_id: Mapped[int] = mapped_column(ForeignKey("surahs.id"), index=True)
    ayah_number: Mapped[int] = mapped_column(Integer)
    text_uthmani: Mapped[str] = mapped_column(Text)
    text_tajweed: Mapped[str | None] = mapped_column(Text, nullable=True)
    tajwid_markup: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    audio_url: Mapped[str | None] = mapped_column(String(512), nullable=True)


class MemberSurahProgress(Base):
    __tablename__ = "member_surah_progress"
    __table_args__ = (UniqueConstraint("member_id", "surah_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("members.id"), index=True)
    surah_id: Mapped[int] = mapped_column(ForeignKey("surahs.id"))
    status: Mapped[SurahProgressStatus] = mapped_column(Enum(SurahProgressStatus, native_enum=False), default=SurahProgressStatus.locked)
    current_ayah: Mapped[int] = mapped_column(Integer, default=1)


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("members.id"), index=True)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id"), index=True)
    context: Mapped[SubmissionContext] = mapped_column(Enum(SubmissionContext, native_enum=False))
    surah_id: Mapped[int | None] = mapped_column(ForeignKey("surahs.id"), nullable=True)
    ayah_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ayah_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reference_text: Mapped[str] = mapped_column(Text)
    recording_key: Mapped[str] = mapped_column(String(512))
    recording_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[SubmissionStatus] = mapped_column(Enum(SubmissionStatus, native_enum=False), default=SubmissionStatus.pending_ai)
    ai_status: Mapped[str] = mapped_column(String(32), default="pending")
    ai_insights: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evaluator_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rubric_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TahsinAttempt(Base):
    __tablename__ = "tahsin_attempts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("members.id"), index=True)
    submission_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("submissions.id"), nullable=True)
    result: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MurojaahItem(Base):
    __tablename__ = "murojaah_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("members.id"), index=True)
    surah_id: Mapped[int] = mapped_column(ForeignKey("surahs.id"))
    due_date: Mapped[date] = mapped_column(Date, index=True)
    ease_factor: Mapped[float] = mapped_column(default=2.5)
    interval_days: Mapped[int] = mapped_column(Integer, default=1)
    weak_score: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)


class MemberStats(Base):
    __tablename__ = "member_stats"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("members.id"), unique=True)
    xp: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[int] = mapped_column(Integer, default=1)
    rank_title: Mapped[str] = mapped_column(String(64), default="Santri Pemula")
    streak_days: Mapped[int] = mapped_column(Integer, default=0)
    last_active_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    streak_freeze_remaining: Mapped[int] = mapped_column(Integer, default=1)
    mutiara: Mapped[int] = mapped_column(Integer, default=0)

    member: Mapped["Member"] = relationship(back_populates="stats")


class XpConfig(Base):
    __tablename__ = "xp_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    activity_key: Mapped[str] = mapped_column(String(64), unique=True)
    xp_value: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(120))


class BadgeDefinition(Base):
    __tablename__ = "badge_definitions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    requirement_key: Mapped[str] = mapped_column(String(64))


class MemberBadge(Base):
    __tablename__ = "member_badges"
    __table_args__ = (UniqueConstraint("member_id", "badge_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("members.id"), index=True)
    badge_id: Mapped[str] = mapped_column(ForeignKey("badge_definitions.id"))
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    parent_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("parent_users.id"), index=True)
    endpoint: Mapped[str] = mapped_column(Text)
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(255))


class FamilyAiConsent(Base):
    """Persetujuan orang tua agar rekaman suara anak dikirim ke layanan transkripsi pihak ketiga."""

    __tablename__ = "family_ai_consents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id"), unique=True)
    granted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("parent_users.id"))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MemberPushSubscription(Base):
    """Langganan Web Push perangkat anak (orang tua tetap memakai PushSubscription)."""

    __tablename__ = "member_push_subscriptions"
    __table_args__ = (UniqueConstraint("endpoint_hash"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("members.id"), index=True)
    endpoint_hash: Mapped[str] = mapped_column(String(64))
    endpoint: Mapped[str] = mapped_column(Text)
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(255))


class ReminderLog(Base):
    """Satu pengingat per anak per hari (idempoten)."""

    __tablename__ = "reminder_logs"
    __table_args__ = (UniqueConstraint("member_id", "day"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("members.id"), index=True)
    day: Mapped[date] = mapped_column(Date)


class FamilyInvite(Base):
    """Undangan orang tua kedua. Hanya pemilik keluarga yang boleh membuatnya."""

    __tablename__ = "family_invites"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id"), index=True)
    code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("parent_users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("parent_users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MemberSettings(Base):
    """Pengaturan per anak (menggantikan angka tunggal per keluarga)."""

    __tablename__ = "member_settings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("members.id"), unique=True)
    coverage: Mapped[str] = mapped_column(String(16), default="juz30")  # juz30 | all
    daily_ayahs: Mapped[int] = mapped_column(Integer, default=1)  # 1, 2, 3, 5
    murajaah_strong_days: Mapped[int] = mapped_column(Integer, default=14)  # 7 | 14
    set_by: Mapped[str] = mapped_column(String(16), default="parent")  # parent | teacher
    placement: Mapped[str | None] = mapped_column(String(16), nullable=True)  # none | basic | fluent (tingkat awal, dapat diubah guru)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TahsinPointProgress(Base):
    """Kemajuan tahsin per Pulau (poin 1-9)."""

    __tablename__ = "tahsin_point_progress"
    __table_args__ = (UniqueConstraint("member_id", "point", name="uq_tahsin_point_member"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("members.id"), index=True)
    point: Mapped[int] = mapped_column(Integer)
    best_score: Mapped[float] = mapped_column(Float, default=0.0)  # 0-10
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_below_threshold: Mapped[bool] = mapped_column(Boolean, default=False)
    decided_by: Mapped[str | None] = mapped_column(String(16), nullable=True)  # parent | teacher
    decider_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    passed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160))
    invite_code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Teacher(Base):
    """Guru: mandiri (diverifikasi orang tua yang mengundang) atau guru instansi (diverifikasi lewat kode instansi)."""

    __tablename__ = "teachers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(16), default="independent")  # independent | institution
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | verified | rejected
    institution_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("institutions.id"), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    invite_code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    grading_target_hours: Mapped[int] = mapped_column(Integer, default=48)  # 24 | 48 | 72
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TeacherDocument(Base):
    """Dokumen dasar guru mandiri. Platform tidak memeriksa; orang tua yang melihat."""

    __tablename__ = "teacher_documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    teacher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teachers.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TeacherLink(Base):
    """Tautan guru-anak. Satu anak paling banyak satu guru aktif; izin dengar rekaman ada di sini."""

    __tablename__ = "teacher_links"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    teacher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teachers.id"), index=True)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id"), index=True)
    member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("members.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="requested")  # requested | active | rejected | revoked
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    recording_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    requested_by: Mapped[uuid.UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecordingAccessLog(Base):
    __tablename__ = "recording_access_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    teacher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teachers.id"))
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    member_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DeletionRequest(Base):
    """Hapus atas permintaan: hilang dari aplikasi seketika, dihapus permanen paling lambat 7 hari."""

    __tablename__ = "deletion_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id"), index=True)
    member_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    requested_by: Mapped[uuid.UUID] = mapped_column(Uuid)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    purge_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | purged
    recording_count: Mapped[int] = mapped_column(Integer, default=0)


class TeacherMessage(Base):
    __tablename__ = "teacher_messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    teacher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teachers.id"), index=True)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id"), index=True)
    member_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    direction: Mapped[str] = mapped_column(String(16), default="to_parent")  # to_parent | to_teacher
    kind: Mapped[str] = mapped_column(String(16), default="note")  # note | reminder
    body: Mapped[str] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TransferRequest(Base):
    """Pindah keluarga ke instansi: dimulai pemilik, disetujui admin instansi."""

    __tablename__ = "transfer_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id"), index=True)
    institution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id"), index=True)
    requested_by: Mapped[uuid.UUID] = mapped_column(Uuid)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | approved | rejected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
