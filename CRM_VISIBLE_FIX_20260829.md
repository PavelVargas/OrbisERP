# CRM visible dossier fix · 2026-08-29

Corrección puntual para el CRM cuando el panel derecho quedaba bloqueado en “Cargando cliente…”.

## Causa

La ficha cargaba simultáneamente colecciones de ventas e interacciones mediante `joinedload`. En clientes con historial, el JOIN podía multiplicar las filas (ventas × interacciones), haciendo que el endpoint de detalle tardara demasiado o pareciera bloqueado.

## Cambios

- El detalle del cliente se construye con consultas independientes y acotadas.
- Ventas se resumen directamente en SQL (`SUM`, `COUNT`, `AVG`, `MAX`).
- Interacciones se consultan aparte, ordenadas y limitadas a las 120 más recientes.
- Tareas pendientes se consultan aparte y de forma acotada.
- El CRM ya no intenta actualizar tasas de moneda por red al abrir una ficha; usa la tasa local disponible y un fallback de presentación.
- La primera ficha se precarga en el HTML inicial para que la información aparezca inmediatamente.
- Cambiar de cliente conserva AJAX, con cancelación de solicitudes anteriores y timeout de 12 s.
- El loader dejó de cubrir un panel gigante; ahora es un indicador compacto y no oculta la información ya visible.
- Si una llamada falla o excede el timeout, aparece un estado de error recuperable en lugar de un spinner infinito.

## Contratos conservados

No se cambiaron endpoints públicos, IDs DOM, nombres de campos, etapas CRM ni acciones de tareas/interacciones.
