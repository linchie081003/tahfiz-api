import pytest

from app import migrate


@pytest.mark.asyncio
async def test_migrasi_otomatis_dilewati_di_sqlite(monkeypatch):
    called = []
    monkeypatch.setattr(migrate, "_upgrade", lambda: called.append(1))
    monkeypatch.setattr(migrate.settings, "database_url", "sqlite+aiosqlite:///./x.db")
    await migrate.run_migrations()
    assert called == []
