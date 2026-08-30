from __future__ import annotations

from decimal import Decimal
from html import escape
from io import BytesIO

from reportlab.graphics.barcode import code128
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


INK = colors.HexColor('#172033')
TEXT = colors.HexColor('#334155')
MUTED = colors.HexColor('#64748b')
LINE = colors.HexColor('#dfe4ea')
SURFACE = colors.HexColor('#f8fafc')
PRIMARY = colors.HexColor('#ff7a45')


def _text(value, fallback='—') -> str:
    raw = str(value or '').strip()
    return escape(raw if raw else fallback)


def _qty(value) -> str:
    try:
        amount = Decimal(str(value or 0))
    except Exception:
        return '0'
    if amount == amount.to_integral():
        return str(int(amount))
    return f'{amount.normalize():f}'


def _warehouse_label(warehouse, location=None) -> str:
    base = getattr(warehouse, 'name', None) or '—'
    path = getattr(location, 'full_path', None) if location else None
    return f'{base} / {path}' if path else base


def build_transfer_pdf(*, transfer, user=None) -> bytes:
    """Build a transfer PDF using ReportLab only.

    This intentionally avoids wkhtmltopdf/pdfkit so it works on Railway's
    Debian Trixie images and other minimal production containers.
    """
    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title=f'Conduce TR{int(getattr(transfer, "id", 0)):06d}',
        author='OrbisERP',
    )

    styles = getSampleStyleSheet()
    base = ParagraphStyle(
        'TransferBase', parent=styles['BodyText'], fontName='Helvetica',
        fontSize=8.5, leading=11, textColor=TEXT,
    )
    small = ParagraphStyle('TransferSmall', parent=base, fontSize=7.2, leading=9, textColor=MUTED)
    label = ParagraphStyle('TransferLabel', parent=small, fontName='Helvetica-Bold', fontSize=6.8, leading=8)
    strong = ParagraphStyle('TransferStrong', parent=base, fontName='Helvetica-Bold', textColor=INK)
    title = ParagraphStyle('TransferTitle', parent=base, fontName='Helvetica-Bold', fontSize=20, leading=22, textColor=INK)
    doc_title = ParagraphStyle('TransferDocTitle', parent=base, fontName='Helvetica-Bold', fontSize=11, leading=13, textColor=MUTED)
    right = ParagraphStyle('TransferRight', parent=base, alignment=TA_RIGHT)
    center_small = ParagraphStyle('TransferCenterSmall', parent=small, alignment=TA_CENTER)

    transfer_id = int(getattr(transfer, 'id', 0) or 0)
    ref = f'TR{transfer_id:06d}'
    created = getattr(transfer, 'created_at', None)
    created_text = created.strftime('%d/%m/%Y %H:%M') if created else '—'
    emitted_by = getattr(user, 'name', None) or getattr(getattr(transfer, 'creator', None), 'name', None) or 'Sistema'

    story = []

    barcode = code128.Code128(ref, barHeight=11 * mm, barWidth=0.34 * mm, humanReadable=False)
    barcode_box = Table([
        [barcode],
        [Paragraph(_text(ref), center_small)],
    ], colWidths=[55 * mm])
    barcode_box.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.55, LINE),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
        ('TOPPADDING', (0, 1), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
    ]))

    header_left = [
        Paragraph('ORBIS ERP', title),
        Paragraph('CONDUCE DE TRANSFERENCIA LOGÍSTICA', doc_title),
        Spacer(1, 2 * mm),
        Paragraph(f"<font color='#ff7a45'><b>REF: {_text(ref)}</b></font>", strong),
    ]
    header = Table([[header_left, barcode_box]], colWidths=[120 * mm, 60 * mm])
    header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEBELOW', (0, 0), (-1, -1), 1.2, INK),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story += [header, Spacer(1, 5 * mm)]

    info = Table([
        [Paragraph('ALMACÉN ORIGEN', label), Paragraph('ALMACÉN DESTINO', label)],
        [Paragraph(_text(_warehouse_label(getattr(transfer, 'from_warehouse', None), getattr(transfer, 'from_location', None))), strong),
         Paragraph(_text(_warehouse_label(getattr(transfer, 'to_warehouse', None), getattr(transfer, 'to_location', None))), strong)],
        [Paragraph('EMITIDO POR', label), Paragraph('FECHA Y HORA', label)],
        [Paragraph(_text(emitted_by), base), Paragraph(_text(created_text), base)],
    ], colWidths=[90 * mm, 90 * mm])
    info.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), SURFACE),
        ('BOX', (0, 0), (-1, -1), 0.6, LINE),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, LINE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story += [info, Spacer(1, 6 * mm)]

    product = getattr(transfer, 'product', None)
    product_name = getattr(product, 'name', None) or 'Producto'
    sku = getattr(product, 'sku', None) or 'SIN SKU'
    qty = _qty(getattr(transfer, 'quantity', 0))
    rows = [
        [Paragraph('DESCRIPCIÓN DEL PRODUCTO', label), Paragraph('SKU / REFERENCIA', label), Paragraph('CANTIDAD', label)],
        [Paragraph(f'<b>{_text(product_name)}</b>', base), Paragraph(_text(sku), base), Paragraph(f'<b>{_text(qty)}</b>', right)],
    ]
    items = Table(rows, colWidths=[100 * mm, 48 * mm, 32 * mm], repeatRows=1)
    items.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eef2f6')),
        ('LINEBELOW', (0, 0), (-1, 0), 0.7, LINE),
        ('LINEBELOW', (0, 1), (-1, -1), 0.5, LINE),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
    ]))
    story += [items, Spacer(1, 12 * mm)]

    note = Table([[
        Paragraph('<b>NOTA DE RECEPCIÓN</b><br/>Este documento debe ser escaneado en el almacén de destino para confirmar la entrada de mercancía.', base)
    ]], colWidths=[180 * mm])
    note.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fff7ed')),
        ('BOX', (0, 0), (-1, -1), 0.6, colors.HexColor('#fed7aa')),
        ('LEFTPADDING', (0, 0), (-1, -1), 9),
        ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story += [note, Spacer(1, 8 * mm), Paragraph('DOCUMENTO GENERADO POR ORBIS ERP · USO INTERNO EXCLUSIVO', center_small)]

    doc.build(story)
    return output.getvalue()
