# services/pdf_service.py
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# CAPA PDF EXPORT â€” Sprint 3 Week 2
# Renders a regulatory-grade CAPA document with ReportLab.
# Pure-Python, no network. Returns PDF bytes.
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

import io
from datetime import datetime
from xml.sax.saxutils import escape
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)
from reportlab.lib.enums import TA_LEFT

NAVY  = colors.HexColor("#0D1B40")
GREEN = colors.HexColor("#0E7C2B")
GREY  = colors.HexColor("#555555")
LIGHT = colors.HexColor("#F2F4F7")
LINE  = colors.HexColor("#CCD3E0")


def _pdf_text(value, default="\u2014"):
    """Escape text before passing it to ReportLab Paragraph markup."""
    if value is None:
        return default
    text = str(value)
    if not text:
        return default
    return escape(text).replace("\n", "<br/>")


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("CapaTitle", parent=ss["Title"], fontSize=18,
                          textColor=NAVY, spaceAfter=2, alignment=TA_LEFT))
    ss.add(ParagraphStyle("CapaSub", parent=ss["Normal"], fontSize=9,
                          textColor=GREY, spaceAfter=10))
    ss.add(ParagraphStyle("SectionH", parent=ss["Heading2"], fontSize=11,
                          textColor=NAVY, spaceBefore=10, spaceAfter=4))
    ss.add(ParagraphStyle("Body", parent=ss["Normal"], fontSize=9.5,
                          textColor=colors.HexColor("#1A1A1A"), leading=13, spaceAfter=6))
    ss.add(ParagraphStyle("Label", parent=ss["Normal"], fontSize=8.5,
                          textColor=GREY))
    ss.add(ParagraphStyle("Val", parent=ss["Normal"], fontSize=9.5,
                          textColor=colors.HexColor("#1A1A1A")))
    return ss


def _header_footer(canvas, doc):
    canvas.saveState()
    # header band
    canvas.setFillColor(NAVY)
    canvas.rect(0, letter[1] - 0.5 * inch, letter[0], 0.5 * inch, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawString(0.75 * inch, letter[1] - 0.33 * inch, "AI Quality Management System - CAPA Record")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(letter[0] - 0.75 * inch, letter[1] - 0.33 * inch, "Quality Management System")
    # footer
    canvas.setFillColor(GREY)
    canvas.setFont("Helvetica", 7.5)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    canvas.drawString(0.75 * inch, 0.4 * inch,
                      f"Generated {ts}  \u00B7  AI-assisted draft \u2014 requires human review & approval")
    canvas.drawRightString(letter[0] - 0.75 * inch, 0.4 * inch, f"Page {doc.page}")
    canvas.setStrokeColor(LINE)
    canvas.line(0.75 * inch, 0.55 * inch, letter[0] - 0.75 * inch, 0.55 * inch)
    canvas.restoreState()


def _kv_table(rows):
    t = Table(rows, colWidths=[1.6 * inch, 5.2 * inch])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 9),
        ("TEXTCOLOR", (0, 0), (0, -1), NAVY),
        ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor("#1A1A1A")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
        ("BACKGROUND", (0, 0), (0, -1), LIGHT),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def _fmt_refs(refs):
    if isinstance(refs, list):
        return ", ".join(str(r) for r in refs) if refs else "\u2014"
    if isinstance(refs, str):
        s = refs.strip("[]").replace("'", "").replace('"', "")
        return s if s else "\u2014"
    return "\u2014"


def build_capa_pdf(capa: dict, similar: list = None) -> bytes:
    """
    Render a CAPA dict to PDF bytes. `similar` (optional) is the RAG
    top-k list; if provided, a short 'related past cases' note is added.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        topMargin=0.8 * inch, bottomMargin=0.8 * inch,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        title=f"CAPA {capa.get('capaId','')}",
    )
    ss = _styles()
    story = []

    # Title block
    story.append(Paragraph(f"CAPA {_pdf_text(capa.get('capaId'))}", ss["CapaTitle"]))
    status = capa.get("status", "Under Review")
    story.append(Paragraph(
        f"Status: {_pdf_text(status)}  \u00B7  Source Record: {_pdf_text(capa.get('sourceRecordId'))}  "
        f"\u00B7  Risk: {_pdf_text(capa.get('riskRating'))}", ss["CapaSub"]))
    story.append(HRFlowable(width="100%", thickness=1, color=GREEN, spaceAfter=10))

    # Metadata table
    story.append(Paragraph("Record Details", ss["SectionH"]))
    story.append(_kv_table([
        ["Source Record", str(capa.get("sourceRecordId", "\u2014"))],
        ["Owner", str(capa.get("capaOwner", "\u2014"))],
        ["Risk Rating", str(capa.get("riskRating", "\u2014"))],
        ["Est. Closure (days)", str(capa.get("estimatedClosureDays", "\u2014"))],
        ["Regulatory References", _fmt_refs(capa.get("regulatoryRef", []))],
        ["Created", str(capa.get("createdAt", "\u2014"))[:19].replace("T", " ")],
    ]))

    # CAPA content sections
    sections = [
        ("Root Cause", capa.get("rootCause", "")),
        ("Immediate Action", capa.get("immediateAction", "")),
        ("Corrective Action", capa.get("correctiveAction", "")),
        ("Preventive Action", capa.get("preventiveAction", "")),
        ("Effectiveness Check", capa.get("effectivenessCheck", "")),
    ]
    for label, text in sections:
        story.append(Paragraph(label, ss["SectionH"]))
        story.append(Paragraph(_pdf_text(text), ss["Body"]))

    if capa.get("notes"):
        story.append(Paragraph("Additional Notes", ss["SectionH"]))
        story.append(Paragraph(_pdf_text(capa["notes"]), ss["Body"]))

    # Optional RAG related cases
    if similar:
        story.append(Spacer(1, 6))
        story.append(Paragraph("Related Past Cases (AI-retrieved for reference)", ss["SectionH"]))
        for s in similar[:3]:
            story.append(Paragraph(
                f"\u2022 [{_pdf_text(s.get('similarity'), '')}] {_pdf_text(s.get('title'), '')} "
                f"(CAPA {_pdf_text(s.get('capaId'), '')})", ss["Label"]))

    # Approval / signature block
    story.append(Spacer(1, 18))
    story.append(HRFlowable(width="100%", thickness=0.5, color=LINE, spaceAfter=8))
    story.append(Paragraph("Approval", ss["SectionH"]))
    sig = Table([
        ["Reviewed by:", "", "Approved by:", ""],
        ["", "", "", ""],
        ["Name / Signature", "Date", "Name / Signature", "Date"],
    ], colWidths=[1.7 * inch, 1.7 * inch, 1.7 * inch, 1.7 * inch])
    sig.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
        ("TEXTCOLOR", (0, 0), (-1, -1), GREY),
        ("LINEBELOW", (0, 1), (0, 1), 0.5, colors.black),
        ("LINEBELOW", (1, 1), (1, 1), 0.5, colors.black),
        ("LINEBELOW", (2, 1), (2, 1), 0.5, colors.black),
        ("LINEBELOW", (3, 1), (3, 1), 0.5, colors.black),
        ("TOPPADDING", (0, 1), (-1, 1), 16),
        ("FONT", (0, 2), (-1, 2), "Helvetica", 7),
    ]))
    story.append(sig)

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return buf.getvalue()


