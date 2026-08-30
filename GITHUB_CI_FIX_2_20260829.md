# GitHub CI fix 2 · 2026-08-29

Correcciones aplicadas a los fallos observados en `pytest -q -rs --ignore=tests/e2e`:

1. Nueva migración `b4d8f2c7a930` que alinea `companies` con el modelo y crea:
   - `is_readonly`
   - `storage_limit`
   - `current_storage_usage`
2. Eliminación de los 7 templates legacy duplicados prohibidos por el release gate.
3. Regla final del POS con `cursor: default;` para que las tarjetas no prometan un click oculto.
4. Actualización del contrato visual obsoleto: el primario canónico del POS es naranja `#f2672a`, no azul `#2563eb`.

Para una copia de trabajo existente, los templates legacy deben eliminarse con `git rm`; extraer un ZIP encima de una carpeta existente no elimina archivos que ya estaban allí.
