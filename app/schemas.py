import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.models import AgeMode, EvaluatorType, SubmissionContext, SubmissionStatus, TahsinStatus


class RegisterFamilyIn(BaseModel):
    family_name: str
    admin_name: str
    admin_email: EmailStr
    admin_password: str = Field(min_length=8)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    role: str
    family_access_code: str


class SessionOut(BaseModel):
    role: str
    member_id: uuid.UUID | None
    member_name: str | None
    age_mode: AgeMode | None = None
    family_name: str
    family_access_code: str
    needs_child_profile: bool


class PublicChildOut(BaseModel):
    id: uuid.UUID
    name: str
    color: str
    has_pin: bool


class PublicFamilyChildrenOut(BaseModel):
    family_name: str
    children: list[PublicChildOut]


class ChildLoginIn(BaseModel):
    access_code: str = Field(max_length=16)
    child_id: uuid.UUID
    pin: str = Field(default="", max_length=32)


class MemberCreateIn(BaseModel):
    name: str
    birth_date: date | None = None
    age_mode: AgeMode = AgeMode.sd


class MemberUpdateIn(BaseModel):
    age_mode: AgeMode | None = None


class PasswordResetIn(BaseModel):
    email: EmailStr
    access_code: str = Field(min_length=4, max_length=12)
    new_password: str = Field(min_length=8)


class MemberOut(BaseModel):
    id: uuid.UUID
    name: str
    age_mode: AgeMode
    tahsin_status: TahsinStatus
    color: str

    model_config = {"from_attributes": True}


class MemberDeleteOut(BaseModel):
    ok: bool = True
    access_token: str | None = None


class ParentChildSummaryOut(BaseModel):
    id: uuid.UUID
    name: str
    color: str
    age_mode: AgeMode
    tahsin_status: TahsinStatus
    xp: int
    streak_days: int
    level: int
    passed_surahs: int
    pending_setor: int
    tahsin_line: str = ""
    hafalan_open: bool = True
    mandatory_passed: int = 0
    hafalan_line: str = ""
    murajaah_due: int = 0
    murajaah_surah: str = ""


class ParentDashboardOut(BaseModel):
    family_name: str
    family_access_code: str
    queue_total: int
    active_member_id: uuid.UUID | None = None
    children: list[ParentChildSummaryOut]


class WeeklyDayOut(BaseModel):
    date: date
    label: str
    ayat: int


class WeeklyReportOut(BaseModel):
    member_id: uuid.UUID
    member_name: str
    week_start: date
    week_end: date
    ayat_total: int
    active_days: int
    surahs_finished: int
    daily: list[WeeklyDayOut]
    overdue_murojaah_count: int
    overdue_murojaah_surahs: list[str]
    note: str


class PinVerifyIn(BaseModel):
    pin: str


class FamilySettingsOut(BaseModel):
    evaluator_type: EvaluatorType
    daily_ziyadah_ayahs: int
    daily_murojaah_cap: int
    reminder_hour: int
    celebrations_enabled: bool
    leaderboard_enabled: bool
    reciter_id: str
    playback_speed: float
    arabic_font_size: str
    show_tajweed_colors: bool
    parent_can_evaluate: bool = True

    model_config = {"from_attributes": True}


class FamilySettingsUpdateIn(BaseModel):
    evaluator_type: EvaluatorType | None = None
    daily_ziyadah_ayahs: int | None = Field(default=None, ge=1, le=30)
    daily_murojaah_cap: int | None = Field(default=None, ge=1, le=30)
    reminder_hour: int | None = None
    celebrations_enabled: bool | None = None
    leaderboard_enabled: bool | None = None
    reciter_id: str | None = None
    playback_speed: float | None = None
    arabic_font_size: str | None = None
    show_tajweed_colors: bool | None = None
    parent_can_evaluate: bool | None = None


class ReciterOut(BaseModel):
    id: str
    label: str
    gender: str
    description: str
    style: str
    default_for_age: bool = False


class BeautyRewardOut(BaseModel):
    submission_id: uuid.UUID
    surah_id: int
    ayah_start: int
    ayah_end: int
    audio_urls: list[str]
    label: str


class SurahOut(BaseModel):
    id: int
    name_ar: str
    name_id: str
    ayah_count: int
    juz_number: int
    curriculum_order: int

    model_config = {"from_attributes": True}


class AyahOut(BaseModel):
    id: int
    surah_id: int
    ayah_number: int
    text_uthmani: str
    text_tajweed: str | None = None
    tajwid_markup: dict | None
    audio_url: str | None
    reciter_id: str | None = None

    model_config = {"from_attributes": True}


class SubmissionCreateOut(BaseModel):
    id: uuid.UUID
    status: SubmissionStatus
    ai_status: str


class CorrectionIn(BaseModel):
    status: SubmissionStatus
    rubric_scores: dict[str, int] | None = None
    evaluator_notes: str | None = None
    reason: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _stars(self):
        _check_pass_stars(self.status, self.rubric_scores)
        return self


MIN_STAR_PASS = 3  # bintang minimal di tiap penilaian agar boleh diluluskan (skala 1-5)


def _check_pass_stars(status, rubric_scores):
    if status == SubmissionStatus.passed and rubric_scores and any(v < MIN_STAR_PASS for v in rubric_scores.values()):
        raise ValueError(f"Lulus butuh minimal {MIN_STAR_PASS} bintang di setiap penilaian")


class EvaluateSubmissionIn(BaseModel):
    status: SubmissionStatus
    rubric_scores: dict[str, int] | None = None
    evaluator_notes: str | None = None

    @model_validator(mode="after")
    def _stars(self):
        _check_pass_stars(self.status, self.rubric_scores)
        return self


class SubmissionOut(BaseModel):
    id: uuid.UUID
    context: SubmissionContext
    surah_id: int | None
    reference_text: str
    reference_text_tajweed: str | None = None
    tahsin_point: int | None = None  # ada = ujian Pulau tahsin
    status: SubmissionStatus
    ai_status: str
    ai_insights: dict[str, Any] | None
    rubric_scores: dict[str, int] | None
    recording_url: str | None = None
    created_at: datetime
    member_name: str | None = None

    model_config = {"from_attributes": True}


class HomeOut(BaseModel):
    greeting_name: str
    age_mode: AgeMode | None = None
    streak_days: int
    xp: int
    level: int
    rank_title: str
    xp_next_level: int
    mission_title: str
    mission_detail: str
    mission_xp: int
    mission_action: str
    tahsin_status: TahsinStatus
    tahsin_wajib_lulus: int | None = None  # jumlah Pulau wajib (1-3) yang sudah lulus
    menu_locks: dict[str, str]
    level_progress: float
    beauty_reward: BeautyRewardOut | None = None
    parent_preview: bool = False
    mission_items: dict[str, str] = {}


class PetaNodeOut(BaseModel):
    surah_id: int
    name_id: str
    ayah_count: int
    status: str
    curriculum_order: int
    selectable: bool = False  # mode bebas: surat ini boleh dipilih untuk dihafal sekarang


class SetorPlanOut(BaseModel):
    """Rencana setoran berikutnya: surat pendek sekaligus utuh, surat panjang sesuai target harian."""

    surah_id: int
    name_id: str
    ayah_count: int
    ayah_start: int
    ayah_end: int
    mode: str  # seluruh_surat | target_harian
    done_ayahs: int


class PetaOut(BaseModel):
    juz_number: int
    track: str = "juz30"
    passed_count: int
    total_count: int
    active_surah_id: int | None
    active_surah_name: str | None
    unlock_hint: str | None
    nodes: list[PetaNodeOut]
    hafalan_order: str = "sequential"
    plan: SetorPlanOut | None = None
    planned: bool = False  # anak sudah membuat rencana surat yang dihafal
    suggested_surah_id: int | None = None


class MurojaahItemOut(BaseModel):
    id: uuid.UUID
    surah_id: int
    surah_name: str
    due_date: date
    ayah_start: int | None = None
    ayah_end: int | None = None

    model_config = {"from_attributes": True}


class MurojaahSessionItemOut(BaseModel):
    id: uuid.UUID
    ayah_start: int
    ayah_end: int


class MurojaahBlockOut(BaseModel):
    surah_id: int
    surah_name: str
    ayah_start: int
    ayah_end: int
    items: list[MurojaahSessionItemOut]


class MurojaahSessionOut(BaseModel):
    active: bool  # Sesi 1 aktif jika ada minimal satu ayat lulus
    max_ayah: int
    total_ayah: int
    blocks: list[MurojaahBlockOut]


class MurojaahCompleteIn(BaseModel):
    rating: str = Field(pattern="^(lancar|ragu|lupa)$")


class BadgeOut(BaseModel):
    id: str
    title: str
    description: str
    earned: bool
    kind: str | None = None  # jenis syarat: tahsin, juz30, streak (untuk ikon)
    earned_at: datetime | None = None


class GamificationOut(BaseModel):
    xp: int
    level: int
    xp_level_start: int = 0
    xp_next_level: int = 100
    rank_title: str
    streak_days: int
    badges: list[BadgeOut]


class AiConsentIn(BaseModel):
    granted: bool


class PushUnsubscribeIn(BaseModel):
    endpoint: str


class PushSubscribeIn(BaseModel):
    endpoint: str
    keys: dict[str, str]
