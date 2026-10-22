-- Data uji: anak yang SUDAH LULUS Tahsin (Pulau 1-9) dan siap memulai hafalan baru.
-- Jalankan di Supabase SQL Editor. Ganti 'Anak1' dengan nama anak yang dituju
-- (jika nama kembar, tambahkan filter family_id). Aman dijalankan berulang.
-- Pastikan data surat sudah ada (scripts/import_full_quran.py / halaman Tilawah sekali dibuka).

BEGIN;

-- 1) Nilai 9/10 di semua Pulau, diputuskan "parent"
INSERT INTO tahsin_point_progress (id, member_id, point, best_score, passed, approved_below_threshold, decided_by, passed_at)
SELECT gen_random_uuid(), m.id, p.n, 9, TRUE, FALSE, 'parent', now()
FROM members m CROSS JOIN generate_series(1, 9) AS p(n)
WHERE m.name = 'Anak1'
ON CONFLICT (member_id, point) DO UPDATE
  SET best_score = GREATEST(tahsin_point_progress.best_score, 9), passed = TRUE,
      decided_by = COALESCE(tahsin_point_progress.decided_by, 'parent'),
      passed_at = COALESCE(tahsin_point_progress.passed_at, now());

-- 2) Status Tahsin lulus (membuka Hafalan baru dan Murajaah)
UPDATE members SET tahsin_status = 'passed' WHERE name = 'Anak1';

-- 3) Lewati onboarding dan pastikan pengaturan belajar ada
INSERT INTO member_settings (id, member_id, coverage, daily_ayahs, murajaah_strong_days, set_by, placement)
SELECT gen_random_uuid(), m.id, 'juz30', 1, 14, 'parent', 'basic'
FROM members m WHERE m.name = 'Anak1'
ON CONFLICT (member_id) DO UPDATE SET placement = COALESCE(member_settings.placement, 'basic');

-- 4) Surat pertama (urutan kurikulum 1, An-Nas) jadi hafalan aktif bila belum ada yang aktif
INSERT INTO member_surah_progress (id, member_id, surah_id, status, current_ayah)
SELECT gen_random_uuid(), m.id, s.id, 'in_progress', 1
FROM members m, (SELECT id FROM surahs ORDER BY curriculum_order LIMIT 1) s
WHERE m.name = 'Anak1'
  AND NOT EXISTS (SELECT 1 FROM member_surah_progress x WHERE x.member_id = m.id AND x.status IN ('in_progress', 'needs_retry'))
ON CONFLICT (member_id, surah_id) DO UPDATE SET status = 'in_progress'
  WHERE member_surah_progress.status = 'locked';

COMMIT;

-- Cek: tahsin_status = passed, 9 baris lulus, 1 surat aktif
SELECT m.name, m.tahsin_status,
       (SELECT count(*) FROM tahsin_point_progress t WHERE t.member_id = m.id AND t.passed) AS pulau_lulus,
       (SELECT s.name_id FROM member_surah_progress x JOIN surahs s ON s.id = x.surah_id
         WHERE x.member_id = m.id AND x.status = 'in_progress' LIMIT 1) AS hafalan_aktif
FROM members m WHERE m.name = 'Anak1';
