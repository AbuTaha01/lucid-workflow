"""
actions/pdf_generator.py
========================
Generates two PDF documents using ReportLab:

  1. generate_quote_pdf()        — client-facing quote with order details,
                                   engineering specs, and financial summary
  2. generate_sustainability_pdf() — sustainability data sheet for retail
                                     supplier portals (e.g. Sobeys, PetSmart)
"""

from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

# ── Lucid Corp brand colours ──────────────────────────────────────────────────
LUCID_GREEN      = colors.HexColor("#2d7a3a")
LUCID_GREEN_PALE = colors.HexColor("#e8f4ea")
LUCID_DARK       = colors.HexColor("#1a1a14")
LUCID_MUTED      = colors.HexColor("#6b6b5a")
LUCID_BORDER     = colors.HexColor("#d0d0c4")
WHITE            = colors.white


def _base_styles():
    styles = getSampleStyleSheet()
    custom = {
        "title": ParagraphStyle(
            "DocTitle",
            fontSize=22, fontName="Helvetica-Bold",
            textColor=LUCID_DARK, spaceAfter=4, leading=26,
        ),
        "subtitle": ParagraphStyle(
            "DocSubtitle",
            fontSize=11, fontName="Helvetica",
            textColor=LUCID_MUTED, spaceAfter=2,
        ),
        "section": ParagraphStyle(
            "Section",
            fontSize=10, fontName="Helvetica-Bold",
            textColor=LUCID_GREEN, spaceBefore=14, spaceAfter=4,
            borderPad=2,
        ),
        "body": ParagraphStyle(
            "Body",
            fontSize=9, fontName="Helvetica",
            textColor=LUCID_DARK, leading=14, spaceAfter=3,
        ),
        "body_small": ParagraphStyle(
            "BodySmall",
            fontSize=8, fontName="Helvetica",
            textColor=LUCID_MUTED, leading=12,
        ),
        "mono": ParagraphStyle(
            "Mono",
            fontSize=8, fontName="Courier",
            textColor=LUCID_DARK, leading=13,
            backColor=colors.HexColor("#f5f4f0"),
            borderPad=6, spaceAfter=4,
        ),
        "footer": ParagraphStyle(
            "Footer",
            fontSize=7.5, fontName="Helvetica",
            textColor=LUCID_MUTED, alignment=TA_CENTER,
        ),
        "center": ParagraphStyle(
            "Center",
            fontSize=9, fontName="Helvetica",
            textColor=LUCID_DARK, alignment=TA_CENTER,
        ),
    }
    return custom


def _header_block(styles, doc_type: str, ref: str) -> list:
    """Shared letterhead block for all Lucid Corp PDFs."""
    date_str = datetime.now().strftime("%B %d, %Y")
    elements = []

    # Top bar table: logo text left, doc info right
    header_data = [[
        Paragraph("<b>LUCID CORP</b>", ParagraphStyle(
            "Logo", fontSize=16, fontName="Helvetica-Bold",
            textColor=WHITE,
        )),
        Paragraph(
            f"<font color='white'>{doc_type}<br/>"
            f"<font size='8'>Ref: {ref} &nbsp;|&nbsp; {date_str}</font></font>",
            ParagraphStyle("HeaderRight", fontSize=10, fontName="Helvetica",
                           alignment=TA_RIGHT, textColor=WHITE),
        ),
    ]]
    header_table = Table(header_data, colWidths=[3.5 * inch, 4 * inch])
    header_table.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), LUCID_GREEN),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (0, 0), 14),
        ("RIGHTPADDING", (1, 0), (1, 0), 14),
        ("TOPPADDING",   (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 12),
    ]))
    elements.append(header_table)

    # Tagline below header
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(
        "Custom PET Food Packaging &nbsp;·&nbsp; 390 Orenda Road, Brampton ON L6T1G8 &nbsp;·&nbsp; info@lucidcorp.com",
        ParagraphStyle("Tagline", fontSize=7.5, fontName="Helvetica",
                       textColor=LUCID_MUTED, alignment=TA_CENTER),
    ))
    elements.append(HRFlowable(width="100%", thickness=0.5,
                                color=LUCID_BORDER, spaceAfter=10))
    return elements


def _footer(canvas, doc):
    """Page footer drawn on every page."""
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(LUCID_MUTED)
    canvas.drawString(0.75 * inch, 0.5 * inch,
                      "Lucid Corp Confidential — lucidcorp.com")
    canvas.drawRightString(
        letter[0] - 0.75 * inch, 0.5 * inch,
        f"Page {doc.page}",
    )
    canvas.restoreState()


def _wrap_agent_output(text: str, styles: dict) -> list:
    """Convert raw agent output text into PDF paragraphs."""
    elements = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            elements.append(Spacer(1, 4))
            continue
        # Lines starting with numbers or dashes → body style
        # Lines starting with → or ✓ → styled differently
        if stripped.startswith(("→", "✓")):
            elements.append(Paragraph(
                f"<i>{stripped}</i>",
                ParagraphStyle("Note", fontSize=8.5, fontName="Helvetica-Oblique",
                               textColor=LUCID_GREEN, spaceBefore=6),
            ))
        else:
            elements.append(Paragraph(stripped, styles["body"]))
    return elements


# ─────────────────────────────────────────────────────────────────────────────
#  Quote PDF
# ─────────────────────────────────────────────────────────────────────────────

def generate_quote_pdf(
    brief: str,
    sales_output: str,
    design_output: str,
    finance_output: str,
    output_path: Path,
) -> Path:
    """
    Generate a client-facing quote PDF combining Sales, Engineering,
    and Finance agent outputs.
    """
    ref      = f"LCQ-{datetime.now().strftime('%Y%m%d%H%M')}"
    doc      = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.6 * inch,   bottomMargin=0.75 * inch,
    )
    styles   = _base_styles()
    elements = []

    # ── Header ────────────────────────────────────────────────────────────────
    elements += _header_block(styles, "CUSTOM PACKAGING QUOTE", ref)

    # ── Intro ─────────────────────────────────────────────────────────────────
    elements.append(Paragraph(
        "Thank you for your interest in Lucid Corp's sustainable thermoforming solutions. "
        "Please find your custom packaging quote below, prepared by our Sales, Engineering, "
        "and Finance teams.",
        styles["body"],
    ))
    elements.append(Spacer(1, 10))

    # ── Order Brief ───────────────────────────────────────────────────────────
    elements.append(Paragraph("ORDER BRIEF", styles["section"]))
    elements.append(HRFlowable(width="100%", thickness=0.5,
                                color=LUCID_BORDER, spaceAfter=6))
    brief_table = Table(
        [[Paragraph(brief.strip(), styles["body"])]],
        colWidths=[7.5 * inch],
    )
    brief_table.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), LUCID_GREEN_PALE),
        ("LEFTPADDING",  (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING",   (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 8),
        ("ROUNDEDCORNERS", (0, 0), (-1, -1), [4, 4, 4, 4]),
    ]))
    elements.append(brief_table)
    elements.append(Spacer(1, 10))

    # ── Sales Intake Summary ──────────────────────────────────────────────────
    elements.append(Paragraph("CLIENT & ORDER SUMMARY", styles["section"]))
    elements.append(HRFlowable(width="100%", thickness=0.5,
                                color=LUCID_BORDER, spaceAfter=6))
    elements += _wrap_agent_output(sales_output, styles)
    elements.append(Spacer(1, 8))

    # ── Engineering Assessment ────────────────────────────────────────────────
    elements.append(Paragraph("ENGINEERING & TOOLING ASSESSMENT", styles["section"]))
    elements.append(HRFlowable(width="100%", thickness=0.5,
                                color=LUCID_BORDER, spaceAfter=6))
    elements += _wrap_agent_output(design_output, styles)
    elements.append(Spacer(1, 8))

    # ── Financial Quote ───────────────────────────────────────────────────────
    elements.append(Paragraph("PRICING & FINANCIAL TERMS", styles["section"]))
    elements.append(HRFlowable(width="100%", thickness=0.5,
                                color=LUCID_BORDER, spaceAfter=6))
    elements += _wrap_agent_output(finance_output, styles)
    elements.append(Spacer(1, 12))

    # ── Terms box ────────────────────────────────────────────────────────────
    terms_data = [[
        Paragraph("<b>Quote Validity:</b> 30 days from issue date.", styles["body_small"]),
        Paragraph("<b>Questions?</b> info@lucidcorp.com", styles["body_small"]),
    ]]
    terms_table = Table(terms_data, colWidths=[3.75 * inch, 3.75 * inch])
    terms_table.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), colors.HexColor("#f5f4f0")),
        ("LEFTPADDING",  (0, 0), (-1, -1), 10),
        ("TOPPADDING",   (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 8),
        ("BOX",          (0, 0), (-1, -1), 0.5, LUCID_BORDER),
    ]))
    elements.append(terms_table)

    doc.build(elements, onFirstPage=_footer, onLaterPages=_footer)
    return output_path


# ─────────────────────────────────────────────────────────────────────────────
#  Sustainability Data Sheet PDF
# ─────────────────────────────────────────────────────────────────────────────

def generate_sustainability_pdf(
    brief: str,
    sustainability_output: str,
    output_path: Path,
) -> Path:
    """
    Generate a sustainability data sheet PDF suitable for retail
    supplier portals (Sobeys, PetSmart, Whole Foods, EU compliance).
    """
    ref      = f"LCS-{datetime.now().strftime('%Y%m%d%H%M')}"
    doc      = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.6 * inch,   bottomMargin=0.75 * inch,
    )
    styles   = _base_styles()
    elements = []

    # ── Header ────────────────────────────────────────────────────────────────
    elements += _header_block(styles, "SUSTAINABILITY DATA SHEET", ref)

    # ── Mission statement ─────────────────────────────────────────────────────
    mission_data = [[Paragraph(
        "<b>Lucid Corp Mission:</b> Eliminate billions of soaker pads and non-recyclable "
        "trays from landfills. Our 100% recyclable rPET and ocean-bound plastic packaging "
        "enables a circular economy — <i>Simply Rinse &amp; Recycle.</i>",
        styles["body"],
    )]]
    mission_table = Table(mission_data, colWidths=[7.5 * inch])
    mission_table.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), LUCID_GREEN_PALE),
        ("LEFTPADDING",  (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING",   (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 10),
        ("LINEAFTER",    (0, 0), (0, -1), 3, LUCID_GREEN),
    ]))
    elements.append(mission_table)
    elements.append(Spacer(1, 12))

    # ── Product brief ─────────────────────────────────────────────────────────
    elements.append(Paragraph("PRODUCT BRIEF", styles["section"]))
    elements.append(HRFlowable(width="100%", thickness=0.5,
                                color=LUCID_BORDER, spaceAfter=6))
    elements.append(Paragraph(brief.strip(), styles["body"]))
    elements.append(Spacer(1, 10))

    # ── Sustainability profile ────────────────────────────────────────────────
    elements.append(Paragraph("SUSTAINABILITY PROFILE & CERTIFICATIONS", styles["section"]))
    elements.append(HRFlowable(width="100%", thickness=0.5,
                                color=LUCID_BORDER, spaceAfter=6))
    elements += _wrap_agent_output(sustainability_output, styles)
    elements.append(Spacer(1, 12))

    # ── Certifications table ──────────────────────────────────────────────────
    elements.append(Paragraph("APPLICABLE CERTIFICATIONS", styles["section"]))
    elements.append(HRFlowable(width="100%", thickness=0.5,
                                color=LUCID_BORDER, spaceAfter=6))

    cert_data = [
        ["Certification", "Region", "Status"],
        ["Rinse & Recycle — Plastics",   "USA & Canada", "✓ Applicable"],
        ["Ocean-Bound Plastic Content",  "International", "✓ Available"],
        ["100% Recyclable rPET",         "North America", "✓ Standard"],
        ["EU Packaging Regulation",      "European Union", "See compliance notes"],
    ]
    cert_table = Table(cert_data, colWidths=[3.5 * inch, 2 * inch, 2 * inch])
    cert_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), LUCID_GREEN),
        ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8.5),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1),
            [colors.HexColor("#f9f9f6"), colors.HexColor("#f2f2ec")]),
        ("TEXTCOLOR",     (0, 1), (-1, -1), LUCID_DARK),
        ("ALIGN",         (1, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (0, -1), 10),
        ("BOX",           (0, 0), (-1, -1), 0.5, LUCID_BORDER),
        ("INNERGRID",     (0, 0), (-1, -1), 0.25, LUCID_BORDER),
    ]))
    elements.append(cert_table)
    elements.append(Spacer(1, 14))

    # ── Disclaimer ────────────────────────────────────────────────────────────
    elements.append(Paragraph(
        "This document was generated by Lucid Corp's AI Workflow System. "
        "Certification details and compliance status should be verified with Lucid Corp's "
        "Sustainability team before submission to retail portals. "
        "Contact: info@lucidcorp.com",
        styles["body_small"],
    ))

    doc.build(elements, onFirstPage=_footer, onLaterPages=_footer)
    return output_path
