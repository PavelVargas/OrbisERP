from __future__ import annotations

from decimal import Decimal
from html import escape
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


INK = colors.HexColor('#172033')
TEXT_SOFT = colors.HexColor('#526071')
MUTED = colors.HexColor('#7b8794')
LINE = colors.HexColor('#e5e9ef')
SURFACE = colors.HexColor('#f8fafc')
PRIMARY = colors.HexColor('#2563eb')
PRIMARY_SOFT = colors.HexColor('#eff6ff')
WARNING = colors.HexColor('#9a5b08')
WARNING_SOFT = colors.HexColor('#fff8e7')


def _decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal('0')


def _money(value, symbol: str, conversion_rate) -> str:
    rate = _decimal(conversion_rate)
    if rate <= 0:
        rate = Decimal('1')
    amount = _decimal(value) / rate
    return f'{symbol} {amount:,.2f}'


def _text(value, fallback='—') -> str:
    raw = str(value or '').strip()
    return escape(raw if raw else fallback)


def _safe_logo_path(company, static_folder: str | Path | None) -> Path | None:
    if not company or not getattr(company, 'logo', None) or not static_folder:
        return None
    static_root = Path(static_folder).resolve()
    relative = str(company.logo).lstrip('/\\')
    candidate = (static_root / relative).resolve()
    if candidate == static_root or static_root not in candidate.parents:
        return None
    try:
        if not candidate.is_file() or candidate.stat().st_size > 10 * 1024 * 1024:
            return None
    except OSError:
        return None
    if candidate.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp'}:
        return None
    return candidate


def build_sale_invoice_pdf(*, sale, company, static_folder, selected_currency, currency_symbol, conversion_rate) -> bytes:
    """Build a self-contained invoice/quotation PDF without an OS PDF binary.

    ReportLab is already an application dependency, so this works in Linux,
    Windows, containers and production runners without wkhtmltopdf/pdfkit.
    """
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=letter,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title=f"{'Cotizacion' if getattr(sale, 'status', '') == 'QUOTATION' else 'Factura'} {getattr(sale, 'id', '')}",
        author='OrbisERP',
    )

    sample = getSampleStyleSheet()
    base = ParagraphStyle(
        'OrbisBase',
        parent=sample['BodyText'],
        fontName='Helvetica',
        fontSize=8.6,
        leading=11.2,
        textColor=TEXT_SOFT,
        spaceAfter=0,
    )
    small = ParagraphStyle('OrbisSmall', parent=base, fontSize=7.5, leading=9.5, textColor=MUTED)
    strong = ParagraphStyle('OrbisStrong', parent=base, fontName='Helvetica-Bold', textColor=INK)
    h1 = ParagraphStyle('OrbisH1', parent=base, fontName='Helvetica-Bold', fontSize=19, leading=22, textColor=INK)
    doc_title = ParagraphStyle('OrbisDocTitle', parent=h1, fontSize=22, leading=24, alignment=TA_RIGHT)
    right = ParagraphStyle('OrbisRight', parent=base, alignment=TA_RIGHT)
    right_strong = ParagraphStyle('OrbisRightStrong', parent=strong, alignment=TA_RIGHT)
    label = ParagraphStyle('OrbisLabel', parent=small, fontName='Helvetica-Bold', fontSize=7, textColor=MUTED, leading=8.5)

    is_quote = getattr(sale, 'status', '') == 'QUOTATION'
    kind = 'COT' if is_quote else 'FAC'
    company_name = getattr(company, 'name', None) or 'OrbisERP'
    logo_path = _safe_logo_path(company, static_folder)

    story = []
    if not company or getattr(company, 'fiscal_mode', 'disabled') == 'disabled':
        disclaimer = getattr(company, 'fiscal_disclaimer', None) or 'DOCUMENTO NO FISCAL'
        notice = Table([[Paragraph(_text(disclaimer), ParagraphStyle(
            'FiscalNotice', parent=small, fontName='Helvetica-Bold', textColor=WARNING,
            alignment=1, fontSize=7.2, leading=9,
        ))]], colWidths=[183 * mm])
        notice.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), WARNING_SOFT),
            ('BOX', (0, 0), (-1, -1), 0.6, colors.HexColor('#f2d49c')),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story += [notice, Spacer(1, 4 * mm)]

    company_lines = [Paragraph(_text(company_name), h1)]
    if getattr(company, 'rnc', None):
        company_lines.append(Paragraph(f"<b>RNC:</b> {_text(company.rnc)}", small))
    if getattr(company, 'address', None):
        company_lines.append(Paragraph(_text(company.address), small))
    contact = ' · '.join(filter(None, [str(getattr(company, 'phone', '') or '').strip(), str(getattr(company, 'email', '') or '').strip()]))
    if contact:
        company_lines.append(Paragraph(_text(contact), small))

    if logo_path:
        try:
            logo = Image(str(logo_path), width=24 * mm, height=24 * mm, kind='proportional')
            brand = Table([[logo, company_lines]], colWidths=[28 * mm, 77 * mm], hAlign='LEFT')
            brand.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0), ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0)]))
        except Exception:
            brand = company_lines
    else:
        brand = company_lines

    created = getattr(sale, 'created_at', None)
    date_text = created.strftime('%d/%m/%Y') if created else '—'
    time_text = created.strftime('%H:%M') if created else '—'
    meta_rows = [
        [Paragraph('FECHA', label), Paragraph(_text(date_text), right_strong)],
        [Paragraph('HORA', label), Paragraph(_text(time_text), right_strong)],
        [Paragraph('MONEDA', label), Paragraph(_text(selected_currency), right_strong)],
    ]
    if is_quote and getattr(sale, 'quote_valid_until', None):
        meta_rows.append([
            Paragraph('VÁLIDA HASTA', label),
            Paragraph(_text(sale.quote_valid_until.strftime('%d/%m/%Y')), right_strong),
        ])
    invoice_meta = [
        Paragraph('Cotización' if is_quote else 'Factura', doc_title),
        Paragraph(f"<font color='#2563eb'><b>{kind}-{int(getattr(sale, 'id', 0)):06d}</b></font>", right_strong),
        Spacer(1, 2 * mm),
        Table(meta_rows, colWidths=[25 * mm, 39 * mm]),
    ]

    header = Table([[brand, invoice_meta]], colWidths=[112 * mm, 71 * mm])
    header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story += [header, Spacer(1, 5 * mm)]

    client = getattr(sale, 'client', None)
    customer_name = getattr(client, 'name', None) or getattr(sale, 'customer_name', None) or 'Consumidor final'
    client_rows = [[Paragraph('CLIENTE', label), Paragraph(_text(customer_name), strong)]]
    if client and getattr(client, 'phone', None):
        client_rows.append([Paragraph('TELÉFONO', label), Paragraph(_text(client.phone), base)])
    if client and getattr(client, 'email', None):
        client_rows.append([Paragraph('CORREO', label), Paragraph(_text(client.email), base)])
    client_box = Table(client_rows, colWidths=[27 * mm, 156 * mm])
    client_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), SURFACE),
        ('BOX', (0, 0), (-1, -1), 0.55, LINE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 9),
        ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story += [client_box, Spacer(1, 5 * mm)]

    item_rows = [[
        Paragraph('DESCRIPCIÓN', label),
        Paragraph('CANT.', label),
        Paragraph('PRECIO', label),
        Paragraph('IMP.', label),
        Paragraph('IMPORTE', label),
    ]]
    for item in list(getattr(sale, 'items', []) or []):
        product = getattr(item, 'product', None)
        variant = getattr(item, 'variant', None)
        title = getattr(variant, 'name', None) or getattr(product, 'name', None) or 'Producto'
        sku = getattr(variant, 'sku', None) or getattr(product, 'sku', None)
        description = f"<b>{_text(title)}</b>"
        if sku:
            description += f"<br/><font color='#7b8794'>SKU {_text(sku)}</font>"
        quantity = _decimal(getattr(item, 'quantity', 0))
        qty_text = f'{quantity.normalize():f}' if quantity != quantity.to_integral() else f'{int(quantity)}'
        tax_rate = _decimal(getattr(item, 'tax_rate', 0))
        item_rows.append([
            Paragraph(description, base),
            Paragraph(_text(qty_text), right),
            Paragraph(_money(getattr(item, 'price', 0), currency_symbol, conversion_rate), right),
            Paragraph(f'{tax_rate:,.2f}%', right),
            Paragraph(_money(_decimal(getattr(item, 'price', 0)) * quantity, currency_symbol, conversion_rate), right_strong),
        ])

    items_table = Table(item_rows, colWidths=[79 * mm, 20 * mm, 28 * mm, 20 * mm, 36 * mm], repeatRows=1)
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eef2f6')),
        ('TEXTCOLOR', (0, 0), (-1, 0), MUTED),
        ('LINEBELOW', (0, 0), (-1, 0), 0.7, LINE),
        ('LINEBELOW', (0, 1), (-1, -1), 0.45, LINE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('TOPPADDING', (0, 0), (-1, 0), 7),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 7),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
    ]))
    story += [items_table, Spacer(1, 5 * mm)]

    notes_text = getattr(sale, 'quote_notes', None) if is_quote else getattr(company, 'invoice_footer', None)
    if not notes_text:
        notes_text = 'Gracias por su preferencia.'
    note_parts = [Paragraph('NOTAS', label), Spacer(1, 1.5 * mm), Paragraph(_text(notes_text), base)]
    if selected_currency != 'DOP':
        note_parts += [Spacer(1, 1.5 * mm), Paragraph(f'Tasa aplicada: 1 {_text(selected_currency)} = {_decimal(conversion_rate):,.2f} DOP.', small)]

    total_rows = [
        [Paragraph('Subtotal', base), Paragraph(_money(getattr(sale, 'subtotal', 0), currency_symbol, conversion_rate), right_strong)],
        [Paragraph('Impuestos', base), Paragraph(_money(getattr(sale, 'itbis', 0), currency_symbol, conversion_rate), right_strong)],
    ]
    discount = _decimal(getattr(sale, 'discount_amount', 0))
    if discount:
        total_rows.append([Paragraph('Descuento', base), Paragraph(f"- {_money(discount, currency_symbol, conversion_rate)}", right_strong)])
    if not is_quote:
        paid = _decimal(getattr(sale, 'amount_paid', 0))
        balance = _decimal(getattr(sale, 'balance', 0))
        if paid:
            total_rows.append([Paragraph('Pagado', base), Paragraph(_money(paid, currency_symbol, conversion_rate), right_strong)])
        if balance > 0:
            total_rows.append([Paragraph('Balance', base), Paragraph(_money(balance, currency_symbol, conversion_rate), right_strong)])
    total_rows.append([Paragraph('<b>Total</b>', ParagraphStyle('GrandLabel', parent=base, fontName='Helvetica-Bold', fontSize=11, textColor=INK)), Paragraph(_money(getattr(sale, 'total', 0), currency_symbol, conversion_rate), ParagraphStyle('GrandValue', parent=right_strong, fontSize=12, textColor=INK))])
    totals = Table(total_rows, colWidths=[35 * mm, 48 * mm])
    totals.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -2), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -2), 4),
        ('LINEABOVE', (0, -1), (-1, -1), 1.2, INK),
        ('TOPPADDING', (0, -1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, -1), (-1, -1), 4),
    ]))

    bottom = Table([[note_parts, totals]], colWidths=[96 * mm, 87 * mm])
    bottom.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (0, 0), 10),
        ('RIGHTPADDING', (1, 0), (1, 0), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story += [KeepTogether(bottom), Spacer(1, 7 * mm)]

    footer = Paragraph(
        f"{_text(company_name)} · {kind}-{int(getattr(sale, 'id', 0)):06d} · Documento generado por OrbisERP",
        ParagraphStyle('Footer', parent=small, alignment=1, fontSize=7, textColor=MUTED),
    )
    story.append(footer)

    def page_decoration(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(PRIMARY)
        canvas.setLineWidth(2.2)
        canvas.line(doc.leftMargin, letter[1] - 9 * mm, letter[0] - doc.rightMargin, letter[1] - 9 * mm)
        canvas.setFillColor(MUTED)
        canvas.setFont('Helvetica', 6.8)
        canvas.drawRightString(letter[0] - doc.rightMargin, 8 * mm, f'Página {doc.page}')
        canvas.restoreState()

    document.build(story, onFirstPage=page_decoration, onLaterPages=page_decoration)
    return output.getvalue()
