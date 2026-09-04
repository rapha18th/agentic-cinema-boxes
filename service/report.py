"""Assemble a project's full research into a typeset PDF dossier.

Same restraint as the app: near-white ground, hairline rules, one accent, the
monolith on the cover. Text-first — every claim carries its citation.
"""

from __future__ import annotations

import io
import time
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

INK = colors.HexColor("#1c1a15")
MUTED = colors.HexColor("#5f5a4e")
FAINT = colors.HexColor("#8a8272")
LINE = colors.HexColor("#c7c1ad")
ACCENT = colors.HexColor("#9c6b1a")

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm

_TITLE = ParagraphStyle("title", fontName="Helvetica", fontSize=22, leading=26,
                        textColor=INK, spaceAfter=2)
_KICKER = ParagraphStyle("kicker", fontName="Helvetica", fontSize=8, leading=12,
                         textColor=FAINT, spaceAfter=16)
_PREMISE = ParagraphStyle("premise", fontName="Helvetica", fontSize=13, leading=18,
                          textColor=INK, spaceBefore=6, spaceAfter=14)
_H = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=11, leading=14,
                    textColor=MUTED, spaceBefore=18, spaceAfter=4)
_SUB = ParagraphStyle("sub", fontName="Helvetica-Bold", fontSize=9.5, leading=13,
                      textColor=ACCENT, spaceBefore=10, spaceAfter=2)
_BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=9, leading=12.5,
                       textColor=INK, alignment=TA_LEFT, spaceAfter=3)
_DIM = ParagraphStyle("dim", fontName="Helvetica", fontSize=8, leading=11,
                      textColor=MUTED, spaceAfter=2)
_META = ParagraphStyle("meta", fontName="Helvetica", fontSize=7.5, leading=10,
                       textColor=FAINT, spaceAfter=8)


def _pct(x) -> str:
    try:
        return f"{round(float(x or 0) * 100)}%"
    except (TypeError, ValueError):
        return "0%"


def _p(text, style) -> Paragraph:
    return Paragraph(escape(str(text if text is not None else "")), style)


def _rule():
    return HRFlowable(width="100%", thickness=0.5, color=LINE,
                      spaceBefore=4, spaceAfter=4)


class Monolith(Flowable):
    """A 4:9 black slab with a lit top edge — the cover mark."""

    def __init__(self, w: float = 24 * mm):
        super().__init__()
        self.width = w
        self.height = w * 9 / 4

    def wrap(self, *_):
        return (self.width, self.height)

    def draw(self):
        c = self.canv
        c.setFillColor(colors.black)
        c.rect(0, 0, self.width, self.height, stroke=0, fill=1)
        c.setStrokeColor(colors.HexColor("#8a8272"))
        c.setLineWidth(0.8)
        c.line(0, self.height, self.width, self.height)


def _footer(canv, doc):
    canv.saveState()
    canv.setFont("Helvetica", 7)
    canv.setFillColor(FAINT)
    canv.drawString(MARGIN, 12 * mm, "Assembled by THE BOXES  ·  Agentic Cinema")
    canv.drawRightString(PAGE_W - MARGIN, 12 * mm, str(doc.page))
    canv.restoreState()


def build_report_pdf(*, project: dict, boxes: list[dict], evidence: list[dict],
                     verdicts: list[dict], runs: list[dict], reel: list[dict]) -> bytes:
    premise = (project.get("premise") or "").strip()
    story: list = []

    # ---- cover -------------------------------------------------------------
    story += [Spacer(1, 26 * mm), Monolith(), Spacer(1, 12 * mm)]
    story.append(_p("THE BOXES", _TITLE))
    story.append(_p("Research dossier", _KICKER))
    story.append(_p(premise or "Untitled project", _PREMISE))
    story.append(_rule())

    domains = {e.get("source_domain") for e in evidence if e.get("source_domain")}
    sources = {e.get("url") for e in evidence if e.get("url")}
    conflicts = [v for v in verdicts if v.get("relation") == "contradicts"]
    facts = [
        ("Depth", str(project.get("depth", "scout")).title()),
        ("Research confidence", _pct(project.get("confidence"))),
        ("Coverage", _pct(project.get("coverage"))),
        ("Status", str(project.get("status", "—"))),
        ("Boxes", str(len(boxes))),
        ("Evidence fragments", str(len(evidence))),
        ("Distinct sources", str(len(sources))),
        ("Distinct domains", str(len(domains))),
        ("Contradictions", f"{len(conflicts)} conflict, {len(verdicts) - len(conflicts)} context"),
        ("Research passes", str(len(runs))),
        ("Generated", time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())),
        ("Project id", str(project.get("id", ""))),
    ]
    t = Table([[_p(k, _DIM), _p(v, _BODY)] for k, v in facts],
              colWidths=[46 * mm, PAGE_W - 2 * MARGIN - 46 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, LINE),
    ]))
    story.append(t)
    story.append(PageBreak())

    # ---- the plan --------------------------------------------------------
    story.append(_p("THE PLAN", _H))
    story.append(_rule())
    by_id = {b.get("id"): b for b in boxes}
    for b in sorted(boxes, key=lambda x: -(x.get("score") or 0)):
        tag = "  (emergent)" if b.get("emergent") else ""
        story.append(_p((b.get("name") or "UNNAMED") + tag, _SUB))
        if b.get("description"):
            story.append(_p(b["description"], _BODY))
        if b.get("rationale"):
            story.append(_p(f"Why: {b['rationale']}", _DIM))
        story.append(_p(
            f"coverage {_pct(b.get('score'))}  ·  {b.get('evidence_count', 0)} items"
            f"  ·  {b.get('distinct_domains', 0)} domains", _META))
    if not boxes:
        story.append(_p("No plan drawn yet.", _DIM))

    # ---- evidence by box ----------------------------------------------------
    story.append(PageBreak())
    story.append(_p("EVIDENCE", _H))
    story.append(_rule())
    grouped: dict[str, list[dict]] = {}
    for e in evidence:
        grouped.setdefault(e.get("objective_id") or "_unfiled", []).append(e)

    order = [b.get("id") for b in sorted(boxes, key=lambda x: -(x.get("score") or 0))]
    order += [k for k in grouped if k not in order]
    for key in order:
        items = grouped.get(key)
        if not items:
            continue
        name = by_id.get(key, {}).get("name") or ("UNFILED" if key == "_unfiled" else key)
        story.append(_p(f"{name}  ({len(items)})", _SUB))
        for e in items:
            cite = " · ".join(x for x in [
                e.get("title") or e.get("source_domain") or e.get("url"),
                e.get("publish_date"),
            ] if x)
            own = "  ·  your upload" if e.get("source") == "director" else ""
            story.append(_p(f"• {cite}{own}", _BODY))
            snippet = (e.get("text") or "").strip().replace("\n", " ")
            if snippet:
                story.append(_p(snippet[:320] + ("…" if len(snippet) > 320 else ""), _DIM))
            tail = "  ·  ".join(x for x in [
                e.get("modality", "text"),
                e.get("url"),
                e.get("license_note"),
            ] if x)
            if tail:
                story.append(_p(tail, _META))
    if not evidence:
        story.append(_p("No evidence indexed yet.", _DIM))

    # ---- contradictions --------------------------------------------------
    story.append(PageBreak())
    story.append(_p("CONTRADICTIONS", _H))
    story.append(_rule())
    for v in verdicts:
        story.append(_p((v.get("relation") or "").upper(), _SUB))
        if v.get("explanation"):
            story.append(_p(v["explanation"], _BODY))
        story.append(_p(f"A  —  {v.get('a_cite', '')}", _DIM))
        story.append(_p(f"B  —  {v.get('b_cite', '')}", _DIM))
    if not verdicts:
        story.append(_p("None found.", _DIM))

    # ---- ledger ----------------------------------------------------------
    story.append(_p("RESEARCH LEDGER", _H))
    story.append(_rule())
    for r in runs:
        story.append(_p(f"RUN {str(r.get('run', 0)).zfill(3)}", _SUB))
        story.append(_p(
            f"{r.get('sources_examined', 0)} sources  ·  {r.get('evidence_indexed', 0)} fragments"
            f"  ·  {r.get('sources_extracted', 0)} via Extract", _DIM))
        story.append(_p(
            f"coverage {_pct(r.get('coverage_before'))} → {_pct(r.get('coverage_after'))}"
            f"   confidence {_pct(r.get('confidence_before'))} → {_pct(r.get('confidence_after'))}",
            _DIM))
        if r.get("new_boxes"):
            story.append(_p("opened: " + ", ".join(r["new_boxes"]), _DIM))
        for s in r.get("searches", []) or []:
            qs = "; ".join(s.get("queries", []))
            story.append(_p(f"{s.get('objective', '')} — {qs}", _META))
        if r.get("next_action"):
            story.append(_p(f"→ {r['next_action']}", _META))
    if not runs:
        story.append(_p("No research run yet.", _DIM))

    # ---- reference reel --------------------------------------------------
    story.append(PageBreak())
    story.append(_p("REFERENCE REEL", _H))
    story.append(_rule())
    for b in reel:
        story.append(_p(f"{b.get('t', '00:00')}   {b.get('title', '')}", _SUB))
        if b.get("note"):
            story.append(_p(b["note"], _BODY))
        for s in b.get("sources", []) or []:
            line = " — ".join(x for x in [s.get("cite"), s.get("url")] if x)
            if line:
                story.append(_p(line, _META))
    if not reel:
        story.append(_p("No reel cut yet.", _DIM))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm,
        leftMargin=MARGIN, rightMargin=MARGIN,
        title=f"THE BOXES — {premise[:60]}" if premise else "THE BOXES",
        author="THE BOXES",
    )
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
