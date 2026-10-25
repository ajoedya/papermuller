"""
demo_data.py  -  PRETEND ANSWERS FOR PRACTICE
=============================================
Used only when DEMO_MODE=true. Nothing goes online, nothing costs money.

All papers here are FICTIONAL (their DOIs start with 10.0000/demo) so they
can never be mistaken for real references.

The demo is scripted to show you every quality gate in action:
  - one paper FAILS verification
  - draft 1 cites a paper that does not exist  -> citation gate catches it
  - draft 2 gets a low reviewer score           -> it is revised
  - draft 3 passes
"""

import json

_counter = {"draft": 0, "review": 0}

_PAPERS = [
    ("Road infrastructure and rural poverty: evidence from district panels", 2021,
     "A. Rahman, L. Chen", 140, "Using a fixed-effects panel of 400 districts, we find road density reduces poverty rates, mainly through market access."),
    ("Governance quality as a moderator of public investment returns", 2019,
     "M. Ortega, S. Lee", 210, "Cross-country regressions show public investment raises growth only where governance quality is high."),
    ("Fiscal transfers, local capacity and service delivery", 2020,
     "R. Putri, J. Smith", 95, "Difference-in-differences on decentralisation reform; transfers improve services only in high-capacity districts."),
    ("Corruption and the cost of infrastructure projects", 2018,
     "K. Novak", 300, "Audit data from 1,200 projects show cost overruns are larger in regions with weaker oversight."),
    ("Spatial spillovers of transport investment", 2022,
     "T. Wang, P. Garcia", 60, "Spatial econometric models reveal positive spillovers of road investment to neighbouring regions."),
    ("Measuring subnational governance: a review of indicators", 2023,
     "D. Hassan", 40, "Reviews 25 subnational governance indices and discusses their validity and comparability."),
    ("A retracted-style example with a wrong DOI", 2020,
     "X. Unknown", 10, "This record exists only to show what a failed verification looks like."),
]


def fake_search(keyword):
    papers = []
    for i, (title, year, authors, cites, abstract) in enumerate(_PAPERS, start=1):
        papers.append({"title": title, "year": year, "authors": authors,
                       "doi": f"10.0000/demo.{i}", "abstract": abstract, "cited_by": cites})
    return papers


def fake_verify(doi):
    if doi.endswith(".7"):
        return False, "DOI not found in Crossref (demo failure)"
    return True, "verified (demo)"


def fake_llm_answer(stage, prompt):
    import re
    if stage == "plan":
        _counter.update(draft=0, review=0)  # each new run starts the demo story again
        return json.dumps({
            "title": "Road Infrastructure, Governance Quality and Poverty Outcomes",
            "research_questions": [
                "How is road infrastructure associated with poverty outcomes?",
                "How does governance quality moderate these relationships?"],
            "keywords": ["road infrastructure poverty", "governance quality public investment",
                         "fiscal transfers service delivery", "transport spillovers"],
            "scope_note": "Infrastructure, governance and poverty; geography, population and timeframe are not yet specified.",
            "assumptions": ["Which geography and population should the actual study cover?"]})

    if stage == "screen":
        ids = re.findall(r"\[(P\d+)\]", prompt)
        return json.dumps({"include": ids, "excluded": {}})

    if stage == "matrix":
        matches = re.findall(r"Paper (P\d+):[^\n]*\nAbstract: ([^\n]+)", prompt)
        return json.dumps({"rows": [{"id": pid, "method": "As reported in the abstract",
                                     "main_finding": abstract,
                                     "evidence_quote": abstract,
                                     "limitation": "not stated",
                                     "relevance": "Relevant to research questions."} for pid, abstract in matches]})

    if stage == "outline":
        return json.dumps({"themes": [
            {"name": "Roads and poverty", "papers": ["P1", "P5"], "point": "Roads reduce poverty via market access."},
            {"name": "Governance conditions", "papers": ["P2", "P3", "P4"], "point": "Returns depend on governance."},
            {"name": "Measurement", "papers": ["P6"], "point": "Governance is hard to measure locally."}],
            "gap": "Governance as a moderator at district level is rarely tested."})

    if stage == "draft":
        _counter["draft"] += 1
        bad = " A recent study also confirms this [P99]." if _counter["draft"] == 1 else ""
        return (f"## Roads and poverty (demo round {_counter['draft']})\n\n"
                "Research on transport infrastructure generally finds that roads reduce poverty "
                f"by improving market access [P1; P5].{bad}\n\n## Governance conditions\n\n"
                "However, returns to public investment appear conditional on governance quality [P2], "
                "and weak oversight raises project costs [P3]. Evidence on fiscal transfers points the same way [P4].\n\n"
                "## Measurement\n\nMeasuring governance at the subnational level remains contested [P6].\n\n"
                "**Research gap:** few studies test governance as a moderator at district level [P2; P6].")

    if stage == "evidence_audit":
        abstracts = dict(re.findall(r"(P\d+):[^\n]*\nABSTRACT: (?:\[PAGE ABSTRACT\] )?([^\n]+)", prompt))
        results = []
        for number, cites in re.findall(r"PARAGRAPH (\d+) \(cites ([^)]+)\):", prompt):
            ids = [pid.strip() for pid in cites.split(",") if pid.strip()]
            results.append({"paragraph": int(number), "status": "supported",
                            "evidence": [{"id": pid, "quote": abstracts.get(pid, "")}
                                         for pid in ids],
                            "reason": "DEMO ONLY: scripted check, not genuine semantic evaluation"})
        return json.dumps({"items": results})

    if stage == 'redteam':
        return json.dumps({'findings': [], 'limitations': ['Demo menggunakan literatur fiktif'],
                           'summary': 'DEMO ONLY: not a genuine adversarial review'})

    if stage == "review":
        _counter["review"] += 1
        level = {1: 6, 2: 7, 3: 8}.get(_counter["review"], 8)
        scores = {k: level for k in ["synthesis", "research_gap", "coverage", "evidence_use", "clarity", "scope_fidelity"]}
        scores["clarity"] = min(10, level + 1)
        return json.dumps({"scores": scores, "strengths": ["Clear thematic structure"],
                           "fixes": [] if level >= 8 else ["Compare the methods of P2 and P5 explicitly",
                                                           "Link the research gap to research question 2"]})
    return "OK"
