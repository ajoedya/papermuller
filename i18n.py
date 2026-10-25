"""
i18n.py  -  MESSAGES IN SEVERAL LANGUAGES
=========================================
Every progress message the harness shows lives here, once per language.
The web page has its own translations inside ui.html.

To add a language: copy the whole "en" block, change the key (e.g. "ms"),
and translate the text on the right. Keep the {placeholders} unchanged.
"""

LANG = "en"  # changed at runtime from the UI_LANGUAGE setting

MESSAGES = {
    "en": {
        "searching": "   searching: {kw}",
        "search_start": "Stage 2: searching papers in OpenAlex...",
        "candidates": "Found {n} candidate papers.",
        "verify_start": "Stage 3: verifying papers in Crossref, then screening for relevance...",
        "verified": "Passed verification: {v} of {n}.",
        "chosen": "   kept {c} of {n} relevant papers",
        "too_few": "Fewer than {m} relevant, verified papers. Try broader keywords or an earlier start year, then start again.",
        "matrix_start": "Stage 4: summarising papers into the literature matrix...",
        "summarised": "   summarised {ids}",
        "outline_start": "Stage 5: planning the themes...",
        "draft_write": "Stage 5: writing the draft (round {r})...",
        "draft_revise": "Stage 5: revising the draft (round {r})...",
        "cite_fail": "Citation check FAILED: the draft cites {ids}, which are not in the evidence. Fixing.",
        "cite_ok": "Citation check passed ({u} of {n} papers cited).",
        "review_start": "Stage 6: the reviewer is scoring the draft (round {r})...",
        "review_score": "Reviewer score: {s}/10 (target {t}). Details: {detail}",
        "target_reached": "Target score reached.",
        "limit_best": "Revision limit reached. Using the best draft (round {r}, score {s}).",
        "no_draft": "No draft passed the citation check. Please run again.",
        "final_saved": "Final draft saved (round {r}, score {s}/10) with a reference list.",
        "topic": "Topic: {t}",
        "mode_demo": "Mode: DEMO (sample data)",
        "mode_real": "Mode: REAL",
        "plan_start": "Stage 1: drafting the research plan...",
        "plan_ready": "Plan ready. Please review and approve it.",
        "approved": "Plan approved by the user.",
        "done": "Done.",
        "stopped": "The process stopped.",
        "check_settings": "Settings file",
        "check_demo": "Demo mode",
        "check_demo_note": "Demo mode is on, so no connection is needed. Turn it off for real research.",
        "check_ai": "AI model (OpenRouter)",
        "check_ai_reply": "Replied: {r}",
        "check_oa": "Paper search (OpenAlex)",
        "check_oa_ok": "{n} sample papers found",
        "check_oa_bad": "No answer. Check your OpenAlex key.",
        "check_cr": "Paper verification (Crossref)",
        "busy": "Another process is still running.",
        "no_topic": "The topic is empty.",
        "quota": "The daily free-model quota on OpenRouter is used up. Wait until it resets tomorrow, "
                 "or buy 10 credits once to raise it to 1,000 requests per day.",
    },
    "id": {
        "searching": "   mencari: {kw}",
        "search_start": "Tahap 2: mencari artikel di OpenAlex...",
        "candidates": "Ditemukan {n} artikel kandidat.",
        "verify_start": "Tahap 3: memeriksa keaslian di Crossref, lalu menyaring relevansi...",
        "verified": "Lolos verifikasi: {v} dari {n}.",
        "chosen": "   dipilih {c} dari {n} artikel yang relevan",
        "too_few": "Artikel relevan yang lolos verifikasi kurang dari {m}. Coba kata kunci yang lebih umum atau tahun yang lebih awal, lalu mulai lagi.",
        "matrix_start": "Tahap 4: merangkum artikel ke matriks literatur...",
        "summarised": "   dirangkum {ids}",
        "outline_start": "Tahap 5: menyusun kerangka tema...",
        "draft_write": "Tahap 5: menulis draf (putaran {r})...",
        "draft_revise": "Tahap 5: merevisi draf (putaran {r})...",
        "cite_fail": "Pemeriksaan sitasi GAGAL: draf mengutip {ids} yang tidak ada di bukti. Diperbaiki.",
        "cite_ok": "Pemeriksaan sitasi lolos ({u} dari {n} artikel dikutip).",
        "review_start": "Tahap 6: penelaah menilai draf (putaran {r})...",
        "review_score": "Nilai penelaah: {s}/10 (target {t}). Rincian: {detail}",
        "target_reached": "Target nilai tercapai.",
        "limit_best": "Batas putaran revisi tercapai. Draf terbaik (putaran {r}, nilai {s}) dipakai.",
        "no_draft": "Tidak ada draf yang lolos pemeriksaan sitasi. Coba jalankan lagi.",
        "final_saved": "Draf akhir disimpan (putaran {r}, nilai {s}/10) beserta daftar pustaka.",
        "topic": "Topik: {t}",
        "mode_demo": "Mode: LATIHAN (data contoh)",
        "mode_real": "Mode: NYATA",
        "plan_start": "Tahap 1: menyusun rencana penelitian...",
        "plan_ready": "Rencana siap. Silakan periksa lalu setujui.",
        "approved": "Rencana disetujui pengguna.",
        "done": "Selesai.",
        "stopped": "Proses berhenti.",
        "check_settings": "Berkas pengaturan",
        "check_demo": "Mode latihan",
        "check_demo_note": "Mode latihan aktif, jadi tidak perlu koneksi. Matikan untuk riset nyata.",
        "check_ai": "Model AI (OpenRouter)",
        "check_ai_reply": "Menjawab: {r}",
        "check_oa": "Pencarian artikel (OpenAlex)",
        "check_oa_ok": "{n} artikel contoh ditemukan",
        "check_oa_bad": "Tidak ada jawaban. Periksa kunci OpenAlex.",
        "check_cr": "Verifikasi artikel (Crossref)",
        "busy": "Masih ada proses yang berjalan.",
        "no_topic": "Topik masih kosong.",
        "quota": "Jatah harian model gratis OpenRouter sudah habis. Tunggu sampai jatah direset besok, "
                 "atau isi saldo 10 kredit sekali untuk menaikkan jatah menjadi 1.000 permintaan per hari.",
    },
}


def set_language(code):
    global LANG
    LANG = code if code in MESSAGES else "en"


def tr(key, **values):
    """Translate a message key into the current language, filling in {placeholders}."""
    text = MESSAGES.get(LANG, MESSAGES["en"]).get(key) or MESSAGES["en"].get(key, key)
    return text.format(**values)
