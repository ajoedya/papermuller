"""A manuscript scaffold that does not invent methods, observations or results."""
import json
from datetime import datetime, timezone


def compile_manuscript(plan, draft, matrix, audit):
    author_methods = (plan.get('author_methods') or '').strip()
    author_results = (plan.get('author_results') or '').strip()
    questions = '\n'.join(f'- {q}' for q in plan['research_questions'])
    methods = (f'**Teks yang diberikan peneliti (belum diverifikasi):**\n\n{author_methods}' if author_methods
               else '> **[PENELITI PERLU MENGISI]** Desain, sumber data, sampel, variabel, prosedur, serta etika penelitian.')
    results = (f'**Teks yang diberikan peneliti (belum diverifikasi):**\n\n{author_results}' if author_results
               else '> **[PENELITI PERLU MENGISI]** Hasil analisis dan tabel/figur yang benar-benar berasal dari data.')
    status = 'LULUS audit otomatis dan AI; menunggu verifikasi manusia' if audit.get('passed') else 'BELUM LOLOS audit bukti'
    txt = f'''# {plan['title']}

> **MANUSKRIP KERJA — BUKAN ARTIKEL SIAP SUBMIT.** Tinjauan pustaka: {status}.
> Bagian yang belum didukung data tidak dibuat secara otomatis. Teks metode/hasil dari peneliti tidak diaudit oleh AI maupun divalidasi secara independen.

## Abstract

> **[PENELITI PERLU MENGISI SETELAH ANALISIS SELESAI]** Tujuan, metode, hasil utama, implikasi, keterbatasan.

## 1. Introduction

**Topik:** {plan['original_topic'] or plan['title']}

**Pertanyaan penelitian:**

{questions}

**Ruang lingkup yang disetujui:** {plan['scope_note']}

> **[PENELITI PERLU MENYUSUN]** Latar belakang, urgensi, kontribusi, dan signifikansi masalah dengan referensi terverifikasi.

## 2. Literature Review

{draft}

## 3. Methods

{methods}

## 4. Results

{results}

## 5. Discussion

> **[PENELITI PERLU MENYUSUN]** Interpretasikan hasil penelitian yang sesungguhnya, bandingkan dengan sumber terverifikasi, dan periksa klaim serta ketidakpastian. Jangan mengarang hasil.

## 6. Conclusion

> **[PENELITI PERLU MENYUSUN]** Kesimpulan berdasarkan hasil nyata, keterbatasan, dan agenda penelitian lanjutan.

## References

'''
    for r in matrix:
        txt += f"- [{r['id']}] {r['authors']} ({r['year']}). {r['title']}. https://doi.org/{r['doi']}\n"
    return txt, {'methods': 'author_supplied_unverified' if author_methods else 'missing',
                 'results': 'author_supplied_unverified' if author_results else 'missing',
                 'abstract': 'pending', 'introduction': 'pending',
                 'discussion': 'pending', 'conclusion': 'pending',
                 'literature_review': 'audit_passed_pending_human' if audit.get('passed') else 'audit_failed'}


def verification_record(matrix):
    return {'papers': {r['id']: {'read_full_text': False, 'claims_checked': False} for r in matrix},
            'checks': {'methods_checked': False, 'results_checked': False,
                       'journal_policy_checked': False, 'ai_disclosure_checked': False},
            'notes': '', 'saved_at': None}


def normalize_verification(update, matrix):
    identifiers = {str(r['id']) for r in matrix}
    if not isinstance(update, dict):
        raise ValueError('Format verifikasi tidak valid.')
    record = verification_record(matrix)
    given = update.get('papers') or {}
    checks = update.get('checks') or {}
    if not isinstance(given, dict) or set(given) - identifiers or not isinstance(checks, dict):
        raise ValueError('ID sumber atau format verifikasi tidak valid.')
    for pid in identifiers:
        state = given.get(pid) or {}
        if not isinstance(state, dict):
            raise ValueError('Status sumber tidak valid.')
        for key in record['papers'][pid]:
            record['papers'][pid][key] = state.get(key) is True
    for key in record['checks']:
        record['checks'][key] = checks.get(key) is True
    record['notes'] = str(update.get('notes') or '')[:2000]
    record['saved_at'] = datetime.now(timezone.utc).isoformat()
    return record


def verified_count(record):
    done = sum(sum(bool(x) for x in flags.values()) for flags in record['papers'].values())
    done += sum(bool(x) for x in record['checks'].values())
    total = sum(len(flags) for flags in record['papers'].values()) + len(record['checks'])
    return {'done': done, 'total': total, 'all_checked': bool(total) and done == total}


def disclosure_template(settings, matrix):
    model = settings.get('MODEL', '(model not recorded)')
    review_model = settings.get('REVIEW_MODEL') or model
    return ("# Draft AI-assistance disclosure (edit to match journal requirements)\n\n"
            "**This is a disclosure template, not an automatically validated compliance statement.**\n\n"
            "During preparation of this manuscript, the author used an AI-assisted local research "
            f"workflow with the writing model `{model}` and review model `{review_model}` "
            "to help identify literature, organize themes, draft a literature review, and flag potential "
            "citation and evidence issues. The author is responsible for reading the cited works, "
            "verifying all claims, reviewing the entire manuscript, and following the journal's disclosure policy.\n\n"
            f"Sources selected in the research matrix: {len(matrix)}. "
            "The system's validation results are provisional and do not constitute scientific peer review.\n")
