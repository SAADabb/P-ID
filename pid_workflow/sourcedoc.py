"""The specification as text, page by page, and the check that every quote in a topology is verbatim.

Supports PDF (pypdf text layer), plain text and Markdown (pages separated by form feeds or
``--- page N ---`` markers; otherwise a single page).  A scanned PDF without a text layer yields
empty pages: OCR it first (e.g. ``ocrmypdf``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SPLIT = re.compile(r"\s*(?:\.\.\.|…)\s*")


def norm(s: str) -> str:
    s = (s.replace(" ", " ").replace(" ", " ").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
         .replace("ﬁ", "fi").replace("ﬂ", "fl").replace("‐", "-").replace("‑", "-"))
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class SourceDocument:
    path: Path
    pages: list[str]

    @classmethod
    def load(cls, path: str | Path) -> SourceDocument:
        path = Path(path)
        if path.suffix.lower() == ".pdf":
            from pypdf import PdfReader

            pages = [p.extract_text() or "" for p in PdfReader(str(path)).pages]
        else:
            raw = path.read_text(encoding="utf-8")
            parts = re.split(r"\f|^-{3,}\s*page\s+\d+\s*-{3,}\s*$", raw, flags=re.I | re.M)
            pages = [p for p in parts if p.strip()] or [raw]
        return cls(path, pages)

    @property
    def normalized(self) -> list[str]:
        return [norm(p) for p in self.pages]

    def has_text(self) -> bool:
        return sum(len(p.strip()) for p in self.pages) > 200

    def pages_with(self, quote: str) -> list[int]:
        """1-based pages that contain every fragment of the quote (fragments joined by ' … ')."""
        parts = [norm(x) for x in _SPLIT.split(quote) if x.strip()]
        return [i for i, p in enumerate(self.normalized, 1) if all(x in p for x in parts)]

    def write_pages(self, out_dir: str | Path) -> list[Path]:
        """One text file per page, for reading by the agent (source/pages/page_001.txt ...)."""
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        files = []
        for i, p in enumerate(self.pages, 1):
            f = out_dir / f"page_{i:03d}.txt"
            f.write_text(p, encoding="utf-8")
            files.append(f)
        return files


def quotes_of(topo: Any) -> list[tuple[str, int | None, str]]:
    """(object id, page, quote) for every quoted provenance in a topology."""
    out: list[tuple[str, int | None, str]] = []

    def add(oid: str, prov: Any) -> None:
        if prov is not None and getattr(prov, "quote", None):
            out.append((oid, prov.page, prov.quote))

    for oid, o in topo.objects().items():
        add(oid, o.provenance)
        for k, a in o.attributes.items():
            add(f"{oid}.{k}", a.provenance)
    for e in topo.equipment:
        for n in e.nozzles:
            if n.size is not None:
                add(f"{e.id}:{n.name}", n.size.provenance)
    for ln in topo.process_lines:
        for k, a in ln.properties.items():
            add(f"{ln.id}.{k}", a.provenance)
    for b in topo.metadata.engineering_basis:
        p = b.get("provenance") or {}
        if p.get("quote"):
            out.append(("metadata.engineering_basis", p.get("page"), p["quote"]))
    return out


def check_quotes(topo: Any, doc: SourceDocument) -> list[tuple[str, str]]:
    """Problems as (object id, message): quote not in the document, or on another page than stated."""
    bad: list[tuple[str, str]] = []
    for oid, page, q in quotes_of(topo):
        found = doc.pages_with(q)
        if not found:
            bad.append((oid, f"quote not found verbatim in {doc.path.name}: “{q[:90]}”"))
        elif page is not None and page not in found:
            bad.append((oid, f"quote is on page {found[0]}, not page {page}: “{q[:60]}”"))
    return bad
