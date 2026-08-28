#!/usr/bin/env python3
"""Create a reproducible, customer-safe OrbisERP source release ZIP."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {
    '.git', '.venv', '.auditvenv', 'venv', 'node_modules', '__pycache__', '.pytest_cache',
    '.tox', '.nox', '.mypy_cache', '.ruff_cache',
    'logs', 'backups', 'storage', 'dist', 'instance', 'htmlcov',
}
EXCLUDED_FILES = {
    '.env', '.DS_Store', '.coverage',
    'REPAIR_REPORT.json', 'SECOND_PASS_STATUS.txt',
    'POLISH_REPORT.txt', 'POLISH_STATUS.txt',
    # Historical engineering reports are useful in the workspace but do not
    # belong in a customer-facing release. Keep only the current audit and
    # current validation evidence.
    'AUDIT_CLIENT_20260826.md',
    'AUDIT_CLIENT_FINAL_20260826.md',
    'AUDIT_CUSTOMER_HARDENING_20260826.md',
    'AUDIT_VERIFIED_20260827.md',
    'FIXES_20260823.md',
    'FIXES_APPLIED.md',
    'FIXES_POS_20260825.md',
    'FIXES_TRANSFER_SCANNER_20260825.md',
    'POS_CATALOG_VALIDATION.json',
    'POS_UI_VALIDATION.json',
    'POS_VISUAL_VALIDATION_20260827.json',
    'SCANNER_DARK_FIX_REPORT.json',
    'SCANNER_DARK_VALIDATION.json',
}
EXCLUDED_SUFFIXES = {'.pyc', '.pyo', '.zip', '.sqlite', '.sqlite3', '.db'}
RUNTIME_PREFIXES = (Path('static/uploads'),)
PLACEHOLDERS = (
    'static/uploads/.gitkeep', 'storage/.gitkeep', 'logs/.gitkeep', 'backups/.gitkeep',
)
FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)

# Refuse to produce a misleading partial archive. These paths and minimum
# counts represent the application source tree, not runtime/user data.
REQUIRED_SOURCE_PATHS = (
    Path('app.py'), Path('requirements.txt'), Path('templates'), Path('static'),
    Path('routes'), Path('models'), Path('services'), Path('migrations'),
    Path('templates/layouts/app_head_assets.html'),
    Path('templates/sales/create_sales.html'),
    Path('templates/products/products.html'),
)
MINIMUM_RELEASE_FILES = 300
MINIMUM_TEMPLATE_FILES = 80
MINIMUM_STATIC_FILES = 100
MINIMUM_ROUTE_FILES = 25

# Documented for release wrappers that import this module.
SENSITIVE_RELEASE_EXCLUDES = {
    '.git', '.env', '.env.local', '.venv', '.auditvenv', 'venv', '.pytest_cache', '__pycache__',
    'logs', 'instance', '.coverage', 'htmlcov', 'static/uploads',
}


def include(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if path.is_symlink():
        return False
    if any(part in EXCLUDED_DIRS for part in rel.parts):
        return False
    if path.name in EXCLUDED_FILES or path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    if path.name.startswith('.env') and path.name not in {'.env.example', '.env.production.example'}:
        return False
    if any(rel == prefix or prefix in rel.parents for prefix in RUNTIME_PREFIXES):
        return False
    return path.is_file()


def _zip_info(archive_name: str, executable: bool = False) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(archive_name, FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    mode = 0o755 if executable else 0o644
    info.external_attr = (mode & 0xFFFF) << 16
    return info


def _forbidden_member(name: str) -> bool:
    path = Path(name)
    return (
        '/.git/' in f'/{name}'
        or path.name == '.env'
        or '__pycache__' in path.parts
        or path.suffix.lower() in {'.pyc', '.pyo', '.db', '.sqlite', '.sqlite3'}
        or '..' in path.parts
        or name.startswith(('/', '\\'))
        or '\\' in name
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=str(ROOT.parent / 'orbiserp_release.zip'))
    parser.add_argument('--root-name', default='OrbisERP')
    args = parser.parse_args()
    output = Path(args.output).resolve()
    root_name = ''.join(ch for ch in args.root_name if ch.isalnum() or ch in {'-', '_'}) or 'OrbisERP'
    output.parent.mkdir(parents=True, exist_ok=True)

    missing = [str(path) for path in REQUIRED_SOURCE_PATHS if not (ROOT / path).exists()]
    if missing:
        raise SystemExit('Proyecto incompleto; faltan rutas obligatorias: ' + ', '.join(missing))

    files = sorted(path for path in ROOT.rglob('*') if include(path))
    category_counts = {
        'templates': sum(1 for path in files if 'templates' in path.relative_to(ROOT).parts),
        'static': sum(1 for path in files if 'static' in path.relative_to(ROOT).parts),
        'routes': sum(1 for path in files if 'routes' in path.relative_to(ROOT).parts),
    }
    if len(files) < MINIMUM_RELEASE_FILES:
        raise SystemExit(f'Proyecto incompleto: solo {len(files)} archivos publicables')
    if category_counts['templates'] < MINIMUM_TEMPLATE_FILES:
        raise SystemExit(f'Proyecto incompleto: solo {category_counts["templates"]} plantillas')
    if category_counts['static'] < MINIMUM_STATIC_FILES:
        raise SystemExit(f'Proyecto incompleto: solo {category_counts["static"]} archivos estaticos')
    if category_counts['routes'] < MINIMUM_ROUTE_FILES:
        raise SystemExit(f'Proyecto incompleto: solo {category_counts["routes"]} archivos de rutas')

    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            rel = path.relative_to(ROOT).as_posix()
            executable = rel.startswith('scripts/') and path.suffix in {'.sh', '.py'}
            info = _zip_info(f'{root_name}/{rel}', executable=executable)
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        for placeholder in PLACEHOLDERS:
            archive.writestr(_zip_info(f'{root_name}/{placeholder}'), b'')

    with zipfile.ZipFile(output) as archive:
        bad = archive.testzip()
        names = archive.namelist()
    if bad:
        raise SystemExit(f'ZIP corrupto: {bad}')
    forbidden = [name for name in names if _forbidden_member(name)]
    if forbidden:
        raise SystemExit(f'El release contiene archivos prohibidos: {forbidden[:5]}')

    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(f'Release: {output}')
    print(f'Archivos: {len(names)}')
    print(f'Plantillas: {category_counts["templates"]}')
    print(f'Estaticos: {category_counts["static"]}')
    print(f'Rutas: {category_counts["routes"]}')
    print(f'SHA-256: {digest}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
