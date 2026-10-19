-- Jalankan sebagai superuser (mis. postgres) di PostgreSQL lokal
CREATE USER hafiz WITH PASSWORD 'hafiz_dev';
CREATE DATABASE hafiz OWNER hafiz;
GRANT ALL PRIVILEGES ON DATABASE hafiz TO hafiz;

\connect hafiz
GRANT ALL ON SCHEMA public TO hafiz;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO hafiz;
