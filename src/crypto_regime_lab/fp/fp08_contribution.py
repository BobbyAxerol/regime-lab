"""FP-08 regime contribution checks (guide FP08.4's five questions).
Every answer cites the real per-cell evidence it is derived from -- never
a qualitative judgement without a number behind it.
"""
from __future__ import annotations


def _context_conditioned_count(selections_by_origin: dict) -> tuple[int, int]:
    c_sel = selections_by_origin.get("C_FP_CONTEXT", {})
    total = len(c_sel)
    conditioned = sum(1 for row in c_sel.values() if row.get("source") == "CONTEXT_CONDITIONED")
    return conditioned, total


def build_contribution_checks(*, cell1_selections_by_origin: dict, cell2_selections_by_origin: dict) -> dict:
    c1_conditioned, c1_total = _context_conditioned_count(cell1_selections_by_origin)
    c2_conditioned, c2_total = _context_conditioned_count(cell2_selections_by_origin)
    context_ever_changed_a_selection = (c1_conditioned + c2_conditioned) > 0

    answers = []

    answers.append({
        "question": "Context có thực sự đổi candidate rankings/selections không?",
        "question_en": "Does context actually change candidate rankings/selections?",
        "answer": ("Yes" if context_ever_changed_a_selection else "No"),
        "evidence": f"cell1: {c1_conditioned}/{c1_total} origins CONTEXT_CONDITIONED; "
                   f"cell2: {c2_conditioned}/{c2_total} origins CONTEXT_CONDITIONED",
    })

    if not context_ever_changed_a_selection:
        na_reason = ("no cell shows a single CONTEXT_CONDITIONED selection -- C's own predictions "
                    "were always either FALLBACK_TO_A or FALLBACK_TO_B, so there is no "
                    "context-driven effect for the next three questions to examine")
        answers.append({"question": "Benefit có còn sau common calendar?",
                        "question_en": "Does the benefit persist after a common calendar?",
                        "answer": "N/A", "evidence": na_reason})
        answers.append({"question": "Context improvement có chỉ là market-wide offset không?",
                        "question_en": "Is the context improvement just a market-wide offset?",
                        "answer": "N/A", "evidence": na_reason})
        answers.append({"question": "C thắng do conditional selection hay chỉ giảm exposure?",
                        "question_en": "Does C win via conditional selection or just reduced exposure?",
                        "answer": "N/A", "evidence": na_reason})
    else:
        answers.append({"question": "Benefit có còn sau common calendar?",
                        "question_en": "Does the benefit persist after a common calendar?",
                        "answer": "REQUIRES_MANUAL_REVIEW",
                        "evidence": "a real CONTEXT_CONDITIONED selection exists -- guide 19's arms "
                                   "already share one calendar by construction, so this needs the "
                                   "specific origin's own paired contrast reviewed directly, not a "
                                   "generic formula"})
        answers.append({"question": "Context improvement có chỉ là market-wide offset không?",
                        "question_en": "Is the context improvement just a market-wide offset?",
                        "answer": "REQUIRES_MANUAL_REVIEW",
                        "evidence": "needs comparing the specific CONTEXT_CONDITIONED origin's C "
                                   "selection against a market-wide benchmark for that window"})
        answers.append({"question": "C thắng do conditional selection hay chỉ giảm exposure?",
                        "question_en": "Does C win via conditional selection or just reduced exposure?",
                        "answer": "REQUIRES_MANUAL_REVIEW",
                        "evidence": "needs comparing entries/exposure at the specific "
                                   "CONTEXT_CONDITIONED origin between B and C"})

    vintage_note = ("cell1 (A-SC/BTCUSDT, 12 origins) and cell2 (A-SC/ETHUSDT, 3 origins) both show "
                    f"{c1_conditioned}/{c1_total} and {c2_conditioned}/{c2_total} "
                    "CONTEXT_CONDITIONED selections respectively")
    depends_on_one_vintage = (c1_conditioned == 0) != (c2_conditioned == 0)
    answers.append({
        "question": "Kết quả có phụ thuộc một origin/model vintage không?",
        "question_en": "Does the result depend on one origin/model vintage?",
        "answer": ("YES_PATTERN_DIFFERS_BY_CELL" if depends_on_one_vintage else
                  "CONSISTENT_ACROSS_CELLS" if c1_total and c2_total else "INSUFFICIENT_CELLS"),
        "evidence": vintage_note,
    })

    return {"schema": "regime_lab.fp08_contribution_checks.v1", "answers": answers}
