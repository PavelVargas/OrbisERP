# POS · Efectivo recibido y cambio · 2026-08-29

## Objetivo

OrbisERP ahora distingue entre el importe de efectivo aplicado a una venta y el dinero físico entregado por el cliente. Esto permite calcular, guardar, auditar y reimprimir el cambio real sin alterar ventas, ingresos ni conciliación.

## Flujo de caja

- En `Efectivo`, el POS muestra `Efectivo recibido`, `A cobrar` y `Cambio`.
- El cajero introduce el efectivo físico recibido.
- El cambio se calcula en tiempo real.
- No se permite confirmar si el efectivo recibido es menor que el importe que corresponde pagar en efectivo.
- Si un cliente entrega exactamente el total, el cambio queda en 0.00.
- En pago dividido, el cálculo usa únicamente la porción configurada como efectivo.

Ejemplo: venta RD$7,800.00, recibido RD$8,000.00 -> cambio RD$200.00. La venta y el pago aplicado siguen siendo RD$7,800.00.

## Persistencia

Se añadieron a `sales`:

- `cash_received NUMERIC(12,2) NULL`: efectivo físico entregado.
- `cash_change NUMERIC(12,2) NOT NULL DEFAULT 0`: cambio devuelto.

Migración Alembic: `c6e1a4f8b207_sale_cash_tender.py`, revisa `b4d8f2c7a930`.

Para desplegar:

```bash
flask --app app db upgrade
```

## Documentos y auditoría

- El ticket térmico imprime el efectivo recibido y el cambio real.
- El detalle de venta muestra ambos valores en la pestaña Pagos.
- El PDF de factura incluye ambos datos cuando hubo efectivo.
- Ventas históricas sin estos campos siguen funcionando: si un cliente/API antiguo no envía `cash_received`, el backend asume pago exacto y cambio 0.00.

## Validación

- Python compile: OK.
- Jinja: 118/118.
- Static release audit: OK.
- UI consistency audit: OK.
- Client UI audit: OK.
- Pruebas focalizadas de checkout/retail/POS: 35 passed.
