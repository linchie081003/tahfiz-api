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
