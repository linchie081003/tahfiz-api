from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import auth, family, gamify, member_progress, privacy, teacher, home, members, murojaah, notifikasi, notifications, parent, peta, quran, setor, settings as settings_router, sesi3, sesi_harian, tahsin, verifikasi, tanda, tilawah


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_migrate:
        from app.migrate import run_migrations

        await run_migrations()  # gagal = start gagal, agar tidak berjalan dengan skema yang salah
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except OSError as e:
        raise RuntimeError(
            "PostgreSQL tidak dapat dihubungi. Periksa DATABASE_URL di .env "
            "(contoh: postgresql+asyncpg://hafiz:hafiz_dev@localhost:5432/hafiz). "
            "Lihat docs/setup-postgresql-lokal.md"
        ) from e
    try:
        from app.database import AsyncSessionLocal
        from app.services import gamification

        async with AsyncSessionLocal() as session:
            await gamification.ensure_reference_data(session)
            await session.commit()
    except Exception:  # data rujukan juga dijamin saat dipakai; jangan gagalkan startup
        pass
    import asyncio

    from app.services import stt

    warm = asyncio.create_task(stt.preload())  # unduh dan muat model Whisper di latar belakang
    worker = None
    if settings.stt_enabled and settings.stt_inline_worker:
        from app.services import stt_queue

        worker = asyncio.create_task(stt_queue.run_forever())  # antrean pra-cek (tabel stt_jobs) di proses ini
    yield
    warm.cancel()
    if worker:
        worker.cancel()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

_dev = settings.environment.lower() in ("development", "dev", "test")
if _dev:
    # Vite bisa pindah port (5176+) bila 5175 sibuk; LAN IP untuk HP di jaringan yang sama.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|\[::1\]|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3})(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router)
app.include_router(members.router)
app.include_router(parent.router)
app.include_router(settings_router.router)
app.include_router(quran.router)
app.include_router(setor.router)
app.include_router(home.router)
app.include_router(peta.router)
app.include_router(murojaah.router)
app.include_router(gamify.router)
app.include_router(notifications.router)
app.include_router(tahsin.router)
app.include_router(family.router)
app.include_router(member_progress.router)
app.include_router(teacher.router)
app.include_router(privacy.router)
app.include_router(privacy.inst_router)
app.include_router(tilawah.router)
app.include_router(tanda.router)
app.include_router(sesi3.router)
app.include_router(sesi_harian.router)
app.include_router(verifikasi.router)
app.include_router(notifikasi.router)


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name}
