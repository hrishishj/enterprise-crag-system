"""Render the synthetic eval corpus (evals/corpus.py) to PDFs under sample_data/.

    python scripts/make_sample_docs.py [output_dir]

Requires reportlab (dev extra). Page breaks follow the corpus exactly, so gold page numbers stay valid.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evals.corpus import CORPUS


def render(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, pages in CORPUS.items():
        path = out_dir / name
        c = canvas.Canvas(str(path), pagesize=A4)
        for paragraphs in pages:
            y = 780
            for para in paragraphs:
                for line in textwrap.wrap(para, 85):
                    c.drawString(60, y, line)
                    y -= 16
                y -= 10
            c.showPage()
        c.save()
        written.append(path)
    return written


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "sample_data"
    for p in render(target):
        print(p)
