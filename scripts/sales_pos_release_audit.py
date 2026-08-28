#!/usr/bin/env python3
"""Static release gate for the live POS add-line regression and cashier UX."""
from __future__ import annotations

import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []


def read(relative: str) -> str:
    path = ROOT / relative
    if not path.is_file():
        ERRORS.append(f'Falta {relative}')
        return ''
    return path.read_text(encoding='utf-8')


def require(condition: bool, message: str) -> None:
    if not condition:
        ERRORS.append(message)


route_source = read('routes/sales/core.py')
actions_source = read('routes/sales/actions.py')
retail_source = read('services/retail.py')
template = read('templates/sales/create_sales.html')
pos_css = read('static/css/sales_css/create_sales.css')
app_source = read('app.py')
shell = read('templates/layouts/left_bar.html')
left_js = read('static/js/left.js')
left_css = read('static/css/left.css')
company_settings = read('templates/company/settings.html')
transfer_create = read('templates/transfers/create.html')
reports_source = read('routes/reports/reports.py')
quotes_source = read('routes/sales/quotes.py')

try:
    tree = ast.parse(route_source)
except SyntaxError as exc:
    ERRORS.append(f'routes/sales/core.py no compila: {exc}')
    tree = ast.Module(body=[], type_ignores=[])

add_line = next((node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_add_line'), None)
require(add_line is not None, 'No existe _add_line')
if add_line is not None:
    sale_item_calls = [
        node for node in ast.walk(add_line)
        if isinstance(node, ast.Call)
        and ((isinstance(node.func, ast.Name) and node.func.id == 'SaleItem')
             or (isinstance(node.func, ast.Attribute) and node.func.attr == 'SaleItem'))
    ]
    require(len(sale_item_calls) == 1, '_add_line debe construir una sola línea SaleItem nueva')
    if sale_item_calls:
        keywords = {keyword.arg for keyword in sale_item_calls[0].keywords if keyword.arg}
        for required in {'sale', 'sale_id', 'product', 'product_id', 'variant', 'variant_id', 'warehouse', 'warehouse_id'}:
            require(required in keywords, f'SaleItem nuevo no asigna {required}; la relación puede quedar None antes del flush')

add_route = next((node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'add_to_cart'), None)
require(add_route is not None, 'No existe add_to_cart')
if add_route is not None:
    catches = []
    for handler in (node for node in ast.walk(add_route) if isinstance(node, ast.ExceptHandler)):
        if isinstance(handler.type, ast.Tuple):
            catches.extend(item.id for item in handler.type.elts if isinstance(item, ast.Name))
        elif isinstance(handler.type, ast.Name):
            catches.append(handler.type.id)
    require('BusinessRuleError' in catches, 'add_to_cart no captura reglas de negocio')
    require('NumericValueError' in catches, 'add_to_cart no captura cantidades/decimales inválidos')

require('if product is None:' in retail_source, 'resolve_sale_price vuelve a desreferenciar product sin validarlo')
require('El producto no pertenece a la empresa usada para calcular el precio' in retail_source, 'Falta validación tenant en resolve_sale_price')
require('El producto está desactivado o archivado' in retail_source, 'resolve_sale_price no bloquea productos desactivados/archivados')
require('El precio de venta resultante no puede ser negativo' in retail_source, 'resolve_sale_price permite un precio resultante negativo')
require('allowed_uoms = {' in route_source and '_compatible_uoms(product)' in route_source,
        '_add_line no valida la UOM contra las unidades realmente habilitadas del producto')
require('El producto fue desactivado o archivado' in route_source,
        '_add_line no vuelve a validar el estado del producto dentro de la transacción')
require('existing.product = product' in route_source and 'existing.warehouse = warehouse' in route_source,
        '_add_line no refresca relaciones de una línea existente antes de tarificarla')
require("old_state = {" in route_source and "for field, value in old_state.items()" in route_source,
        '_add_line no restaura la línea existente cuando falla precio/stock/reserva')
require('@app.errorhandler(NumericValueError)' in app_source, 'NumericValueError no tiene manejador HTTP seguro')
require('def _expects_json_response()' in app_source, 'Los formularios AJAX no tienen negociación JSON global')
require("'X-Requested-With': 'XMLHttpRequest'" in template, 'El POS no marca la operación de agregar como AJAX')
require('window.OrbisFeedback?.show' in template, 'El POS no usa el popup detallado para errores')
require('alert(' not in template, 'El POS conserva alert() nativo')
require('def _sale_cart_payload(sale):' in route_source, 'El POS no expone el estado canónico del carrito')
require('cart = _sale_cart_payload(sale)' in route_source and 'cart=cart' in route_source, 'Agregar producto no devuelve el carrito actualizado de forma transaccional')
require('sale.items.remove(item)' in route_source, 'Eliminar una línea puede recalcular con el artículo borrado todavía en memoria')
require('Unexpected POS add failure' in route_source and 'Unexpected POS remove failure' in route_source, 'Las mutaciones POS inesperadas no devuelven un error JSON seguro')
require('sale.client = client' in route_source and 'sale.price_list = selected' in route_source and 'sale.price_list = price_list' in route_source,
        'Cliente/lista de precios pueden quedar desfasados dentro de la misma petición')
require('Unexpected POS client assignment failure' in route_source,
        'La asignación de cliente no captura fallos inesperados con rollback seguro')
require('async function assignSaleClient(form)' in template and "posClientSelect.addEventListener('change'" in template,
        'Cambiar cliente sigue forzando una recarga completa o no actualiza el carrito por AJAX')
require('await fetchProducts(barcodeInput.value.trim())' in template,
        'Cambiar cliente no refresca los precios del catálogo según la nueva lista')
require('sale.promotion = promotion' in quotes_source and 'sale.promotion = None' in quotes_source,
        'Promociones cambian solo el FK y recalc_sale puede usar una relación obsoleta')
require('sale.promotion = None' in route_source,
        'recalc_sale no limpia la relación de una promoción vencida')
require("'can_checkout': bool(items)" in route_source,
        'El POS vuelve a bloquear una venta de consumidor final por no tener cliente')
require("'can_checkout': bool(items and sale.client_id)" not in route_source,
        'El carrito conserva la condición antigua que exigía cliente para cobrar')
require("if not sale.client_id:" not in actions_source,
        'finish_sale vuelve a exigir cliente para efectivo/tarjeta/transferencia')
require('ensure_credit_allowed(sale.client, credit)' in actions_source,
        'Las ventas a crédito dejaron de validar un cliente y su cupo')
require("Sale.query.filter_by(id=sale_id, company_id=company_id).with_for_update().first()" in actions_source,
        'Finalizar venta no bloquea la venta activa durante la transacción')
require("if sale.status == 'COMPLETED':" in actions_source,
        'Finalizar venta no protege contra reintentos de una venta ya completada')
require("Sale webhook scheduling failed after commit" in actions_source,
        'Un fallo de integración posterior al commit puede volver a presentarse como fallo de venta')
require('async function submitSale(form)' in template and "finishSaleForm?.addEventListener('submit'" in template,
        'Confirmar venta no usa el flujo AJAX transaccional del POS')
require('checkoutNeedsClient(form)' in template and 'credit > 0 || points > 0' in template,
        'La interfaz no diferencia ventas de mostrador de crédito/puntos')
require('Consumidor final · cliente opcional' in template,
        'La interfaz no explica que efectivo/tarjeta/transferencia admiten consumidor final')
require('function renderCart(cart)' in template, 'El POS sigue dependiendo de recargar la página para actualizar el pedido')
require('async function removeCartItem(form)' in template, 'Quitar producto no tiene flujo AJAX seguro')
require('function productAddUrl(productId)' in template and 'addProductUrlSentinel' in template,
        'El POS conserva una sustitución frágil para construir la URL de agregar')
require('function bindProgressSubmit(form, title, detail)' in template,
        'Finalizar/cotizar/apartar no tiene bloqueo de doble envío')
require('¡Venta Registrada!' not in template and '¡Cotización Guardada!' not in template,
        'La interfaz anuncia éxito antes de que el servidor confirme la operación')
require('role="group"' in template and 'role="button" tabindex=' not in template,
        'Las tarjetas POS conservan controles interactivos dentro de un falso botón')
require("card.addEventListener('click'" not in template,
        'La tarjeta completa vuelve a actuar como botón oculto y provoca altas accidentales')
require('cursor: default;' in pos_css.rsplit('.pos-page #product-grid > article.retail-pos-card {', 1)[-1].split('}', 1)[0],
        'La tarjeta anuncia un clic inexistente mediante cursor pointer')
require('id="pos-cart-toggle"' in template, 'Falta acceso visible al pedido en tablet vertical')
require('.pos-cart-open .pos-right' in pos_css, 'Falta el drawer del pedido para tablet vertical')
require('class="add-product-label">Agregar</span>' in template, 'La acción de la tarjeta depende solo de un icono')
require('sale-product-category-mark' in template and 'cart-empty-icon' in template, 'Las tarjetas o el carrito dependen del icono CDN para entenderse')
require('grid-column: 1 / -1;' in pos_css, 'El botón Agregar no ocupa una zona táctil clara')
require('min-height: 46px !important;' in pos_css, 'Falta tamaño táctil de controles POS en tablet')
require('grid-template-columns: 30px minmax(0, 1fr) auto 44px;' in pos_css,
        'La línea del pedido no reserva el ancho del botón táctil y puede desbordarse en tablet')
require('data-nav-section="sales"' in shell, 'El menú no declara grupos colapsables')
require("const navSectionKey = 'orbis-nav-sections-v3';" in left_js, 'El menú no conserva los grupos colapsados')
require("filter(section => !section.querySelector('.nav-item.active'))" in left_js, 'El menú inicial no prioriza la sección activa')
require('OrbisLocalIcons' in left_js and 'orbis-nav-icon' in left_js, 'El menú no renderiza iconos SVG locales cuando el CDN no está disponible')
for icon_alias in ('bi-cash-stack', 'bi-list', 'bi-lock-fill', 'bi-megaphone-fill', 'bi-pc-display', 'bi-box-arrow-right'):
    require(icon_alias in left_js, f'El sistema local de iconos no cubre {icon_alias}')
require('safeInternalUrl' in left_js and 'results.replaceChildren' in left_js, 'La búsqueda global no valida URLs/renderiza DOM seguro')
require('.nav-section.is-collapsed .nav-items' in left_css, 'Falta estilo del menú colapsable')
require('.nav-icon > .orbis-nav-icon' in left_css, 'Falta el estilo del sistema de iconos SVG local')
require('app.logger.propagate = False' in app_source, 'Los logs de Flask pueden duplicarse por propagación')
require('app.logger.removeHandler(default_handler)' in app_source, 'No se elimina el handler por defecto de Flask')
require('logging.basicConfig' not in reports_source, 'El módulo de reportes vuelve a configurar el logger global')
require('alert(' not in company_settings, 'Configuración de empresa conserva alert() nativo')
require('alert(' not in transfer_create, 'Transferencias conserva alert() nativo')
require('window.OrbisFeedback?.show' in company_settings, 'Configuración de empresa no usa feedback detallado')
require('window.OrbisFeedback?.show' in transfer_create, 'Transferencias no usa feedback detallado')

if ERRORS:
    print('SALES_POS_AUDIT: FAILED', file=sys.stderr)
    for error in ERRORS:
        print(f'- {error}', file=sys.stderr)
    raise SystemExit(1)

print('SALES_POS_AUDIT: OK')
print('Verified walk-in checkout, transactional finish, ORM relationships, cart mutations, feedback, tablet shell, touch cards and navigation.')
