"""A manuscript scaffold that does not invent methods, observations or results."""
import json
from datetime import datetime, timezone


def compile_manuscript(plan, draft, matrix, audit):
    author_methods = (plan.get('author_methods') or '').strip()
    author_results = (plan.get('author_results') or '').strip()
    questions = '\n'.join(f'- {q}' for q in plan['research_questions'])
    methods = (f'**Author-supplied text (not verified):**\n\n{author_methods}' if author_methods
               else '> **[AUTHOR TO COMPLETE]** Design, data sources, sample, variables, procedures, and research ethics.')
    results = (f'**Author-supplied text (not verified):**\n\n{author_results}' if author_results
               else '> **[AUTHOR TO COMPLETE]** Analysis results and tables or figures derived from actual data.')
    status = 'Automated and AI evidence checks passed; awaiting researcher verification' if audit.get('passed') else 'Evidence checks have not passed'
    txt = f'''# {plan['title']}

> **WORKING MANUSCRIPT — REQUIRES AUTHOR REVIEW AND COMPLETION.** Literature review: {status}.
> Sections without supporting data are left unfilled. Author-supplied methods and results have not been audited by AI or independently validated.

## Abstract

> **[AUTHOR TO COMPLETE AFTER ANALYSIS]** Objectives, methods, key findings, implications, and limitations.

## 1. Introduction

**Topic:** {plan['original_topic'] or plan['title']}

**Research questions:**

{questions}

**Approved scope:** {plan['scope_note']}

> **[AUTHOR TO WRITE]** Background, motivation, contribution, and significance, supported by checked references.

## 2. Literature Review

{draft}

## 3. Methods

{methods}

## 4. Results

{results}

## 5. Discussion

> **[AUTHOR TO WRITE]** Interpret actual findings, compare them with checked sources, and assess claims and uncertainty. Do not invent results.

## 6. Conclusion

> **[AUTHOR TO WRITE]** Conclusions based on actual results, limitations, and directions for further research.

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
        raise ValueError('Invalid review record format.')
    record = verification_record(matrix)
    given = update.get('papers') or {}
    checks = update.get('checks') or {}
    if not isinstance(given, dict) or set(given) - identifiers or not isinstance(checks, dict):
        raise ValueError('Invalid source ID or review record format.')
    for pid in identifiers:
        state = given.get(pid) or {}
        if not isinstance(state, dict):
            raise ValueError('Invalid source review status.')
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
    from llm import model_for_stage
    model = model_for_stage('draft', settings) if settings.get('MODEL') else '(model not recorded)'
    review_model = model_for_stage('review', settings) if settings.get('MODEL') else model
    roles = [('plan', 'planning'), ('screen', 'screening'), ('matrix', 'evidence extraction'),
             ('outline', 'synthesis'), ('evidence_audit', 'claim audit'), ('redteam', 'red-team review')]
    stage_models = "".join(f"- {label}: `{model_for_stage(stage, settings)}`\n" for stage, label in roles) \
        if settings.get('MODEL') else ""
    return ("# Draft AI-assistance disclosure (edit to match journal requirements)\n\n"
            "**This is a disclosure template, not an automatically validated compliance statement.**\n\n"
            "During preparation of this manuscript, the author used an AI-assisted local research "
            f"workflow with the writing model `{model}` and review model `{review_model}` "
            "to help identify literature, organize themes, draft a literature review, and flag potential "
            "citation and evidence issues. The author is responsible for reading the cited works, "
            "verifying all claims, reviewing the entire manuscript, and following the journal's disclosure policy.\n\n"
            f"Sources selected in the research matrix: {len(matrix)}. "
            "The system's validation results are provisional and do not constitute scientific peer review.\n"
            + (f"\nModels configured for other stages:\n{stage_models}" if stage_models else ""))
