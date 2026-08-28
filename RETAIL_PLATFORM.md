# OrbisERP Retail Platform 2.0

OrbisERP mantiene un único núcleo ERP/POS y activa capacidades retail según la empresa. No existen ediciones separadas para ropa, ferretería o tecnología: la configuración define qué herramientas aparecen y las operaciones comparten ventas, inventario, compras, caja, clientes, auditoría y seguridad.

## Perfiles y capacidades

`Configuración Retail` permite adaptar la empresa sin duplicar módulos. Entre las capacidades introducidas en Retail 2.0 (vigentes en 2026.08.10) están:

- sucursales y terminales POS;
- variantes y atributos de producto;
- unidades de medida y conversiones específicas por producto;
- cantidades fraccionarias para peso/medida;
- múltiples códigos de barras;
- listas de precios y reglas por cantidad;
- proveedores por producto;
- kits/combos;
- lotes, vencimientos y FEFO;
- seriales/IMEI y garantías;
- crédito de cliente, apartados, gift cards y fidelización;
- pagos mixtos;
- promociones avanzadas;
- reposición y costeo;
- cuarentena/dañados y devoluciones trazables;
- API v1, API keys y webhooks firmados;
- ticket térmico 58/80 mm.

## Producto como centro

La ficha de producto concentra la administración comercial y logística. Variantes, precios, códigos, inventario, lotes/series, proveedores y composición de kits se gestionan desde el mismo contexto de producto. El menú principal no replica pantallas para cada capacidad.

## Unidades de medida

Las conversiones de empaque son específicas del producto. Ejemplo:

- Coca Cola: `1 caja = 24 unidades`;
- Leche: `1 caja = 12 unidades`;
- Tornillo: `1 caja = 100 unidades`.

POS, compras y reposición convierten siempre a la unidad base antes de afectar inventario. Las cantidades físicas usan precisión decimal de hasta tres posiciones donde el producto lo permite; los productos serializados continúan exigiendo cantidades enteras.

## Trazabilidad

Los productos pueden operar sin tracking, por lote o por serial. Las devoluciones preservan lote/serial original y permiten destino Disponible, Cuarentena, Dañado o sin reintegro. El Centro de Calidad controla la liberación o descarte posterior. Las garantías mantienen historial de serial y, si existe reemplazo, registran el serial sustituto.

## POS y clientes

El POS soporta almacén/sucursal/terminal, variantes, UOM, lista de precios, promociones y pagos múltiples. Crédito, gift cards y puntos de fidelización pueden participar en el pago según la configuración de la empresa.

## Alcance externo

La plataforma queda preparada para integraciones mediante API/webhooks. Shopify, WooCommerce, pasarelas de pago y fiscalidad oficial requieren credenciales/proveedores externos y pruebas específicas de cada integración. `FISCAL_MODE=disabled` debe mantenerse mientras no exista certificación fiscal aplicable.
