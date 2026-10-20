# Pra-cek AI dengan Whisper sendiri (open source)

Suara anak diproses di servermu sendiri, tidak dikirim ke pihak ketiga.
Perangkat lunak: [Speaches](https://github.com/speaches-ai/speaches) (MIT, API kompatibel OpenAI) + model Whisper.

## 1. Jalankan server transkripsi
```bash
docker compose -f deploy/compose.stt.yaml up -d
curl localhost:8000/health        # harus menjawab OK
```

## 2. Unduh model (sekali)
```bash
uvx speaches-cli model download Systran/faster-whisper-small
```
Titik awal yang disarankan: `Systran/faster-whisper-small` (multibahasa, ringan, cukup untuk CPU).
Bila server punya RAM >= 8 GB / GPU, coba `Systran/faster-whisper-medium` atau `Systran/faster-whisper-large-v3`.
Ganti nama model di `STT_MODEL` setelah diunduh.

## 3. Uji transkripsi
```bash
curl -s localhost:8000/v1/audio/transcriptions \
  -F "file=@contoh.webm" -F "model=Systran/faster-whisper-small" -F "language=ar"
```

## 4. Hubungkan ke API Hafiz (`.env`)
```
STT_ENABLED=true
STT_BASE_URL=http://localhost:8000/v1      # bila API di Docker yang sama: http://hafiz-stt:8000/v1
STT_MODEL=Systran/faster-whisper-small
STT_API_KEY=                               # kosong bila Speaches tanpa API_KEY
```
Restart API, lalu orang tua mencentang izin di Pengaturan -> Pra-cek AI.

## Catatan penting
- **Akurasi belum teruji** untuk bacaan Qur'an oleh anak kecil. Uji 20-30 rekaman nyata dan bandingkan dengan penilaian orang tua sebelum diandalkan. Hasilnya hanya saran.
- Setoran pertama setelah server dinyalakan bisa lambat (model dimuat). `STT_MODEL_TTL=-1` menjaga model tetap termuat.
- CPU: transkripsi ayat pendek biasanya beberapa detik; timeout API 45 detik (`STT_TIMEOUT_SECONDS` di kode, `stt_timeout_seconds`).
- Model Whisper yang di-fine-tune khusus bacaan Qur'an ada di Hugging Face (mis. `tarteel-ai/whisper-base-ar-quran`, Apache-2.0),
  tetapi formatnya Transformers, bukan CTranslate2 yang dipakai Speaches. Memakainya butuh konversi
  (`ct2-transformers-converter`) dan belum diverifikasi bisa dimuat Speaches. Coba setelah model umum diuji.
- Jangan membuka port 8000 ke internet. Bila diakses lewat jaringan, set `API_KEY` di Speaches dan `STT_API_KEY` yang sama.
