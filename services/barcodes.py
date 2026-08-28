from io import BytesIO

import barcode
from barcode.writer import SVGWriter


def barcode_svg(value):
    value = (value or '').strip()
    if not value:
        raise ValueError('Código vacío')
    writer = SVGWriter()
    buffer = BytesIO()
    options = {'write_text': True, 'module_height': 12.0, 'quiet_zone': 2.0, 'font_size': 8, 'text_distance': 2}
    if value.isdigit() and len(value) in {12, 13}:
        base = value[:12]
        code = barcode.get('ean13', base, writer=writer)
    else:
        code = barcode.get('code128', value[:80], writer=writer)
    code.write(buffer, options=options)
    return buffer.getvalue()
