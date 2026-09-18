#!/usr/bin/env python
"""Give every phase report the glossary CLAUDE.md rule 10 requires.

Idempotent: it replaces an existing glossary section rather than stacking a new
one, so re-running after a definition changes updates the reports in place. It
does not touch any other part of a report -- LAB-01..03 were written by hand,
before the generator discipline, and their content is evidence.
"""

from __future__ import annotations

import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB_ROOT / "src"))

from crypto_regime_lab.evidence import glossary as G  # noqa: E402

HEADING = "## Glossary — what each term means and where it applies"
# LAB-04's report is generated and inserts its own glossary at the top.
HANDWRITTEN = {"LAB-01": "lab01_report.md", "LAB-02": "lab02_report.md",
               "LAB-03": "lab03_report.md"}
# LAB-04 and LAB-05 reports are generated and insert their own glossary.


def _strip_existing(text: str) -> str:
    if HEADING not in text:
        return text
    start = text.index(HEADING)
    rest = text[start + len(HEADING):]
    nxt = rest.find("\n## ")
    return text[:start] + (rest[nxt + 1:] if nxt != -1 else "")


def main() -> int:
    changed = []
    for phase, name in sorted(HANDWRITTEN.items()):
        path = LAB_ROOT / "reports" / name
        if not path.is_file():
            print(f"   {name}: MISSING")
            continue
        text = _strip_existing(path.read_text()).rstrip() + "\n\n"
        section = "\n".join(G.render(G.BY_PHASE[phase]))
        path.write_text(text + section)
        changed.append((name, len(G.BY_PHASE[phase])))
        print(f"   {name}: glossary with {len(G.BY_PHASE[phase])} terms")
    print(f"updated {len(changed)} reports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
