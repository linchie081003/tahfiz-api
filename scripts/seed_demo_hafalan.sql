-- Butuh migrasi 0009 dan 0010 (alembic upgrade head) lebih dulu.
-- Data contoh yang konsisten: tiap surat hafal punya riwayat setoran (semua ayat) yang DINILAI LULUS,
-- status surat 'passed', baru kemudian jadwal murajaah dibuat. Tanpa lulus, murajaah tidak muncul.
-- Jalankan di Supabase SQL Editor. Ubah dua nilai di bawah (nama anak dan jumlah surat hafal).
-- Aman diulang: data contoh lama untuk surat yang sama diganti, tidak dobel.
do $$
declare
  v_name   text := 'NAMA ANAK';  -- << ganti dengan nama profil anak persis seperti di aplikasi
  v_count  int  := 5;            -- << jumlah surat pertama di jalur Juz 30 yang dianggap sudah hafal
  v_member uuid;
  v_family uuid;
  v_sub    uuid;
  v_range  uuid;
  r        record;
begin
  select id, family_id into v_member, v_family from members where name = v_name order by created_at desc limit 1;
  if v_member is null then
    raise exception 'Anak "%" tidak ditemukan. Cek ejaan nama profil.', v_name;
  end if;

  for r in
    select id, ayah_count, row_number() over (order by curriculum_order, id) as rn
    from surahs where juz_number = 30
  loop
    if r.rn <= v_count then
      -- surat sudah hafal lengkap
      insert into member_surah_progress (id, member_id, surah_id, status, current_ayah)
      values (gen_random_uuid(), v_member, r.id, 'passed', r.ayah_count)
      on conflict (member_id, surah_id) do update set status = 'passed', current_ayah = excluded.current_ayah;

      -- riwayat setoran lengkap (ayat 1 sampai akhir) yang sudah dinilai lulus; contoh lama dibersihkan dulu
      delete from murojaah_items where member_id = v_member and surah_id = r.id;
      delete from memorized_ranges where member_id = v_member and surah_id = r.id and submission_id in
        (select id from submissions where member_id = v_member and surah_id = r.id and evaluator_notes = 'Data contoh');
      delete from evaluations where member_id = v_member and submission_id in
        (select id from submissions where member_id = v_member and surah_id = r.id and evaluator_notes = 'Data contoh');
      delete from submissions where member_id = v_member and surah_id = r.id and evaluator_notes = 'Data contoh';
      v_sub := gen_random_uuid();
      insert into submissions (id, member_id, family_id, context, surah_id, ayah_start, ayah_end, reference_text,
                               recording_key, recording_deleted_at, status, ai_status, evaluator_notes, created_at, evaluated_at)
      values (v_sub, v_member, v_family, 'ziyadah', r.id, 1, r.ayah_count, 'Data contoh',
              'tidak-disimpan', now(), 'passed', 'completed', 'Data contoh', now() - ((v_count - r.rn + 2) || ' days')::interval, now() - ((v_count - r.rn + 2) || ' days')::interval);

      -- rentang lulus dan penilaian (tabel baru), lalu jadwal murajaah per rentang
      v_range := gen_random_uuid();
      insert into evaluations (id, member_id, submission_id, evaluator_role, result, notes, source)
      values (gen_random_uuid(), v_member, v_sub, 'unknown', 'passed', 'Data contoh', 'migration');
      insert into memorized_ranges (id, member_id, surah_id, ayah_start, ayah_end, status, submission_id, source)
      values (v_range, v_member, r.id, 1, r.ayah_count, 'passed', v_sub, 'migration');

      -- murajaah: jatuh tempo hari ini atau kemarin, beberapa ditandai lemah agar didahulukan
      insert into murojaah_items (id, member_id, surah_id, due_date, ease_factor, interval_days, weak_score, completed, range_id, ayah_start, ayah_end)
      values (gen_random_uuid(), v_member, r.id, current_date - (r.rn % 2)::int, 2.5, 1, case when r.rn % 3 = 0 then 2 else 0 end, false, v_range, 1, r.ayah_count);

    elsif r.rn = v_count + 1 then
      -- surat berikutnya siap direncanakan anak (belum dipilih; anak membuat rencana di aplikasi)
      insert into member_surah_progress (id, member_id, surah_id, status, current_ayah)
      values (gen_random_uuid(), v_member, r.id, 'in_progress', 1)
      on conflict (member_id, surah_id) do update
        set status = case when member_surah_progress.status = 'passed' then 'passed' else 'in_progress' end;
    end if;
  end loop;

  -- rencana dikosongkan supaya anak diminta memilih surat dulu
  update member_settings set focus_surah_id = null where member_id = v_member;

  raise notice 'Selesai: % surat hafal untuk %, murajaah siap.', v_count, v_name;
end $$;
