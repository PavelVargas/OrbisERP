# Checklist de salida comercial — OrbisERP 2026.08.13

Este documento separa lo que el software puede verificar de lo que exige una decisión operativa o externa.

## Antes de desplegar

- [ ] Ejecutar `python scripts/static_release_audit.py` y exigir resultado OK.

- [ ] Ejecutar `pip install -r requirements.txt` y `python -m pip check`.
- [ ] Ejecutar `flask --app app db upgrade`; después confirmar que `flask --app app db current` coincide con `python scripts/release_identity.py` (head de este paquete: `c6e1a4f8b207`).
- [ ] Ejecutar `pytest -q -rs --ignore=tests/e2e` contra PostgreSQL de pruebas.
- [ ] Ejecutar smoke E2E de Playwright o confirmar que GitHub Actions terminó verde.
- [ ] Ejecutar `flask --app app audit-integrity` y `flask --app app validate-integrity`.
- [ ] Configurar un `SECRET_KEY` aleatorio fuerte y secretos independientes para billing, cron e incident webhook.
- [ ] Configurar `PUBLIC_BASE_URL=https://...`, TLS en el reverse proxy y `TRUST_PROXY=1` solo detrás de ese proxy.
- [ ] Configurar SMTP TLS y verificar entrega de correos de recuperación/verificación.
- [ ] Mantener `FISCAL_MODE=disabled` mientras no exista certificación fiscal aplicable.
- [ ] Si `PUBLIC_REGISTRATION=1`, publicar Términos/Privacidad HTTPS revisados profesionalmente y fijar `LEGAL_VERSION`.

## Datos y recuperación

- [ ] Crear backup completo antes del upgrade.
- [ ] Configurar `BACKUP_MIRROR_DIR` o un proceso externo que copie respaldos fuera del servidor.
- [ ] Ejecutar `scripts/verify_backup.sh` sobre el último respaldo.
- [ ] Ejecutar un `scripts/restore_drill.sh` sobre una base exclusivamente de pruebas antes del primer lanzamiento y después de cambios mayores.
- [ ] Verificar espacio de disco y permisos de `STORAGE_ROOT`, uploads, logs y backups.

## Operación

- [ ] Configurar monitor externo para `/operations/health/live` y `/operations/health/ready`.
- [ ] Configurar `ERROR_WEBHOOK_URL`/`ERROR_WEBHOOK_SECRET` o una plataforma equivalente de incidentes.
- [ ] Ejecutar `flask --app app maintenance-check --strict` y resolver cualquier fallo.
- [ ] Programar `maintenance-clean` y revisión de backups según `MAINTENANCE.md`.
- [ ] Documentar contacto de soporte, ventana de mantenimiento y responsable de restauración.

## Piloto y General Availability

- [ ] Ejecutar un piloto con clientes reales y registrar incidencias por versión de release.
- [ ] Confirmar al menos un ciclo real completo: venta → caja → stock → devolución; compra → recepción → CxP; transferencia; documentos; CRM; auditoría.
- [ ] No lanzar como facturación fiscal si `FISCAL_MODE=disabled`.
- [ ] Si se vende Electron como aplicación instalable, completar firma de binarios, instalador y política de actualización para cada plataforma objetivo.


## Validación Retail 2.0

- [ ] Probar producto simple y producto con variantes.
- [ ] Probar una UOM de empaque específica (ej. caja x24) en compra, recepción, POS y reposición.
- [ ] Probar venta fraccionaria para un producto `WEIGHT`.
- [ ] Probar lote/FEFO y devolución a Disponible/Cuarentena/Dañado.
- [ ] Probar serial/IMEI, venta, devolución y reclamación/reemplazo de garantía.
- [ ] Probar lista de precios y regla por volumen.
- [ ] Probar pago mixto y, si están activos, crédito/gift card/fidelización.
- [ ] Probar terminal POS y ticket térmico 58/80 mm.
- [ ] Probar API key/scopes y firma HMAC de webhook en staging.
