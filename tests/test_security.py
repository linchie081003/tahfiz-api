"""Uji keamanan: pembatas percobaan, pencabutan token, hak ubah age_mode, validasi rahasia."""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app import ratelimit
from app.config import Settings
from app.database import Base, get_db
from app.main import app


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    async def _get_db():
        async with maker() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_db] = _get_db
    ratelimit.limiter.reset()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c
    app.dependency_overrides.clear()
    ratelimit.limiter.reset()
    await engine.dispose()


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


async def register(c, email="ortu@x.com", pw="rahasia123"):
    r = await c.post("/auth/register-family", json={
        "family_name": "Keluarga", "admin_name": "Ayah", "admin_email": email, "admin_password": pw})
    assert r.status_code == 201, r.text
    return r.json()


async def add_child(c, tok, name="Adik"):
    r = await c.post("/members", json={"name": name}, headers=H(tok))
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_family_code_is_six_digits(client):
    data = await register(client)
    assert len(data["family_access_code"]) == 6 and data["family_access_code"].isdigit()


async def test_login_rate_limited_by_email(client):
    await register(client)
    codes = []
    for _ in range(10):
        r = await client.post("/auth/login", json={"email": "ortu@x.com", "password": "salahsalah"})
        codes.append(r.status_code)
    assert codes[:8] == [401] * 8
    assert 429 in codes[8:]


async def test_reset_password_rate_limited(client):
    data = await register(client)
    codes = []
    for i in range(7):
        r = await client.post("/auth/reset-password", json={
            "email": "ortu@x.com", "access_code": "000000", "new_password": "barubaru123"})
        codes.append(r.status_code)
    assert 429 in codes
    assert data["family_access_code"] != "000000"


async def test_reset_password_revokes_old_parent_token(client):
    data = await register(client)
    old = data["access_token"]
    assert (await client.get("/auth/session", headers=H(old))).status_code == 200
    r = await client.post("/auth/reset-password", json={
        "email": "ortu@x.com", "access_code": data["family_access_code"], "new_password": "barubaru123"})
    assert r.status_code == 200
    assert (await client.get("/auth/session", headers=H(old))).status_code == 401
    new = (await client.post("/auth/login", json={"email": "ortu@x.com", "password": "barubaru123"})).json()
    assert (await client.get("/auth/session", headers=H(new["access_token"]))).status_code == 200


async def test_child_token_dies_when_child_deleted(client):
    data = await register(client)
    tok = data["access_token"]
    cid = await add_child(client, tok)
    r = await client.post("/auth/child-login", json={
        "access_code": data["family_access_code"], "child_id": cid, "pin": ""})
    assert r.status_code == 200
    ctok = r.json()["access_token"]
    assert (await client.get("/auth/session", headers=H(ctok))).status_code == 200
    d = await client.delete(f"/members/{cid}", headers=H(tok))
    assert d.status_code == 200, d.text
    assert (await client.get("/auth/session", headers=H(ctok))).status_code == 401


async def test_child_cannot_change_age_mode(client):
    data = await register(client)
    tok = data["access_token"]
    cid = await add_child(client, tok)
    ctok = (await client.post("/auth/child-login", json={
        "access_code": data["family_access_code"], "child_id": cid, "pin": ""})).json()["access_token"]
    r = await client.patch(f"/members/{cid}", json={"age_mode": "adult"}, headers=H(ctok))
    assert r.status_code == 403
    ok = await client.patch(f"/members/{cid}", json={"age_mode": "adult"}, headers=H(tok))
    assert ok.status_code == 200 and ok.json()["age_mode"] == "adult"


async def test_child_login_rate_limited(client):
    data = await register(client)
    tok = data["access_token"]
    cid = await add_child(client, tok)
    await client.put("/members/settings-pin", json={"pin": "1234"}, headers=H(tok))
    # beri anak PIN lewat DB tidak tersedia di sini; cukup uji batas pada kombinasi kode:anak
    codes = []
    for _ in range(12):
        r = await client.post("/auth/child-login", json={
            "access_code": data["family_access_code"], "child_id": cid, "pin": "x"})
        codes.append(r.status_code)
    assert 429 in codes


async def test_oversized_pin_rejected(client):
    r = await client.post("/auth/child-login", json={"access_code": "123456", "child_id": "00000000-0000-0000-0000-000000000000", "pin": "x" * 500})
    assert r.status_code == 422


async def test_garbage_and_tampered_token_rejected(client):
    data = await register(client)
    assert (await client.get("/auth/session", headers=H("bukan.token.valid"))).status_code == 401
    assert (await client.get("/auth/session", headers=H(data["access_token"][:-3] + "abc"))).status_code == 401


def test_prod_rejects_default_jwt_secret():
    with pytest.raises(ValueError):
        Settings(environment="production", _env_file=None)


def test_prod_accepts_strong_secret():
    s = Settings(environment="production", jwt_secret="a" * 48, _env_file=None)
    assert s.environment == "production"


def test_prod_rejects_default_s3_keys():
    with pytest.raises(ValueError):
        Settings(environment="production", jwt_secret="a" * 48, use_local_storage=False, _env_file=None)


async def test_weekly_report_scoped_to_family_and_parent_only(client):
    a = await register(client, "a@x.com")
    b = await register(client, "b@x.com")
    cid = await add_child(client, a["access_token"])
    ok = await client.get(f"/parent/weekly-report?member_id={cid}", headers=H(a["access_token"]))
    assert ok.status_code == 200 and ok.json()["ayat_total"] == 0 and len(ok.json()["daily"]) == 7
    other = await client.get(f"/parent/weekly-report?member_id={cid}", headers=H(b["access_token"]))
    assert other.status_code == 404
    ctok = (await client.post("/auth/child-login", json={
        "access_code": a["family_access_code"], "child_id": cid, "pin": ""})).json()["access_token"]
    assert (await client.get(f"/parent/weekly-report?member_id={cid}", headers=H(ctok))).status_code == 403
