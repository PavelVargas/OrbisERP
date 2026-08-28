"""Strict validation helpers for customer-managed files.

The browser-supplied MIME type is metadata, not a security boundary. These
helpers validate simple signatures/containers and return a canonical MIME type
that OrbisERP can safely persist and serve with nosniff enabled.
"""
from __future__ import annotations

from io import BytesIO
from zipfile import BadZipFile, ZipFile

CANONICAL_MIME = {
    'pdf': 'application/pdf',
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'webp': 'image/webp',
    'csv': 'text/csv',
    'txt': 'text/plain',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
}


def _looks_textual(data: bytes) -> bool:
    if b'\x00' in data:
        return False
    sample = data[:65536]
    for encoding in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
        try:
            sample.decode(encoding)
            return True
        except UnicodeDecodeError:
            continue
    return False


def validate_document_bytes(data: bytes, extension: str) -> str:
    """Validate content for an allowed document extension and return MIME.

    Raises ValueError for empty, disguised or structurally invalid content.
    This is intentionally conservative; unsupported formats should be added
    explicitly rather than accepted from user-controlled MIME metadata.
    """
    extension = (extension or '').lower().lstrip('.')
    mime = CANONICAL_MIME.get(extension)
    if not mime:
        raise ValueError('Tipo de archivo no permitido.')
    if not data:
        raise ValueError('El archivo está vacío.')

    if extension == 'pdf' and not data.startswith(b'%PDF-'):
        raise ValueError('El archivo no contiene un PDF válido.')
    if extension == 'png' and not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('El archivo no contiene una imagen PNG válida.')
    if extension in {'jpg', 'jpeg'} and not data.startswith(b'\xff\xd8\xff'):
        raise ValueError('El archivo no contiene una imagen JPEG válida.')
    if extension == 'webp' and not (len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP'):
        raise ValueError('El archivo no contiene una imagen WEBP válida.')
    if extension in {'txt', 'csv'} and not _looks_textual(data):
        raise ValueError('El archivo de texto contiene datos binarios no válidos.')
    if extension in {'xlsx', 'docx'}:
        try:
            with ZipFile(BytesIO(data)) as archive:
                names = set(archive.namelist())
                if '[Content_Types].xml' not in names:
                    raise ValueError('El documento Office no contiene una estructura válida.')
                required_prefix = 'xl/' if extension == 'xlsx' else 'word/'
                if not any(name.startswith(required_prefix) for name in names):
                    raise ValueError('El contenido no coincide con la extensión del documento.')
                # Check archive CRCs without extracting paths to disk.
                if archive.testzip() is not None:
                    raise ValueError('El documento Office está dañado.')
        except BadZipFile as exc:
            raise ValueError('El documento Office no es válido.') from exc

    return mime
