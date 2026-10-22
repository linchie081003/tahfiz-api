# Migrasi database (Alembic)

Urutan: **jalankan migrasi dulu, baru deploy kode baru.** `create_all` saat startup hanya membuat tabel
baru; ia tidak menambah kolom ke tabel yang sudah ada (mis. `parent_users.family_role`).

## Menjalankan ke Supabase
```bash
export ALEMBIC_DATABASE_URL="postgresql+asyncpg://USER:PASS@HOST:5432/postgres"   # atau pakai DATABASE_URL
alembic upgrade head
```
Migrasi idempoten, jadi aman dijalankan di database yang sudah dibuat oleh `create_all`.
Cadangkan database dulu (Supabase: Database → Backups).

## Revisi
- `0001` baseline: tabel yang sudah ada (hanya membuat yang belum ada).
- `0002` peran orang tua (`parent_users.family_role`, default `owner`), `family_invites`,
  `member_settings`, `tahsin_point_progress`.

## Membuat revisi baru
Tulis berkas di `alembic/versions/` (revision berurutan, `down_revision` ke revisi sebelumnya).
Uji lebih dulu di SQLite: `ALEMBIC_DATABASE_URL=sqlite+aiosqlite:///./tes.db alembic upgrade head`.

## Kembali
`alembic downgrade 0001` menghapus tabel baru dan kolom `family_role`.
