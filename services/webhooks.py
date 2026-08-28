"""Best-effort outbound webhooks with HTTPS/HMAC and SSRF guardrails."""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import socket
import threading
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from flask import current_app

from models.retail import OutboundWebhook
from services.time_utils import utcnow


def validate_webhook_url(value: str) -> str:
    url = (value or '').strip()
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('El webhook debe usar una URL HTTPS pública sin credenciales embebidas.')
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError('No fue posible resolver el dominio del webhook.') from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise ValueError('El webhook debe apuntar a una dirección pública.')
    return url


def emit_event(company_id: int, event_type: str, payload: dict) -> None:
    """Queue a lightweight best-effort delivery after the business transaction commits."""
    rows = OutboundWebhook.query.filter_by(company_id=company_id, active=True).all()
    targets = []
    for row in rows:
        events = {item.strip() for item in (row.event_types or '').split(',') if item.strip()}
        if '*' in events or event_type in events:
            targets.append((row.id, row.target_url, row.secret))
    if not targets:
        return
    app = current_app._get_current_object()
    envelope = {
        'event': event_type,
        'occurred_at': utcnow().isoformat() + 'Z',
        'company_id': int(company_id),
        'data': payload,
    }
    body = json.dumps(envelope, separators=(',', ':'), ensure_ascii=False).encode('utf-8')

    def worker():
        for webhook_id, target_url, secret in targets:
            try:
                url = validate_webhook_url(target_url)
                signature = hmac.new(secret.encode('utf-8'), body, hashlib.sha256).hexdigest()
                req = Request(url, data=body, method='POST', headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'OrbisERP-Webhooks/1.0',
                    'X-OrbisERP-Event': event_type,
                    'X-OrbisERP-Signature': f'sha256={signature}',
                })
                with urlopen(req, timeout=5) as response:
                    if int(getattr(response, 'status', 200)) >= 400:
                        raise RuntimeError(f'HTTP {response.status}')
            except Exception:
                app.logger.exception('Webhook %s failed for event %s', webhook_id, event_type)

    threading.Thread(target=worker, name=f'orb-webhook-{event_type}', daemon=True).start()
