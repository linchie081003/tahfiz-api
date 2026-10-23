"""Fungsi bantu tes API."""


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


async def make_teacher(db, email=None):
    """Guru sungguhan (PostgreSQL menegakkan foreign key teacher_links.teacher_id)."""
    import uuid
    from app import models
    t = models.Teacher(email=email or f"{uuid.uuid4().hex[:8]}@g.x", hashed_password="x", name="Guru", status="verified", invite_code=uuid.uuid4().hex[:12])
    db.add(t)
    await db.flush()
    return t.id
