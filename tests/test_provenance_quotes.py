"""Every quote in the source topology must be a verbatim passage of the PDF (cells of a table row joined by “…”)."""

import re

from pypdf import PdfReader

from .conftest import PROJECT


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace(" ", " ").replace("’", "'")).strip()


def test_every_quote_is_in_the_pdf(source):
    pdf = PdfReader(str(PROJECT / "source" / "Cahier des Charges P&ID Consolidé.pdf"))
    text = _norm(" ".join(p.extract_text() for p in pdf.pages))
    quotes = []
    for o in source.objects().values():
        if o.provenance.quote:
            quotes.append((o.id, o.provenance.page, o.provenance.quote))
        for a in o.attributes.values():
            if a.provenance and a.provenance.quote:
                quotes.append((o.id, a.provenance.page, a.provenance.quote))
    for e in source.equipment:
        for n in e.nozzles:
            if n.size and n.size.provenance and n.size.provenance.quote:
                quotes.append((e.id, n.size.provenance.page, n.size.provenance.quote))
    for l in source.process_lines:
        for a in l.properties.values():
            if a.provenance and a.provenance.quote:
                quotes.append((l.id, a.provenance.page, a.provenance.quote))
    assert len(quotes) > 40
    bad = []
    for oid, page, q in quotes:
        parts = [_norm(x) for x in re.split(r"\s*(?:\.\.\.|…)\s*", q) if x.strip()]
        if not all(p in text for p in parts):
            bad.append((oid, q[:80]))
    assert not bad, bad[:5]


def test_page_numbers_match_the_pdf_page_that_contains_the_quote(source):
    pdf = PdfReader(str(PROJECT / "source" / "Cahier des Charges P&ID Consolidé.pdf"))
    pages = [_norm(p.extract_text()) for p in pdf.pages]
    wrong = []
    for oid, o in source.objects().items():
        q, pg = o.provenance.quote, o.provenance.page
        if not q or not pg:
            continue
        parts = [_norm(x) for x in re.split(r"\s*(?:\.\.\.|…)\s*", q) if x.strip()]
        if not all(p in pages[pg - 1] for p in parts):
            wrong.append((oid, pg))
    assert not wrong, wrong[:5]
