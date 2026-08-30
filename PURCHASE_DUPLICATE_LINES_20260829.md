# Ordenes de compra: lineas duplicadas independientes

La captura de productos en la orden de compra ahora conserva cada alta como una linea independiente.

## Comportamiento

- El mismo producto puede aparecer dos o mas veces en la misma orden.
- No se acumula automaticamente la cantidad sobre una linea existente.
- Cada linea conserva su propia cantidad, costo, variante, unidad e impuesto.
- El flujo continuo se mantiene: Producto -> Cantidad -> Enter -> nueva linea.
- Los totales siguen calculandose sobre todas las lineas de la orden.

Ejemplo:

- Radiador / 1 ud / RD$ 7,800
- Radiador / 2 ud / RD$ 7,500
- Radiador / 1 ud / RD$ 8,000

Las tres entradas permanecen separadas.
