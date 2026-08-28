from types import SimpleNamespace

from flask import Flask

from services.product_images import product_image_url


def test_product_image_url_uses_local_upload():
    app = Flask(__name__)
    with app.test_request_context('/'):
        product = SimpleNamespace(image_path='uploads/company_2/products/a.webp', image_url='https://example.com/ignored.png')
        assert product_image_url(product).endswith('/static/uploads/company_2/products/a.webp')


def test_product_image_url_ignores_remote_url_without_local_photo():
    app = Flask(__name__)
    with app.test_request_context('/'):
        product = SimpleNamespace(image_path=None, image_url='https://example.com/ignored.png')
        assert product_image_url(product) is None
