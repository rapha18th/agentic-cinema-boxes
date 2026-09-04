"""Assemble a project's full research into a typeset PDF dossier.

Same restraint as the app: near-white ground, hairline rules, one accent, the
monolith on the cover. The dossier is written for a human who has never seen
the project: every box opens with a plain-prose summary before its sources,
so the report stands on its own. Every claim still carries a citation.
"""

from __future__ import annotations

import io
import time
from xml.sax.saxutils import escape

import httpx
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Flowable,
    HRFlowable,
    Image as RLImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from boxes import synthesis
from boxes.ontology import DEPARTMENTS

_DEPT_LABEL = {
    "script": "Script", "casting": "Casting", "costume": "Costume",
    "art_direction": "Art direction", "sound": "Sound",
    "cinematography": "Cinematography", "locations": "Locations",
}
_VISUAL_DEPTS = {"costume", "art_direction"}

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
                          textColor=INK, spaceBefore=6, spaceAfter=10)
_LEAD = ParagraphStyle("lead", fontName="Helvetica", fontSize=10, leading=15.5,
                       textColor=MUTED, spaceAfter=14)
_H = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=11, leading=14,
                    textColor=MUTED, spaceBefore=18, spaceAfter=4)
_INTRO = ParagraphStyle("intro", fontName="Helvetica-Oblique", fontSize=8.5, leading=12,
                        textColor=FAINT, spaceAfter=8)
_SUB = ParagraphStyle("sub", fontName="Helvetica-Bold", fontSize=9.5, leading=13,
                      textColor=ACCENT, spaceBefore=10, spaceAfter=2)
_BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=9, leading=13,
                       textColor=INK, alignment=TA_LEFT, spaceAfter=3)
_DIM = ParagraphStyle("dim", fontName="Helvetica", fontSize=8, leading=11,
                      textColor=MUTED, spaceAfter=2)
_META = ParagraphStyle("meta", fontName="Helvetica", fontSize=7.5, leading=11.5,
                       textColor=FAINT, spaceAfter=8)


def _pct(x) -> str:
    try:
        return f"{round(float(x or 0) * 100)}%"
    except (TypeError, ValueError):
        return "0%"


def _val(x) -> float:
    try:
        return max(0.0, min(1.0, float(x or 0)))
    except (TypeError, ValueError):
        return 0.0


def _p(text, style) -> Paragraph:
    return Paragraph(escape(str(text if text is not None else "")), style)


def _p_lines(lines: list[str], style) -> Paragraph:
    return Paragraph("<br/>".join(escape(x) for x in lines), style)


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


class Bar(Flowable):
    """A thin proportional bar — the same meter language as the app's
    confidence/coverage bars."""

    def __init__(self, value: float, width: float = 60 * mm, height: float = 5):
        super().__init__()
        self.value = _val(value)
        self.width = width
        self.height = height

    def wrap(self, *_):
        return (self.width, self.height)

    def draw(self):
        c = self.canv
        c.setFillColor(LINE)
        c.rect(0, 0, self.width, self.height, stroke=0, fill=1)
        if self.value > 0:
            c.setFillColor(ACCENT)
            c.rect(0, 0, self.width * self.value, self.height, stroke=0, fill=1)


def _bar_row(pct_text: str, value: float, tail: str = "", *, bar_w: float = 46 * mm):
    """label-width percentage, a meter, then a trailing stat line."""
    cell = Table([[_p(pct_text, _BODY), Bar(value, width=bar_w), _p(tail, _META)]],
                colWidths=[13 * mm, bar_w + 4, PAGE_W - 2 * MARGIN - 13 * mm - bar_w - 4])
    cell.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return cell


def _pullquote(flowables: list) -> Table:
    """A left accent bar beside a block of flowables — for a claim worth
    pausing on, not just another bullet."""
    t = Table([["", flowables]],
             colWidths=[2.4, PAGE_W - 2 * MARGIN - 2.4])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), ACCENT),
        ("LEFTPADDING", (1, 0), (1, -1), 10), ("RIGHTPADDING", (1, 0), (1, -1), 0),
        ("LEFTPADDING", (0, 0), (0, -1), 0), ("RIGHTPADDING", (0, 0), (0, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def _fetch_thumb(url: str, *, w: float = 36 * mm) -> RLImage | None:
    """Best-effort: a department moodboard is worth a slow fetch, not a broken
    report. Any failure just drops that one thumbnail."""
    try:
        r = httpx.get(url, timeout=6.0, follow_redirects=True)
        r.raise_for_status()
        if len(r.content) > 8_000_000:
            return None
        reader = ImageReader(io.BytesIO(r.content))
        iw, ih = reader.getSize()
        h = w * (ih / iw) if iw else w
        return RLImage(io.BytesIO(r.content), width=w, height=h)
    except Exception:  # noqa: BLE001
        return None


def _image_row(items: list[dict]):
    cells = [img for img in (
        _fetch_thumb(e.get("image_url") or e.get("media_url"))
        for e in items if e.get("image_url") or e.get("media_url")
    ) if img]
    if not cells:
        return None
    t = Table([cells], colWidths=[38 * mm] * len(cells))
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    return t


def _footer(canv, doc):
    canv.saveState()
    canv.setFont("Helvetica", 7)
    canv.setFillColor(FAINT)
    canv.drawString(MARGIN, 12 * mm, "Assembled by THE BOXES  ·  Agentic Cinema")
    canv.drawRightString(PAGE_W - MARGIN, 12 * mm, str(doc.page))
    canv.restoreState()


def _source_line(e: dict) -> str:
    cite = " · ".join(x for x in [
        e.get("title") or e.get("source_domain") or e.get("url"), e.get("publish_date"),
    ] if x)
    own = "  ·  your upload" if e.get("source") == "director" else ""
    return f"• {cite}{own}"


def _dedup_lines(items: list[dict], key_fn, line_fn, *, cap: int) -> list[str]:
    """A research pass often harvests several fragments off the same page
    (a paragraph plus three photos). One reader-facing source list should
    name that page once, not three times."""
    seen: set[str] = set()
    lines: list[str] = []
    for it in items:
        key = (key_fn(it) or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        lines.append(line_fn(it))
        if len(lines) >= cap:
            break
    return lines


def _cite_key(e: dict) -> str:
    return e.get("title") or e.get("source_domain") or e.get("url") or ""


def build_report_pdf(*, project: dict, boxes: list[dict], evidence: list[dict],
                     verdicts: list[dict], runs: list[dict], reel: list[dict],
                     prior_art: dict | None = None) -> bytes:
    premise = (project.get("premise") or "").strip()
    story: list = []

    try:
        narrative = synthesis.build(premise, boxes, evidence, prior_art)
    except Exception:  # noqa: BLE001
        # The narrative is enrichment. A flaky model call should never break
        # the download — packets fall back to their plan-time description.
        narrative = synthesis.Narrative()

    by_id = {b.get("id"): b for b in boxes}
    grouped: dict[str, list[dict]] = {}
    for e in evidence:
        grouped.setdefault(e.get("objective_id") or "_unfiled", []).append(e)
    ordered_boxes = sorted(boxes, key=lambda x: -(x.get("score") or 0))

    # ---- cover: the picture, in full, before anything else -----------------
    story += [Spacer(1, 22 * mm), Monolith(), Spacer(1, 10 * mm)]
    story.append(_p("THE BOXES", _TITLE))
    story.append(_p("Research dossier", _KICKER))
    story.append(_p(premise or "Untitled project", _PREMISE))
    if narrative.overview:
        story.append(_p(narrative.overview, _LEAD))
    story.append(_rule())

    domains = {e.get("source_domain") for e in evidence if e.get("source_domain")}
    sources = {e.get("url") for e in evidence if e.get("url")}
    conflicts = [v for v in verdicts if v.get("relation") == "contradicts"]
    facts = [
        ("Depth", _p(str(project.get("depth", "scout")).title(), _BODY)),
        ("Research confidence", _bar_row(_pct(project.get("confidence")), project.get("confidence"))),
        ("Coverage", _bar_row(_pct(project.get("coverage")), project.get("coverage"))),
        ("Status", _p(str(project.get("status", "—")), _BODY)),
        ("Boxes", _p(str(len(boxes)), _BODY)),
        ("Evidence fragments", _p(str(len(evidence)), _BODY)),
        ("Distinct sources", _p(str(len(sources)), _BODY)),
        ("Distinct domains", _p(str(len(domains)), _BODY)),
        ("Contradictions", _p(f"{len(conflicts)} conflict, {len(verdicts) - len(conflicts)} context", _BODY)),
        ("Research passes", _p(str(len(runs)), _BODY)),
        ("Generated", _p(time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), _BODY)),
        ("Project id", _p(str(project.get("id", "")), _BODY)),
    ]
    t = Table([[_p(k, _DIM), v] for k, v in facts],
              colWidths=[42 * mm, PAGE_W - 2 * MARGIN - 42 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, LINE),
    ]))
    story.append(t)
    story.append(PageBreak())

    # ---- the boxes: one packet per box — summary first, sources after ------
    story.append(_p("THE BOXES", _H))
    story.append(_p(
        "What the research found, in plain language, box by box. Every claim "
        "below is traceable to the sources listed under it.", _INTRO))
    story.append(_rule())
    for b in ordered_boxes:
        bid = b.get("id")
        tag = "  ·  emergent" if b.get("emergent") else ""
        story.append(_p((b.get("name") or "UNNAMED") + tag, _SUB))
        story.append(_bar_row(
            _pct(b.get("score")), b.get("score") or 0,
            f"{b.get('evidence_count', 0)} items  ·  {b.get('distinct_domains', 0)} domains"))
        summary = narrative.box_summaries.get(bid) or b.get("description", "")
        if summary:
            story.append(_p(summary, _BODY))
        items = grouped.get(bid, [])
        if items:
            lines = _dedup_lines(items, _cite_key, _source_line, cap=15)
            story.append(_p_lines(lines, _META))
        story.append(Spacer(1, 8))
    unfiled = grouped.get("_unfiled")
    if unfiled:
        story.append(_p("UNFILED", _SUB))
        story.append(_p_lines(_dedup_lines(unfiled, _cite_key, _source_line, cap=15), _META))
    if not boxes:
        story.append(_p("No plan drawn yet.", _DIM))

    # ---- contradictions ----------------------------------------------------
    story.append(PageBreak())
    story.append(_p("CONTRADICTIONS", _H))
    story.append(_p(
        "Where two sources disagree. Similarity alone never decides this; "
        "each pair below was read and judged.", _INTRO))
    story.append(_rule())
    for v in verdicts:
        story.append(_p((v.get("relation") or "").upper(), _SUB))
        if v.get("explanation"):
            story.append(_p(v["explanation"], _BODY))
        story.append(_p(f"A  —  {v.get('a_cite', '')}", _DIM))
        story.append(_p(f"B  —  {v.get('b_cite', '')}", _DIM))
    if not verdicts:
        story.append(_p("None found.", _DIM))

    # ---- reference reel ------------------------------------------------------
    story.append(PageBreak())
    story.append(_p("REFERENCE REEL", _H))
    story.append(_p("The strongest material, cut into a sequence a director can read.", _INTRO))
    story.append(_rule())
    for b in reel:
        story.append(_p(f"{b.get('t', '00:00')}   {b.get('title', '')}", _SUB))
        if b.get("note"):
            story.append(_p(b["note"], _BODY))
        lines = _dedup_lines(
            b.get("sources") or [],
            lambda s: s.get("cite") or s.get("url") or "",
            lambda s: "• " + (s.get("cite") or s.get("url") or ""),
            cap=6,
        )
        if lines:
            story.append(_p_lines(lines, _META))
    if not reel:
        story.append(_p("No reel cut yet.", _DIM))

    # ---- departments: the same research, sliced by who needs it ------------
    story.append(PageBreak())
    story.append(_p("DEPARTMENTS", _H))
    story.append(_p(
        "The same boxes, grouped by which crew briefs off them, with what each "
        "one actually contains.", _INTRO))
    story.append(_rule())
    box_by_dept: dict[str, list[dict]] = {}
    for b in boxes:
        for d in b.get("departments") or []:
            box_by_dept.setdefault(d, []).append(b)
    if not box_by_dept:
        story.append(_p("No department tags on this plan yet.", _DIM))
    for d in DEPARTMENTS:
        dboxes = box_by_dept.get(d)
        if not dboxes:
            continue
        story.append(_p(_DEPT_LABEL.get(d, d.title()), _SUB))
        for b in dboxes:
            story.append(_p(
                f"{b.get('name')}  ·  {b.get('evidence_count', 0)} items", _DIM))
            summary = narrative.box_summaries.get(b.get("id")) or b.get("description", "")
            if summary:
                story.append(_p(summary, _BODY))
        if d in _VISUAL_DEPTS:
            ids = {b.get("id") for b in dboxes}
            imgs = [e for e in evidence if e.get("objective_id") in ids
                   and e.get("modality") == "image"][:4]
            row = _image_row(imgs)
            if row:
                story.append(row)
        story.append(Spacer(1, 8))

    # ---- prior art -----------------------------------------------------------
    if prior_art and prior_art.get("neighbors"):
        story.append(PageBreak())
        story.append(_p("PRIOR ART", _H))
        kws = ", ".join(prior_art.get("keywords") or [])
        story.append(_p(
            f"{prior_art.get('surveyed', 0)} existing films surveyed for a similar premise"
            + (f", seeded from: {kws}." if kws else "."), _INTRO))
        story.append(_rule())
        for nb in prior_art["neighbors"]:
            title = f"{nb.get('title', '')} ({nb.get('year', '')})".strip()
            story.append(_p(title, _SUB))
            bits = " · ".join(x for x in [
                nb.get("engine"), nb.get("pov"), nb.get("tone"), nb.get("moral_arc"), nb.get("ending"),
            ] if x)
            if bits:
                story.append(_p(bits, _BODY))
            tail = " · ".join(x for x in [
                f"similarity {nb.get('similarity', 0):.2f}", nb.get("url"),
            ] if x)
            if tail:
                story.append(_p(tail, _META))
        if prior_art.get("unclaimed_angles"):
            story.append(_p("Where this stands, and where it does not yet", _SUB))
            story.append(_p(
                "Originality is claimed only relative to the titles above, never absolutely.",
                _META))
            for a in prior_art["unclaimed_angles"]:
                block = [_p(a.get("angle", ""), _BODY)]
                if a.get("why"):
                    block.append(_p(a["why"], _DIM))
                ct = ", ".join(a.get("contrast_titles") or [])
                if ct:
                    block.append(_p(f"checked against: {ct}", _META))
                if a.get("prompt"):
                    block.append(_p(f"→ {a['prompt']}", _META))
                story.append(_pullquote(block))
                story.append(Spacer(1, 4))

    # ---- research log: the process trail, last ------------------------------
    story.append(PageBreak())
    story.append(_p("RESEARCH LOG", _H))
    story.append(_p("What each pass searched, found, and did next. Process detail, not required reading.", _INTRO))
    story.append(_rule())
    for r in runs:
        story.append(_p(f"PASS {str(r.get('run', 0)).zfill(3)}", _SUB))
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

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm,
        leftMargin=MARGIN, rightMargin=MARGIN,
        title=f"THE BOXES — {premise[:60]}" if premise else "THE BOXES",
        author="THE BOXES",
    )
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
