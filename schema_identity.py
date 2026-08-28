"""Schema identity helpers with no Flask/SQLAlchemy dependency.

Alembic's migration graph is the source of truth for the schema revision the
running code expects. Keeping this logic dependency-free lets config.py,
release tooling, CI and startup all use the same answer.
"""
from __future__ import annotations

import ast
from pathlib import Path


def _literal_assignment(source: str, name: str):
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    return None


def discover_alembic_head(base_dir: str | Path) -> str:
    versions_dir = Path(base_dir) / 'migrations' / 'versions'
    revisions: set[str] = set()
    referenced: set[str] = set()

    for path in sorted(versions_dir.glob('*.py')):
        source = path.read_text(encoding='utf-8')
        revision = _literal_assignment(source, 'revision')
        down_revision = _literal_assignment(source, 'down_revision')
        if not isinstance(revision, str) or not revision:
            continue
        if revision in revisions:
            raise RuntimeError(f'Revisión Alembic duplicada: {revision}')
        revisions.add(revision)
        if isinstance(down_revision, str) and down_revision:
            referenced.add(down_revision)
        elif isinstance(down_revision, (tuple, list)):
            referenced.update(item for item in down_revision if isinstance(item, str) and item)

    heads = sorted(revisions - referenced)
    if len(heads) != 1:
        raise RuntimeError(f'Se esperaba un único head Alembic y se encontraron: {heads}')
    return heads[0]
