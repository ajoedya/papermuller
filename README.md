# Papermuller

**Evidence-first Research & Writing Lab**, sebuah aplikasi web lokal untuk menyusun tinjauan literatur yang dapat diaudit, mengimpor PDF full-text yang dimiliki peneliti, menyiapkan manuskrip kerja IMRaD, dan mengamati setiap tahap melalui **interactive research pipeline**.


> **Status**: prototipe penelitian. Semua klaim, metode, hasil, kutipan, dan kebijakan penggunaan AI wajib diverifikasi peneliti. Audit AI bukan peer review.

## Instalasi

Memerlukan **Python 3.11+** dan internet untuk mode riset nyata. Mode demo berjalan offline setelah dependensi terpasang.

```sh
python -m pip install -r requirements.txt
cp env.example .env  # Windows: copy env.example .env
python app.py
```

Di Windows, kamu juga dapat menjalankan `Start.bat` atau `Mulai.bat` (sesudah menginstal dependensi). Buka `http://localhost:8765`. Server hanya mendengarkan `127.0.0.1`.

Default `DEMO_MODE=true` sehingga kamu dapat bereksperimen tanpa API key. Untuk riset nyata, isi `.env` menggunakan kredensial OpenRouter dan OpenAlex, lalu ubah `DEMO_MODE=false`. Kamu juga bisa menyimpannya dari antarmuka pengaturan lokal.

**Jangan pernah commit `.env`, API key, PDF berlisensi, atau isi direktori `projects/` dan `library/` ke GitHub.** Jika sebelumnya pernah terunggah, rotasi key.

## Visual pipeline: 10 tahap

1. Setup Riset — susun rencana dan minta persetujuan peneliti.
2. Discovery Literatur — cari artikel melalui OpenAlex.
3. Verifikasi & PDF — validasi DOI dengan Crossref; menggunakan PDF dari library lokal bila DOI cocok.
4. Screening — pilih artikel yang relevan.
5. Ekstraksi Bukti — susun matriks dari abstrak atau potongan teks PDF dan catat lokasi kutipan.
6. Sintesis Literatur — rancang outline bertema.
7. Draft Manuskrip — tulis draf tinjauan literatur dan lakukan iterasi perbaikan.
8. Audit Sitasi & Klaim — validasi ID sitasi dan dukungan bukti.
9. Adversarial Review — reviewer AI menilai rubrik, ruang lingkup, dan temuan berisiko.
10. Ekspor & Verifikasi — simpan manuskrip kerja, bukti, checklist peneliti, dan disclosure AI.

Klik setiap node flowchart untuk melihat **input, output, status, model yang dikonfigurasi atau benar-benar dilaporkan provider, token, jumlah respons AI, dan biaya bila dilaporkan**. Status diturunkan dari event backend, **bukan animasi progres atau angka buatan**. Saat draft direvisi, tahap 7–9 dapat dikerjakan berulang.

## Multi-model routing

Atur model OpenRouter default melalui `MODEL`. Kosongkan override jika ingin memakai default.

| Setting | Pemakaian |
| --- | --- |
| `MODEL` | Setup riset dan screening |
| `EVIDENCE_MODEL` | Matriks / ekstraksi bukti |
| `WRITER_MODEL` | Outline dan drafting |
| `VERIFIER_MODEL` | Audit dukungan klaim |
| `REVIEW_MODEL` | Review rubrik dan adversarial review |

Setiap field bisa diatur di tab **Konfigurasi**. Nama model pada inspector diambil dari respons OpenRouter bila tersedia; sebelum request berjalan tampil model yang dikonfigurasi. `openrouter/auto` tidak menjamin model yang sama di setiap request. Mode demo selalu ditandai sebagai simulasi.

Jumlah token/biaya hanya muncul ketika OpenRouter menyediakannya dalam respons; tanda *Tidak dilaporkan* berarti data tidak tersedia, bukan gratis. Jangan mengandalkan hitungan demo sebagai biaya nyata. Fallback model dipisahkan dengan koma pada field model default/override.

## Tahap peneliti dan artefak

- **Research scope approval**: edit judul, research questions, asumsi dan kata kunci. AI tidak berhak mengubah lokasi/periode secara diam-diam.
- **PDF library**: unggah PDF digital berlapisan teks hingga 12 MB dan 150 halaman; hubungkan dengan DOI yang benar. PDF scan tanpa teks belum didukung OCR.
- **Evidence ledger**: kutipan, asal abstrak/halaman PDF, dan pemeriksaan referensi. Kecocokan teks bukan bukti otomatis kebenaran interpretasi.
- **IMRaD**: literature review AI disertakan, tetapi Methods/Results hanya berasal dari masukan peneliti atau berupa placeholder yang jelas. AI tidak mengarang hasil empiris.
- **Human verification checklist**: semua pemeriksaan sumber dan deklarasi penggunaan AI harus dilakukan peneliti sendiri.

Berkas disimpan ke `projects/<timestamp>/`. Dokumen paling berguna: `7_final_draft.md`, `7_final_evidence_audit.json`, `8_manuscript_working.md`, `8_evidence_ledger.csv` (jika tersedia), dan `8_human_verification.json`.

## Pengujian

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

Tes menguji audit bukti, impor PDF, kontrak endpoint lokal, routing model, dan telemetry pipeline. Mode riset nyata memerlukan pengujian tambahan dengan akun API masing-masing.

## Keterbatasan dan tanggung jawab

PDF diproses sebagai potongan relevan, bukan sebagai pengganti membaca keseluruhan artikel. Tidak ada OCR pada rilis ini. Tidak ada jaminan bahwa artikel yang ditemukan relevan, cuplikan yang cocok benar-benar mendukung interpretasi klaim, atau skor reviewer mencerminkan kualitas ilmiah. Biaya/kuota tergantung penyedia model. Proyek tidak membuat riset empiris secara otomatis, tidak mengarang metodologi/hasil, dan tidak mengesampingkan kewajiban peneliti untuk mengikuti kebijakan jurnal/institusi.

UI flowchart v5 saat ini menggunakan Bahasa Indonesia; kemampuan alih bahasa UI lama belum dimigrasikan secara penuh (bahasa draf tetap bisa diatur). `i18n.py` lama disimpan untuk migrasi selanjutnya.
