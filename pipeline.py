"""Stable, honest UI descriptions for the local research pipeline.

Stages report actual transitions; percentage, cost and tokens are intentionally
not fabricated when an upstream provider does not supply them.
"""

STEPS = [
    {"id": 1, "name": "Setup Riset", "summary": "Rencana, pertanyaan dan persetujuan ruang lingkup", "engine": "Human + LLM", "input": "Topik peneliti", "output": "Rencana riset yang disetujui", "role": "planner"},
    {"id": 2, "name": "Discovery Literatur", "summary": "Pencarian artikel dari OpenAlex", "engine": "OpenAlex", "input": "Kata kunci dan tahun", "output": "Kandidat artikel", "role": "retriever"},
    {"id": 3, "name": "Verifikasi & PDF", "summary": "Validasi DOI Crossref dan pencocokan pustaka PDF", "engine": "Crossref · PDF parser", "input": "Kandidat artikel dan PDF lokal", "output": "Artikel terverifikasi", "role": "parser"},
    {"id": 4, "name": "Screening", "summary": "Penyaringan relevansi terhadap pertanyaan riset", "engine": "LLM + rules", "input": "Artikel terverifikasi", "output": "Artikel terpilih", "role": "screen"},
    {"id": 5, "name": "Ekstraksi Bukti", "summary": "Matriks bukti, kutipan dan halaman sumber", "engine": "Evidence model", "input": "PDF / abstrak terpilih", "output": "Matriks dengan provenance", "role": "evidence"},
    {"id": 6, "name": "Sintesis Literatur", "summary": "Tema dan research gap dari matriks", "engine": "Writer model", "input": "Matriks literatur", "output": "Outline tematik", "role": "writer"},
    {"id": 7, "name": "Draft Manuskrip", "summary": "Draf dan iterasi revisi tinjauan pustaka", "engine": "Writer model", "input": "Outline dan bukti", "output": "Draf berbasis sitasi", "role": "writer"},
    {"id": 8, "name": "Audit Sitasi & Klaim", "summary": "Pemeriksaan sitasi dan dukungan bukti", "engine": "Verifier + rules", "input": "Draf dan sumber terverifikasi", "output": "Laporan audit klaim", "role": "verifier"},
    {"id": 9, "name": "Adversarial Review", "summary": "Penilaian rubrik, kritik skeptis, revisi bila perlu", "engine": "Reviewer model", "input": "Draf dan audit bukti", "output": "Penilaian dan temuan risiko", "role": "reviewer"},
    {"id": 10, "name": "Ekspor & Verifikasi", "summary": "Manuskrip kerja, ledger, checklist verifikasi", "engine": "Python", "input": "Draf terpilih dan audit", "output": "Artefak lokal untuk ditinjau peneliti", "role": "system"},
]

ROLE_KEYS = {"planner": "MODEL", "retriever": None, "parser": None,
             "screen": "MODEL", "evidence": "EVIDENCE_MODEL", "writer": "WRITER_MODEL",
             "verifier": "VERIFIER_MODEL", "reviewer": "REVIEW_MODEL", "system": None}


def model_for_role(role, settings):
    if settings.get("DEMO_MODE") and ROLE_KEYS.get(role):
        return "Simulator demo (offline)"
    key = ROLE_KEYS.get(role)
    if not key:
        return {"retriever": "OpenAlex API", "parser": "Crossref + pypdf", "system": "Python local"}.get(role, "Rules engine")
    return settings.get(key) or settings.get("MODEL", "openrouter/auto")


def describe(settings):
    return [dict(step, model=model_for_role(step["role"], settings)) for step in STEPS]
