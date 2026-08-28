#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r'^\d{4}\.\d{2}\.\d+$')
REV_RE = re.compile(r"^revision\s*=\s*['\"]([^'\"]+)['\"]", re.M)
DOWN_RE = re.compile(r"^down_revision\s*=\s*(?:['\"]([^'\"]+)['\"]|None)", re.M)


def fail(message: str) -> None:
    print(f'ERROR: {message}', file=sys.stderr)
    raise SystemExit(1)


def migration_head() -> str:
    revisions: set[str] = set()
    down_revisions: set[str] = set()
    for path in sorted((ROOT / 'migrations' / 'versions').glob('*.py')):
        source = path.read_text(encoding='utf-8')
        revision_match = REV_RE.search(source)
        if not revision_match:
            continue
        revision = revision_match.group(1)
        if revision in revisions:
            fail(f'revisión Alembic duplicada: {revision}')
        revisions.add(revision)
        down_match = DOWN_RE.search(source)
        if down_match and down_match.group(1):
            down_revisions.add(down_match.group(1))
    heads = sorted(revisions - down_revisions)
    if len(heads) != 1:
        fail(f'se esperaba un único head Alembic y se encontraron: {heads}')
    return heads[0]


def main() -> int:
    version = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
    if not VERSION_RE.fullmatch(version):
        fail(f'VERSION inválida: {version!r}')

    config = (ROOT / 'config.py').read_text(encoding='utf-8')
    if 'EXPECTED_SCHEMA_REVISION = discover_alembic_head(BASE_DIR)' not in config:
        fail('config.py debe derivar EXPECTED_SCHEMA_REVISION del grafo Alembic')
    if 'from schema_identity import discover_alembic_head' not in config:
        fail('config.py no importa discover_alembic_head')
    head = migration_head()

    expected_titles = {
        'README.md': f'# OrbisERP {version}',
        'COMMERCIAL_RELEASE.md': f'# OrbisERP {version}',
        'RELEASE_CHECKLIST.md': f'# Checklist de salida comercial — OrbisERP {version}',
    }
    for relative, prefix in expected_titles.items():
        first_line = (ROOT / relative).read_text(encoding='utf-8').splitlines()[0].strip()
        if not first_line.startswith(prefix):
            fail(f'{relative} no está sincronizado con VERSION={version}: {first_line!r}')

    print(f'OK release={version} alembic_head={head}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
