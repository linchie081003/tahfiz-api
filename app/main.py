from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import auth, gamify, home, members, murojaah, notifications, parent, peta, quran, setor, settings as settings_router, tahsin


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except OSError as e:
        raise RuntimeError(
            "PostgreSQL tidak dapat dihubungi. Periksa DATABASE_URL di .env "
            "(contoh: postgresql+asyncpg://hafiz:hafiz_dev@localhost:5432/hafiz). "
            "Lihat docs/setup-postgresql-lokal.md"
        ) from e
    yield


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


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name}
