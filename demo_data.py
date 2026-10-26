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
  - full paper 1 invents a result               -> final review gate catches it
  - full paper 2 passes the gate
"""

import json

_counter = {"draft": 0, "review": 0, "paper": 0, "paper_review": 0}

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
        _counter.update(draft=0, review=0, paper=0, paper_review=0)  # each new run starts the demo story again
        return json.dumps({
            "title": "Road Infrastructure, Governance Quality and Poverty Outcomes",
            "research_questions": [
                "How is road infrastructure associated with poverty outcomes?",
                "How does governance quality moderate these relationships?"],
            "keywords": ["road infrastructure poverty", "governance quality public investment",
                         "fiscal transfers service delivery", "transport spillovers"],
            "scope_note": "Infrastructure, governance and poverty; geography, population and timeframe are not yet specified.",
            "assumptions": ["Which geography and population should the actual study cover?"]})

    if stage == "brainstorm":
        first = [
            ("How does road density relate to rural poverty rates across districts?",
             "Infrastructure as the main explanatory variable", ["road infrastructure poverty", "rural roads"]),
            ("Does governance quality change the poverty returns to public road investment?",
             "Governance as a moderator", ["governance quality public investment", "moderation"]),
            ("How do fiscal transfers and local capacity shape the delivery of infrastructure services?",
             "Fiscal transfers and administrative capacity", ["fiscal transfers service delivery", "local capacity"]),
            ("What do weak audit and oversight arrangements do to infrastructure project costs?",
             "Oversight and cost overruns", ["infrastructure cost overruns", "audit oversight"]),
            ("Do road investments spill over to the poverty outcomes of neighbouring regions?",
             "Spatial spillovers", ["transport spillovers", "spatial econometrics"]),
        ]
        second = [
            ("How reliable are subnational governance indicators when used in poverty research?",
             "Measurement validity", ["subnational governance indicators", "measurement"]),
            ("Which road maintenance arrangements keep the poverty benefits of roads over time?",
             "Maintenance rather than construction", ["road maintenance poverty", "infrastructure durability"]),
            ("How does market access mediate the link between rural roads and household income?",
             "Mechanism: market access", ["market access rural roads", "household income"]),
            ("Do decentralisation reforms change who benefits from road investment?",
             "Decentralisation and distribution", ["decentralisation infrastructure", "distributional effects"]),
            ("How do poverty effects of road projects differ between new construction and upgrading?",
             "Project type comparison", ["road upgrading poverty", "project type"]),
        ]
        chosen = second if first[0][0] in prompt else first
        return json.dumps({"suggestions": [
            {"topic": topic, "angle": angle, "why": "DEMO ONLY: scripted suggestion, not generated by an AI",
             "keywords": keywords} for topic, angle, keywords in chosen]})

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
        return json.dumps({'findings': [], 'limitations': ['Demo uses fictional literature'],
                           'summary': 'DEMO ONLY: not a genuine adversarial review'})

    if stage == "review":
        _counter["review"] += 1
        level = {1: 6, 2: 7, 3: 8}.get(_counter["review"], 8)
        scores = {k: level for k in ["synthesis", "research_gap", "coverage", "evidence_use", "clarity", "scope_fidelity"]}
        scores["clarity"] = min(10, level + 1)
        return json.dumps({"scores": scores, "strengths": ["Clear thematic structure"],
                           "fixes": [] if level >= 8 else ["Compare the methods of P2 and P5 explicitly",
                                                           "Link the research gap to research question 2"]})
    if stage == "paper_draft":
        _counter["paper"] += 1
        invented = ("Using district data we find that roads cut poverty by 12 percent. "
                    if _counter["paper"] == 1 else "")
        abstract = (
            "Public investment in roads is widely expected to reduce poverty, yet the size of that effect "
            "appears to depend on the institutions that plan, procure and maintain the infrastructure. "
            "This article reviews fictional demonstration studies on road infrastructure, governance quality "
            "and poverty outcomes in order to frame a study of governance as a moderator. The literature "
            "suggests that roads improve market access and that these gains spill over to neighbouring "
            "regions, while the returns to public investment are weaker where oversight is poor and "
            "project costs overrun. Evidence on fiscal transfers points in the same direction, and the "
            "measurement of subnational governance remains contested. " + invented +
            "The study is designed to test whether governance quality conditions the association between "
            "road investment and poverty at district level, a relationship that few studies have examined "
            "directly. Results: [pending author analysis]")
        return json.dumps({
            "title": "Road Infrastructure, Governance Quality and Poverty Outcomes: A Review and Research Design",
            "abstract": abstract,
            "keywords": ["road infrastructure", "governance quality", "poverty", "public investment", "demo"],
            "introduction": (
                "Transport infrastructure is a central instrument of development policy, and road density is "
                "associated with lower poverty through improved market access [P1]. Investment does not pay "
                "off equally everywhere, however: returns appear conditional on governance quality [P2].\n\n"
                "This DEMO article asks how road infrastructure relates to poverty outcomes and how governance "
                "quality moderates that relationship. Its contribution is to connect the infrastructure and "
                "governance literatures at district level, where measurement is hardest [P6]."),
            "discussion": (
                "Read together, the studies suggest that the poverty effects of roads are real but conditional. "
                "Spillovers to neighbouring regions [P5] imply that district-level estimates may understate "
                "total effects, while cost overruns under weak oversight [P3] imply that governance shapes how "
                "much road is built per unit of spending.\n\n"
                "Because results are pending, this discussion frames what the planned analysis can test rather "
                "than what it shows. If governance moderates returns as [P2] and [P4] suggest, the association "
                "between road investment and poverty should be stronger in high-capacity districts."),
            "conclusion": (
                "The demonstration literature points to governance as a plausible moderator of the poverty "
                "returns to road investment [P2; P4]. The planned study is expected to contribute a direct "
                "district-level test of that moderation once the author's analysis is complete."),
        })

    if stage == "paper_review":
        _counter["paper_review"] += 1
        first = _counter["paper_review"] == 1
        scores = {"abstract_consistency": 7 if first else 8, "coherence": 8, "claim_support": 8,
                  "no_fabrication": 3 if first else 9, "academic_style": 8, "scope_fidelity": 8}
        return json.dumps({"scores": scores, "strengths": ["DEMO ONLY: scripted review"],
                           "fixes": ["Abstract: remove the invented 12 percent poverty result; no results exist yet"]
                                    if first else []})
    return "OK"
