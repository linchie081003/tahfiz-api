from datetime import date, datetime, timedelta, timezone

from app import models
from app.services.reminders import reminder_message, run_reminders
from tests.helpers import H, add_child, register

AT_17_WIB = datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)  # 17.00 Asia/Jakarta


async def _setup(db, member, *, due=True, parent_sub=True):
    db.add(models.FamilySettings(family_id=member.family_id, reminder_hour=17))
    pu = models.ParentUser(family_id=member.family_id, email="p@x.com", hashed_password="h", name="Ayah")
    db.add(pu)
    await db.flush()
    db.add(models.MemberPushSubscription(member_id=member.id, endpoint_hash="h1", endpoint="https://push/child", p256dh="k", auth="a"))
    if parent_sub:
        db.add(models.PushSubscription(parent_user_id=pu.id, endpoint="https://push/parent", p256dh="k", auth="a"))
    if due:
        db.add(models.MurojaahItem(member_id=member.id, surah_id=114, due_date=date(2026, 10, 20), completed=False))
    await db.flush()


def recorder(result=True):
    sent = []

    async def send(sub, payload):
        sent.append((sub["endpoint"], payload))
        return result

    return sent, send


async def test_sends_to_child_and_parent_once_per_day(db_session, member_with_ziyadah):
    await _setup(db_session, member_with_ziyadah)
    sent, send = recorder()
    s1 = await run_reminders(db_session, AT_17_WIB, send)
    assert s1["members_notified"] == 1 and s1["sent"] == 2
    assert {e for e, _ in sent} == {"https://push/child", "https://push/parent"}
    assert "An-Nas" in sent[0][1]["body"] and sent[0][1]["url"] == "/murojaah"
    s2 = await run_reminders(db_session, AT_17_WIB + timedelta(minutes=1), send)
    assert s2["members_notified"] == 0 and len(sent) == 2  # tidak dobel di hari yang sama


async def test_skips_wrong_hour_and_when_nothing_due(db_session, member_with_ziyadah):
    await _setup(db_session, member_with_ziyadah, due=False)
    sent, send = recorder()
    assert (await run_reminders(db_session, AT_17_WIB, send))["members_notified"] == 0  # tak ada murojaah
    db_session.add(models.MurojaahItem(member_id=member_with_ziyadah.id, surah_id=114, due_date=date(2026, 10, 20)))
    await db_session.flush()
    assert (await run_reminders(db_session, AT_17_WIB + timedelta(hours=2), send))["members_notified"] == 0  # bukan jam 17
    assert sent == []


async def test_gone_subscriptions_are_removed(db_session, member_with_ziyadah):
    await _setup(db_session, member_with_ziyadah)
    _, send = recorder("gone")
    s = await run_reminders(db_session, AT_17_WIB, send)
    assert s["removed"] == 2 and s["sent"] == 0


def test_message_truncates_long_lists():
    m = reminder_message("Adik", ["A", "B", "C", "D"], 4)
    assert m["body"] == "4 surat menunggu: A, B, C…"


async def test_child_and_parent_subscribe_scopes_and_validation(client):
    reg = await register(client)
    tok = reg["access_token"]
    cid = await add_child(client, tok)
    ctok = (await client.post("/auth/child-login", json={
        "access_code": reg["family_access_code"], "child_id": cid, "pin": ""})).json()["access_token"]
    body = {"endpoint": "https://push/x", "keys": {"p256dh": "k", "auth": "a"}}
    assert (await client.post("/notifications/push-subscribe", json=body, headers=H(ctok))).json()["scope"] == "child"
    assert (await client.post("/notifications/push-subscribe", json=body, headers=H(ctok))).status_code == 200  # idempoten
    assert (await client.post("/notifications/push-subscribe", json=body, headers=H(tok))).json()["scope"] == "parent"
    bad = await client.post("/notifications/push-subscribe", json={"endpoint": "https://p/y", "keys": {}}, headers=H(tok))
    assert bad.status_code == 422
    assert (await client.post("/notifications/push-subscribe", json=body)).status_code in (401, 403)
    assert (await client.post("/notifications/push-unsubscribe", json={"endpoint": "https://push/x"}, headers=H(ctok))).status_code == 200
