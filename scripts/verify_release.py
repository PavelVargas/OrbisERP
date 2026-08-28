#!/usr/bin/env python3
"""Fail closed if a generated OrbisERP source release contains runtime/secrets."""
from __future__ import annotations

import argparse
from pathlib import PurePosixPath
import stat
import zipfile

FORBIDDEN_PARTS = {
    '.git', '.venv', '.auditvenv', 'venv', 'node_modules', '__pycache__', '.pytest_cache',
    '.tox', '.nox', '.mypy_cache', '.ruff_cache',
    'logs', 'backups', 'storage', 'instance', 'htmlcov',
}
FORBIDDEN_NAMES = {'.env', '.coverage', '.DS_Store'}
FORBIDDEN_SUFFIXES = {'.pyc', '.pyo', '.db', '.sqlite', '.sqlite3', '.p12', '.pfx', '.key'}
# Keep marker fragments split so this verifier does not flag its own source.
PRIVATE_KEY_MARKERS = tuple(
    b'-----BEGIN ' + kind + b'-----'
    for kind in (
        b'PRIVATE KEY', b'RSA PRIVATE KEY', b'EC PRIVATE KEY',
        b'OPENSSH PRIVATE KEY',
    )
)

REQUIRED_ARCHIVE_SUFFIXES = {
    'app.py', 'requirements.txt',
    'templates/layouts/app_head_assets.html',
    'templates/sales/create_sales.html',
    'templates/products/products.html',
    'scripts/build_release.py',
}
MINIMUM_ARCHIVE_ENTRIES = 300
MINIMUM_TEMPLATE_ENTRIES = 80
MINIMUM_STATIC_ENTRIES = 100
MINIMUM_ROUTE_ENTRIES = 25


def violation(name: str, info: zipfile.ZipInfo) -> str | None:
    if not name or name.startswith(('/', '\\')) or '\\' in name or '\x00' in name:
        return f'ruta no portable: {name!r}'
    path = PurePosixPath(name)
    if '..' in path.parts:
        return f'ruta transversal: {name}'
    if stat.S_ISLNK((info.external_attr >> 16) & 0xFFFF):
        return f'enlace simbólico: {name}'

    parts = set(path.parts)
    if parts & FORBIDDEN_PARTS:
        # Empty placeholders for runtime directories are intentionally allowed.
        if path.name == '.gitkeep' and any(part in {'logs', 'backups', 'storage'} for part in path.parts):
            return None
        return f'directorio runtime: {name}'
    if path.name in FORBIDDEN_NAMES:
        return f'archivo secreto/runtime: {name}'
    if path.suffix.lower() in FORBIDDEN_SUFFIXES:
        return f'archivo sensible/runtime: {name}'
    if 'static' in path.parts and 'uploads' in path.parts and path.name != '.gitkeep':
        return f'archivo de cliente: {name}'
    if path.name.startswith('.env') and path.name not in {'.env.example', '.env.production.example'}:
        return f'secreto de entorno: {name}'
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('archive')
    args = parser.parse_args()
    with zipfile.ZipFile(args.archive) as archive:
        bad_crc = archive.testzip()
        infos = archive.infolist()
        names = [info.filename for info in infos]
        violations = [reason for info in infos if (reason := violation(info.filename, info))]
        roots = {PurePosixPath(name).parts[0] for name in names if PurePosixPath(name).parts}
        if len(roots) != 1:
            violations.append(f'el ZIP debe tener una sola raíz, encontradas: {sorted(roots)}')
        root = next(iter(roots), '')
        relative_names = {
            name[len(root) + 1:] for name in names
            if root and name.startswith(root + '/')
        }
        missing = sorted(REQUIRED_ARCHIVE_SUFFIXES - relative_names)
        if missing:
            violations.append('release incompleto; faltan: ' + ', '.join(missing))
        if len(names) < MINIMUM_ARCHIVE_ENTRIES:
            violations.append(f'release incompleto; solo {len(names)} entradas')
        template_count = sum('/templates/' in '/' + name for name in names)
        static_count = sum('/static/' in '/' + name for name in names)
        route_count = sum('/routes/' in '/' + name for name in names)
        if template_count < MINIMUM_TEMPLATE_ENTRIES:
            violations.append(f'release incompleto; solo {template_count} plantillas')
        if static_count < MINIMUM_STATIC_ENTRIES:
            violations.append(f'release incompleto; solo {static_count} estaticos')
        if route_count < MINIMUM_ROUTE_ENTRIES:
            violations.append(f'release incompleto; solo {route_count} rutas')
        for info in infos:
            if info.file_size > 2 * 1024 * 1024 or info.is_dir():
                continue
            data = archive.read(info)
            if any(marker in data for marker in PRIVATE_KEY_MARKERS):
                violations.append(f'clave privada incrustada: {info.filename}')
    if bad_crc:
        raise SystemExit(f'ZIP corrupto: {bad_crc}')
    if violations:
        raise SystemExit('Release rechazado:\n- ' + '\n- '.join(violations[:20]))
    print(f'Release verificado: {len(names)} entradas, sin secretos/runtime.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
