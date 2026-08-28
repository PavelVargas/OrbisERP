"""Resolve product images stored locally by OrbisERP."""

from flask import url_for


def product_image_url(product):
    """Return the local product image URL, or ``None`` when no photo exists.

    Product photos are uploaded manually and stored under ``static/uploads``.
    The legacy ``image_url`` database column is intentionally ignored so old
    remote links cannot unexpectedly replace a user-uploaded image.
    """
    image_path = str(getattr(product, 'image_path', '') or '').strip()
    if image_path:
        return url_for('static', filename=image_path)
    return None
