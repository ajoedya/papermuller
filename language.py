"""
language.py  -  ONE PLACE FOR "WHICH LANGUAGE DO WE WRITE IN?"
==============================================================
The LANGUAGE setting is "Auto" (write in the language of the topic) or a language name such
as "English" or "Indonesian". With "Auto", the plan stage detects the language of the topic and
stores it in the plan. Every later stage asks writing_language() instead of reading the setting
on its own, so the plan, the outline, the literature review and the full paper always agree.

Search terms always stay in English, because literature databases index English text best.
"""

import re

AUTO = "Auto"
_NAME = re.compile(r"[A-Za-z][A-Za-z \-]{1,28}")
_SAME = {"indonesian": "Indonesian", "bahasa indonesia": "Indonesian", "indonesia": "Indonesian",
         "bahasa": "Indonesian", "english": "English", "inggris": "English"}


def clean_name(value):
    """A language name made of letters only, else "" (empty, or anything that is not a name)."""
    text = str(value or "").strip()
    return text.title() if _NAME.fullmatch(text) else ""


def canonical(name):
    """The same language under one spelling, for example "Bahasa Indonesia" becomes "Indonesian"."""
    return _SAME.get(name.lower(), name)


def writing_language(settings, plan=None):
    """The language the plan, draft and paper are written in."""
    choice = clean_name(settings.get("LANGUAGE"))
    if choice and choice.lower() != AUTO.lower():
        return canonical(choice)
    return canonical(clean_name((plan or {}).get("language"))) or "English"


# Words the finished paper shows. A language without an entry here is written in its own language
# but with English headings.
LABELS = {
    "English": {
        "abstract": "Abstract", "keywords": "Keywords", "introduction": "1. Introduction",
        "literature_review": "2. Literature Review", "methods": "3. Methods", "results": "4. Results",
        "discussion": "5. Discussion", "conclusion": "6. Conclusion", "references": "References",
        "author_text": "Author-supplied text, not verified by AI.", "todo_marker": "[AUTHOR TO COMPLETE]",
        "todo_methods": "Design, data sources, sample, variables, procedures, and research ethics.",
        "todo_results": "Analysis results and tables or figures derived from actual data.",
        "pending": "Results: [pending author analysis]",
        "banner_ok": ("DRAFT — PASSED AI REVIEW, AWAITING RESEARCHER VERIFICATION.",
                      "Complete the checklist in the app to release the final version."),
        "banner_fail": ("DRAFT — DID NOT PASS AI REVIEW.",
                        "See `9_paper_review.json` for the problems; do not submit this version."),
    },
    "Indonesian": {
        "abstract": "Abstrak", "keywords": "Kata kunci", "introduction": "1. Pendahuluan",
        "literature_review": "2. Tinjauan Pustaka", "methods": "3. Metode", "results": "4. Hasil",
        "discussion": "5. Pembahasan", "conclusion": "6. Simpulan", "references": "Daftar Pustaka",
        "author_text": "Teks dari penulis, belum diverifikasi oleh AI.", "todo_marker": "[PENULIS MELENGKAPI]",
        "todo_methods": "Rancangan, sumber data, sampel, variabel, prosedur, dan etika penelitian.",
        "todo_results": "Hasil analisis serta tabel atau gambar yang berasal dari data sebenarnya.",
        "pending": "Hasil: [menunggu analisis penulis]",
        "banner_ok": ("DRAF: LOLOS REVIU AI, MENUNGGU VERIFIKASI PENELITI.",
                      "Lengkapi daftar periksa di aplikasi untuk merilis versi final."),
        "banner_fail": ("DRAF: TIDAK LOLOS REVIU AI.",
                        "Lihat `9_paper_review.json` untuk daftar masalah; jangan kirim versi ini."),
    },
}


def labels(language):
    return LABELS.get(language, LABELS["English"])
