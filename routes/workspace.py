from services.numeric import NumericValueError, bounded_decimal, finite_decimal, finite_int
from services.time_utils import utcnow
import os
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from flask import Blueprint, Response, abort, current_app, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from sqlalchemy import String, cast, func, or_
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from db import db
from models.backoffice import AppNotification, Expense
from models.category.category import Category
from models.client.client import Client
from models.products.products import Product, ProductType
from models.productivity import CashSession, CompanyDocument, DocumentFolder, NotificationRule, Promotion, SalesTax
from models.purchase.purchase_order import PurchaseOrder
from models.sales.sales import Sale
from models.supplier.supplier import Supplier
from models.user.user import User
from services.barcodes import barcode_svg
from services.file_validation import CANONICAL_MIME, validate_document_bytes
from services.notification_rules import (CUSTOM_SOURCES, DEFAULT_RULES, OPERATORS, RULE_DESCRIPTIONS, RULE_LABELS, ensure_default_rules, evaluate_notification_rules)


workspace_bp = Blueprint('workspace_bp', __name__, url_prefix='/workspace')
ALLOWED_DOCUMENT_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'webp', 'csv', 'xlsx', 'docx', 'txt'}
ENTITY_MODELS = {'PRODUCT': Product, 'CLIENT': Client, 'SUPPLIER': Supplier}
TRASH_FOLDER_NAME = '.orbis-trash'

DOCUMENT_ENTITY_MODELS = {
    'PRODUCT': Product, 'CLIENT': Client, 'SUPPLIER': Supplier, 'SALE': Sale,
    'PURCHASE': PurchaseOrder, 'EXPENSE': Expense,
}


def _company_id():
    company_id = session.get('company_id')
    if not company_id:
        abort(401)
    return company_id


def _user():
    return db.session.get(User, session.get('user_id'))


def _safe_display_name(value, max_length):
    value = (value or '').strip()
    if not value or len(value) > max_length or any(ch in value for ch in ('\r', '\n', '\x00', '/', '\\')):
        raise ValueError('El nombre contiene caracteres no permitidos.')
    return value


def _document_path(document):
    root = Path(current_app.config['STORAGE_ROOT']).resolve()
    path = (root / document.stored_name).resolve()
    if root not in path.parents:
        abort(403)
    return path


def _document_entity(entity_type, entity_id, company_id):
    entity_type = (entity_type or 'COMPANY').upper()[:40]
    if entity_type == 'COMPANY':
        return 'COMPANY', None
    model = DOCUMENT_ENTITY_MODELS.get(entity_type)
    if not model or not entity_id:
        raise ValueError('Selecciona un tipo e ID relacionado válidos.')
    row = model.query.filter_by(id=entity_id, company_id=company_id).first()
    if not row:
        raise ValueError('El registro relacionado no existe en esta empresa.')
    return entity_type, entity_id


@workspace_bp.get('/executive')
def executive_dashboard():
    # Compatibilidad: el panel ejecutivo se consolidó en el resumen principal.
    return redirect(url_for('dashboard_bp.dashboard'))


@workspace_bp.get('/search')
def global_search():
    company_id = _company_id()
    user = _user()
    q = (request.args.get('q') or '').strip()
    if len(q) < 2 or not user:
        return jsonify(results=[])
    term = f'%{q}%'
    results = []

    if user.has_permission('products.view'):
        products = Product.query.filter(
            Product.company_id == company_id, Product.archived_at.is_(None),
            or_(Product.name.ilike(term), Product.sku.ilike(term))
        ).order_by(Product.name).limit(6).all()
        for item in products:
            results.append({'type': 'Producto', 'title': item.name, 'subtitle': item.sku, 'icon': 'bi-box-seam',
                            'url': url_for('products_bp.view_product', id=item.id)})

    if user.has_permission('clients.view'):
        clients = Client.query.filter(
            Client.company_id == company_id, Client.archived_at.is_(None),
            or_(Client.name.ilike(term), Client.email.ilike(term), Client.phone.ilike(term))
        ).order_by(Client.name).limit(5).all()
        for item in clients:
            results.append({'type': 'Cliente', 'title': item.name, 'subtitle': item.email or item.phone or 'Cliente', 'icon': 'bi-person',
                            'url': url_for('client_bp.client_detail', client_id=item.id)})

    if user.has_permission('suppliers.view'):
        suppliers = Supplier.query.filter(
            Supplier.company_id == company_id, Supplier.archived_at.is_(None),
            or_(Supplier.name.ilike(term), Supplier.email.ilike(term), Supplier.phone.ilike(term))
        ).order_by(Supplier.name).limit(5).all()
        for item in suppliers:
            results.append({'type': 'Proveedor', 'title': item.name, 'subtitle': item.email or item.phone or 'Proveedor', 'icon': 'bi-truck',
                            'url': url_for('supplier_bp.supplier_purchase_history', supplier_id=item.id)})

    from routes.sales.access import visible_sales_query
    if user.has_permission('sales.view'):
        if q.isdigit():
            sale = visible_sales_query(company_id, user.id).filter_by(id=int(q)).first()
            if sale:
                results.append({'type': 'Venta', 'title': f'Venta #{sale.id}', 'subtitle': sale.status, 'icon': 'bi-receipt',
                                'url': url_for('sales_bp.sale_detail', sale_id=sale.id)})
        else:
            sales = visible_sales_query(company_id, user.id).join(Client, Sale.client_id == Client.id, isouter=True).filter(
                or_(Sale.customer_name.ilike(term), Client.name.ilike(term))
            ).order_by(Sale.created_at.desc()).limit(4).all()
            for sale in sales:
                results.append({'type': 'Venta', 'title': f'Venta #{sale.id}', 'subtitle': sale.client.name if sale.client else sale.customer_name or sale.status,
                                'icon': 'bi-receipt', 'url': url_for('sales_bp.sale_detail', sale_id=sale.id)})

    if q.isdigit() and user.has_permission('purchases.view'):
        purchase = PurchaseOrder.query.filter_by(company_id=company_id, id=int(q)).first()
        if purchase:
            results.append({'type': 'Compra', 'title': f'Orden #{purchase.id}', 'subtitle': purchase.supplier_name, 'icon': 'bi-bag-check',
                            'url': url_for('purchase_bp.purchase_detail', order_id=purchase.id)})

    return jsonify(results=results[:20])


def _trash_folder(company_id, *, create=False):
    folder = DocumentFolder.query.filter_by(company_id=company_id, name=TRASH_FOLDER_NAME, parent_id=None).first()
    if not folder and create:
        folder = DocumentFolder(company_id=company_id, name=TRASH_FOLDER_NAME, parent_id=None, created_by=session['user_id'])
        db.session.add(folder)
        db.session.flush()
    return folder


@workspace_bp.get('/documents')
def documents():
    company_id = _company_id()
    folder_id = request.args.get('folder', type=int)
    current_folder = None
    if folder_id:
        current_folder = DocumentFolder.query.filter_by(id=folder_id, company_id=company_id).first_or_404()

    q = (request.args.get('q') or '').strip()
    entity_type = (request.args.get('entity_type') or '').upper()
    entity_id = request.args.get('entity_id', type=int)
    kind = (request.args.get('kind') or '').lower()
    sort = (request.args.get('sort') or 'recent').lower()

    trash = _trash_folder(company_id)
    query = CompanyDocument.query.filter_by(company_id=company_id)
    if trash:
        query = query.filter(or_(CompanyDocument.folder_id.is_(None), CompanyDocument.folder_id != trash.id))
    folder_query = DocumentFolder.query.filter_by(company_id=company_id).filter(DocumentFolder.name != TRASH_FOLDER_NAME)
    if q:
        term = f'%{q}%'
        query = query.filter(CompanyDocument.display_name.ilike(term))
        folder_query = folder_query.filter(DocumentFolder.name.ilike(term))
    else:
        query = query.filter(CompanyDocument.folder_id == folder_id)
        folder_query = folder_query.filter(DocumentFolder.parent_id == folder_id)
    if entity_type:
        query = query.filter(CompanyDocument.entity_type == entity_type)
    if entity_id:
        query = query.filter(CompanyDocument.entity_id == entity_id)
    if kind == 'pdf':
        query = query.filter(CompanyDocument.mime_type.ilike('%pdf%'))
    elif kind == 'image':
        query = query.filter(CompanyDocument.mime_type.ilike('image/%'))
    elif kind == 'sheet':
        query = query.filter(or_(CompanyDocument.display_name.ilike('%.csv'), CompanyDocument.display_name.ilike('%.xlsx')))
    elif kind == 'document':
        query = query.filter(or_(CompanyDocument.display_name.ilike('%.docx'), CompanyDocument.display_name.ilike('%.txt')))

    if sort == 'name':
        query = query.order_by(CompanyDocument.display_name.asc())
        folder_query = folder_query.order_by(DocumentFolder.name.asc())
    elif sort == 'oldest':
        query = query.order_by(CompanyDocument.created_at.asc())
        folder_query = folder_query.order_by(DocumentFolder.created_at.asc())
    elif sort == 'size':
        query = query.order_by(CompanyDocument.size_bytes.desc(), CompanyDocument.created_at.desc())
        folder_query = folder_query.order_by(DocumentFolder.name.asc())
    else:
        query = query.order_by(CompanyDocument.updated_at.desc(), CompanyDocument.created_at.desc())
        folder_query = folder_query.order_by(DocumentFolder.created_at.desc())

    rows = query.limit(350).all()
    folders = folder_query.limit(150).all()
    all_folders = DocumentFolder.query.filter_by(company_id=company_id).filter(DocumentFolder.name != TRASH_FOLDER_NAME).order_by(DocumentFolder.name.asc()).all()
    total_bytes = db.session.query(func.coalesce(func.sum(CompanyDocument.size_bytes), 0)).filter(
        CompanyDocument.company_id == company_id,
        or_(CompanyDocument.folder_id.is_(None), CompanyDocument.folder_id != (trash.id if trash else -1)),
    ).scalar() or 0
    total_docs_query = CompanyDocument.query.filter_by(company_id=company_id)
    if trash:
        total_docs_query = total_docs_query.filter(or_(CompanyDocument.folder_id.is_(None), CompanyDocument.folder_id != trash.id))
    total_docs = total_docs_query.count()

    breadcrumb = []
    node = current_folder
    visited = set()
    while node and node.id not in visited:
        visited.add(node.id)
        breadcrumb.append(node)
        node = node.parent if node.parent and node.parent.company_id == company_id else None
    breadcrumb.reverse()

    return render_template(
        'workspace/documents.html', user=_user(), documents=rows, folders=folders,
        all_folders=all_folders, current_folder=current_folder, breadcrumb=breadcrumb,
        entity_type=entity_type, entity_id=entity_id, q=q, kind=kind, sort=sort,
        total_bytes=int(total_bytes), total_docs=total_docs,
    )


def _folder_for_company(folder_id, company_id, *, allow_none=True):
    if not folder_id:
        if allow_none:
            return None
        raise ValueError('Selecciona una carpeta válida.')
    folder = DocumentFolder.query.filter_by(id=folder_id, company_id=company_id).first()
    if not folder:
        raise ValueError('La carpeta no existe en esta empresa.')
    return folder


@workspace_bp.post('/documents/folders')
def document_folder_create():
    company_id = _company_id()
    try:
        name = _safe_display_name(request.form.get('name'), 120)
        if name == TRASH_FOLDER_NAME:
            raise ValueError('Nombre reservado')
    except ValueError:
        flash('Escribe un nombre de carpeta válido.', 'danger')
        return redirect(request.referrer or url_for('workspace_bp.documents'))
    parent_id = request.form.get('parent_id', type=int)
    parent = _folder_for_company(parent_id, company_id) if parent_id else None
    duplicate = DocumentFolder.query.filter_by(company_id=company_id, parent_id=parent.id if parent else None).filter(
        func.lower(DocumentFolder.name) == name.lower()
    ).first()
    if duplicate:
        flash('Ya existe una carpeta con ese nombre en esta ubicación.', 'warning')
        return redirect(url_for('workspace_bp.documents', folder=parent.id if parent else None))
    folder = DocumentFolder(
        company_id=company_id, name=name[:120], parent_id=parent.id if parent else None,
        created_by=session['user_id'],
    )
    db.session.add(folder)
    db.session.commit()
    flash('Carpeta creada.', 'success')
    return redirect(url_for('workspace_bp.documents', folder=parent.id if parent else None))


@workspace_bp.post('/documents/folders/<int:folder_id>/update')
def document_folder_update(folder_id):
    company_id = _company_id()
    folder = DocumentFolder.query.filter_by(id=folder_id, company_id=company_id).first_or_404()
    if folder.name == TRASH_FOLDER_NAME:
        abort(404)
    try:
        name = _safe_display_name(request.form.get('name') or folder.name, 120)
    except ValueError:
        flash('El nombre de la carpeta no es válido.', 'danger')
        return redirect(url_for('workspace_bp.documents', folder=folder.id))
    parent_id = request.form.get('parent_id', type=int)
    parent = _folder_for_company(parent_id, company_id) if parent_id else None
    if parent and parent.id == folder.id:
        flash('Una carpeta no puede contenerse a sí misma.', 'danger')
        return redirect(url_for('workspace_bp.documents', folder=folder.id))
    node = parent
    visited = set()
    while node and node.id not in visited:
        if node.id == folder.id:
            flash('No puedes mover una carpeta dentro de una de sus subcarpetas.', 'danger')
            return redirect(url_for('workspace_bp.documents', folder=folder.id))
        visited.add(node.id)
        node = node.parent if node.parent and node.parent.company_id == company_id else None
    duplicate = DocumentFolder.query.filter(
        DocumentFolder.company_id == company_id,
        DocumentFolder.parent_id == (parent.id if parent else None),
        DocumentFolder.id != folder.id,
        func.lower(DocumentFolder.name) == name.lower(),
    ).first()
    if duplicate:
        flash('Ya existe una carpeta con ese nombre en la ubicación elegida.', 'warning')
        return redirect(url_for('workspace_bp.documents', folder=folder.id))
    folder.name = name[:120]
    folder.parent_id = parent.id if parent else None
    db.session.commit()
    flash('Carpeta actualizada.', 'success')
    return redirect(url_for('workspace_bp.documents', folder=folder.id))


@workspace_bp.post('/documents/folders/<int:folder_id>/delete')
def document_folder_delete(folder_id):
    company_id = _company_id()
    folder = DocumentFolder.query.filter_by(id=folder_id, company_id=company_id).first_or_404()
    if folder.name == TRASH_FOLDER_NAME:
        abort(404)
    if folder.children or folder.documents:
        flash('La carpeta debe estar vacía antes de eliminarla.', 'warning')
        return redirect(url_for('workspace_bp.documents', folder=folder.id))
    parent_id = folder.parent_id
    db.session.delete(folder)
    db.session.commit()
    flash('Carpeta eliminada.', 'info')
    return redirect(url_for('workspace_bp.documents', folder=parent_id))


@workspace_bp.post('/documents/upload')
def document_upload():
    company_id = _company_id()
    upload = request.files.get('file')
    if not upload or not upload.filename:
        flash('Selecciona un archivo.', 'danger')
        return redirect(request.referrer or url_for('workspace_bp.documents'))
    safe_name = secure_filename(upload.filename)
    extension = safe_name.rsplit('.', 1)[-1].lower() if '.' in safe_name else ''
    if extension not in ALLOWED_DOCUMENT_EXTENSIONS:
        flash('Tipo de archivo no permitido.', 'danger')
        return redirect(request.referrer or url_for('workspace_bp.documents'))
    try:
        # Contextual uploads (client/supplier/product/etc.) must preserve their
        # relation. _document_entity validates that the target belongs to this
        # company before any file is written.
        entity_type, entity_id = _document_entity(
            request.form.get('entity_type'), request.form.get('entity_id', type=int), company_id
        )
        folder = _folder_for_company(request.form.get('folder_id', type=int), company_id)
    except ValueError as exc:
        flash(str(exc), 'danger')
        return redirect(request.referrer or url_for('workspace_bp.documents'))
    content = upload.read()
    try:
        canonical_mime = validate_document_bytes(content, extension)
    except ValueError as exc:
        flash(str(exc), 'danger')
        return redirect(request.referrer or url_for('workspace_bp.documents'))
    stored_relative = f'company_{company_id}/documents/{uuid.uuid4().hex}_{safe_name}'
    root = Path(current_app.config['STORAGE_ROOT']).resolve()
    path = (root / stored_relative).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if root not in path.parents:
        abort(403)
    path.write_bytes(content)
    row = CompanyDocument(
        company_id=company_id, entity_type=entity_type, entity_id=entity_id,
        display_name=safe_name[:180], stored_name=stored_relative,
        mime_type=canonical_mime, size_bytes=len(content),
        uploaded_by=session['user_id'], folder_id=folder.id if folder else None,
    )
    db.session.add(row)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        path.unlink(missing_ok=True)
        current_app.logger.exception('No se pudo registrar el documento privado')
        flash('No fue posible guardar el documento.', 'danger')
        return redirect(request.referrer or url_for('workspace_bp.documents'))
    flash('Documento guardado.', 'success')
    if entity_type != 'COMPANY':
        return redirect(url_for('workspace_bp.documents', entity_type=entity_type, entity_id=entity_id))
    return redirect(url_for('workspace_bp.documents', folder=folder.id if folder else None))


@workspace_bp.get('/documents/<int:document_id>/preview')
def document_preview(document_id):
    document = CompanyDocument.query.filter_by(id=document_id, company_id=_company_id()).first_or_404()
    path = _document_path(document)
    if not path.is_file():
        abort(404)
    extension = document.display_name.rsplit('.', 1)[-1].lower() if '.' in document.display_name else ''
    mime = CANONICAL_MIME.get(extension, 'application/octet-stream')
    previewable = extension in {'pdf', 'png', 'jpg', 'jpeg', 'webp', 'txt', 'csv'}
    if not previewable:
        return redirect(url_for('workspace_bp.document_download', document_id=document.id))
    return send_file(path, as_attachment=False, download_name=document.display_name, mimetype=mime)


@workspace_bp.get('/documents/<int:document_id>/download')
def document_download(document_id):
    document = CompanyDocument.query.filter_by(id=document_id, company_id=_company_id()).first_or_404()
    path = _document_path(document)
    if not path.is_file():
        abort(404)
    extension = document.display_name.rsplit('.', 1)[-1].lower() if '.' in document.display_name else ''
    return send_file(path, as_attachment=True, download_name=document.display_name, mimetype=CANONICAL_MIME.get(extension, 'application/octet-stream'))


@workspace_bp.post('/documents/<int:document_id>/update')
def document_update(document_id):
    company_id = _company_id()
    document = CompanyDocument.query.filter_by(id=document_id, company_id=company_id).first_or_404()
    try:
        name = _safe_display_name(request.form.get('display_name') or document.display_name, 180)
    except ValueError:
        flash('El nombre del archivo no es válido.', 'danger')
        return redirect(request.referrer or url_for('workspace_bp.documents'))
    current_extension = document.stored_name.rsplit('.', 1)[-1].lower() if '.' in document.stored_name else ''
    new_extension = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    if current_extension != new_extension or new_extension not in ALLOWED_DOCUMENT_EXTENSIONS:
        flash('Puedes renombrar el archivo, pero no cambiar su extensión.', 'danger')
        return redirect(request.referrer or url_for('workspace_bp.documents'))
    try:
        folder = _folder_for_company(request.form.get('folder_id', type=int), company_id)
    except ValueError as exc:
        flash(str(exc), 'danger')
        return redirect(request.referrer or url_for('workspace_bp.documents'))
    document.display_name = name[:180]
    document.folder_id = folder.id if folder else None
    document.updated_at = utcnow()
    db.session.commit()
    flash('Documento actualizado.', 'success')
    return redirect(url_for('workspace_bp.documents', folder=document.folder_id))


@workspace_bp.post('/documents/<int:document_id>/delete')
def document_delete(document_id):
    company_id = _company_id()
    document = CompanyDocument.query.filter_by(id=document_id, company_id=company_id).first_or_404()
    folder_id = document.folder_id
    trash = _trash_folder(company_id, create=True)
    document.folder_id = trash.id
    document.updated_at = utcnow()
    db.session.commit()
    flash('Archivo movido a la Papelera. Puedes restaurarlo cuando quieras.', 'info')
    return redirect(url_for('workspace_bp.documents', folder=folder_id if folder_id != trash.id else None))


@workspace_bp.post('/recycle-bin/document/<int:document_id>/restore')
def restore_document(document_id):
    company_id = _company_id()
    trash = _trash_folder(company_id)
    document = CompanyDocument.query.filter_by(id=document_id, company_id=company_id).first_or_404()
    if not trash or document.folder_id != trash.id:
        abort(404)
    document.folder_id = None
    document.updated_at = utcnow()
    db.session.commit()
    flash(f'{document.display_name} restaurado en Mi unidad.', 'success')
    return redirect(url_for('workspace_bp.recycle_bin'))


@workspace_bp.post('/recycle-bin/document/<int:document_id>/purge')
def purge_document(document_id):
    company_id = _company_id()
    trash = _trash_folder(company_id)
    document = CompanyDocument.query.filter_by(id=document_id, company_id=company_id).first_or_404()
    if not trash or document.folder_id != trash.id:
        abort(404)
    path = _document_path(document)
    db.session.delete(document)
    db.session.commit()
    try:
        path.unlink(missing_ok=True)
    except OSError:
        current_app.logger.warning('No se pudo borrar definitivamente el archivo %s', path)
    flash('Archivo eliminado definitivamente.', 'info')
    return redirect(url_for('workspace_bp.recycle_bin'))


@workspace_bp.get('/recycle-bin')
def recycle_bin():
    company_id = _company_id()
    # Los productos archivados se administran dentro de Productos para evitar dos vistas
    # distintas que hagan exactamente lo mismo.
    archived_product_count = Product.query.filter(
        Product.company_id == company_id,
        Product.archived_at.isnot(None),
    ).count()
    clients = Client.query.filter(Client.company_id == company_id, Client.archived_at.isnot(None)).order_by(Client.archived_at.desc()).all()
    suppliers = Supplier.query.filter(Supplier.company_id == company_id, Supplier.archived_at.isnot(None)).order_by(Supplier.archived_at.desc()).all()
    trash = _trash_folder(company_id)
    documents = CompanyDocument.query.filter_by(company_id=company_id, folder_id=trash.id).order_by(CompanyDocument.updated_at.desc()).all() if trash else []
    return render_template(
        'workspace/recycle_bin.html',
        user=_user(),
        archived_product_count=archived_product_count,
        clients=clients,
        suppliers=suppliers,
        documents=documents,
    )


@workspace_bp.post('/recycle-bin/<entity_type>/<int:entity_id>/restore')
def restore_entity(entity_type, entity_id):
    model = ENTITY_MODELS.get(entity_type.upper())
    if not model:
        abort(404)
    row = model.query.filter_by(id=entity_id, company_id=_company_id()).first_or_404()
    row.archived_at = None
    if isinstance(row, Product):
        row.status = True
    db.session.commit()
    flash(f'{getattr(row, "name", "Registro")} restaurado.', 'success')
    return redirect(url_for('workspace_bp.recycle_bin'))


@workspace_bp.route('/notification-rules', methods=['GET', 'POST'])
def notification_rules():
    company_id = _company_id()
    rules = ensure_default_rules(company_id)
    users = User.query.filter_by(company_id=company_id, is_active=True).order_by(User.name.asc()).all()
    user_ids = {row.id for row in users}
    if request.method == 'POST':
        try:
            for rule in rules:
                rule.threshold = finite_int(
                    request.form.get(f'threshold_{rule.id}', str(rule.threshold or 0)),
                    field_name=f'Umbral de {rule.name}',
                )
                if rule.threshold < 0 or rule.threshold > 2_147_483_647:
                    raise NumericValueError(f'Umbral de {rule.name}: valor fuera de rango.')
                rule.enabled = request.form.get(f'enabled_{rule.id}') == 'on'
                level = (request.form.get(f'level_{rule.id}') or 'WARNING').upper()
                rule.level = level if level in {'INFO', 'WARNING', 'DANGER'} else 'WARNING'
                name = (request.form.get(f'name_{rule.id}') or rule.name or RULE_LABELS.get(rule.rule_type, rule.rule_type)).strip()
                rule.name = name[:120]
                target_user_id = request.form.get(f'target_user_{rule.id}', type=int)
                rule.target_user_id = target_user_id if target_user_id in user_ids else None
                lookback = finite_int(
                    request.form.get(f'lookback_{rule.id}', rule.lookback_days or 30),
                    field_name=f'Período de {rule.name}',
                )
                if lookback < 0 or lookback > 3650:
                    raise NumericValueError(f'Período de {rule.name}: debe estar entre 0 y 3650 días.')
                rule.lookback_days = lookback
                if rule.rule_type == 'CUSTOM':
                    source = (request.form.get(f'source_{rule.id}') or rule.custom_source or '').upper()
                    operator = (request.form.get(f'operator_{rule.id}') or rule.operator or 'GTE').upper()
                    rule.custom_source = source if source in CUSTOM_SOURCES else rule.custom_source
                    rule.operator = operator if operator in OPERATORS else 'GTE'
                    rule.message = (request.form.get(f'message_{rule.id}') or rule.message or '').strip()[:255] or None
                    link = (request.form.get(f'link_{rule.id}') or rule.link or '').strip()
                    rule.link = link[:255] if link.startswith('/') and not link.startswith('//') else None
            db.session.commit()
        except NumericValueError as exc:
            db.session.rollback()
            flash(str(exc), 'danger')
            return redirect(url_for('workspace_bp.notification_rules'))
        produced = evaluate_notification_rules(company_id)
        flash(f'Reglas actualizadas. OrbisERP detectó {produced} condición(es) activa(s) y actualizó Notificaciones.', 'success')
        return redirect(url_for('workspace_bp.notification_rules'))

    existing_types = {rule.rule_type for rule in rules if rule.rule_type != 'CUSTOM'}
    optional_types = [
        key for key in ('RECEIVABLE_AMOUNT_ABOVE', 'EXPENSE_AMOUNT_ABOVE', 'SALE_AMOUNT_ABOVE')
        if key not in existing_types
    ]
    return render_template(
        'workspace/notification_rules.html', user=_user(), rules=rules, labels=RULE_LABELS,
        descriptions=RULE_DESCRIPTIONS, custom_sources=CUSTOM_SOURCES, operators=OPERATORS,
        users=users, optional_types=optional_types,
    )


@workspace_bp.post('/notification-rules/add')
def notification_rule_add():
    company_id = _company_id()
    rule_type = (request.form.get('rule_type') or '').upper()
    allowed = {'RECEIVABLE_AMOUNT_ABOVE', 'EXPENSE_AMOUNT_ABOVE', 'SALE_AMOUNT_ABOVE'}
    if rule_type not in allowed:
        flash('Selecciona una regla predefinida válida.', 'danger')
        return redirect(url_for('workspace_bp.notification_rules'))
    if NotificationRule.query.filter_by(company_id=company_id, rule_type=rule_type).first():
        flash('Esa regla ya está configurada.', 'warning')
        return redirect(url_for('workspace_bp.notification_rules'))
    defaults = {
        'RECEIVABLE_AMOUNT_ABOVE': (50000, 30),
        'EXPENSE_AMOUNT_ABOVE': (25000, 30),
        'SALE_AMOUNT_ABOVE': (50000, 30),
    }
    threshold, lookback = defaults[rule_type]
    db.session.add(NotificationRule(
        company_id=company_id, rule_type=rule_type, name=RULE_LABELS[rule_type],
        threshold=threshold, lookback_days=lookback, level='WARNING', enabled=True,
    ))
    db.session.commit()
    flash('Regla añadida. Ajusta su umbral y severidad.', 'success')
    return redirect(url_for('workspace_bp.notification_rules'))


@workspace_bp.post('/notification-rules/custom')
def notification_rule_custom_create():
    company_id = _company_id()
    name = (request.form.get('name') or '').strip()
    source = (request.form.get('source') or '').upper()
    operator = (request.form.get('operator') or '').upper()
    message = (request.form.get('message') or '').strip()
    if len(name) < 3 or source not in CUSTOM_SOURCES or operator not in OPERATORS:
        flash('Completa nombre, fuente y condición de la alerta personalizada.', 'danger')
        return redirect(url_for('workspace_bp.notification_rules'))
    try:
        threshold = finite_int(request.form.get('threshold') or '0', field_name='Umbral')
        lookback = finite_int(request.form.get('lookback_days') or '30', field_name='Período de análisis')
        if threshold < 0 or threshold > 2_147_483_647:
            raise NumericValueError('Umbral: valor fuera de rango.')
        if lookback < 0 or lookback > 3650:
            raise NumericValueError('Período de análisis: debe estar entre 0 y 3650 días.')
    except NumericValueError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for('workspace_bp.notification_rules'))
    level = (request.form.get('level') or 'WARNING').upper()
    if level not in {'INFO', 'WARNING', 'DANGER'}:
        level = 'WARNING'
    target_user_id = request.form.get('target_user_id', type=int)
    if target_user_id and not User.query.filter_by(id=target_user_id, company_id=company_id, is_active=True).first():
        target_user_id = None
    link = (request.form.get('link') or '').strip()
    if link and (not link.startswith('/') or link.startswith('//')):
        link = ''
    db.session.add(NotificationRule(
        company_id=company_id, rule_type='CUSTOM', name=name[:120], threshold=threshold,
        level=level, enabled=True, custom_source=source, operator=operator,
        lookback_days=lookback, message=message[:255] or None, link=link[:255] or None,
        target_user_id=target_user_id,
    ))
    db.session.commit()
    produced = evaluate_notification_rules(company_id)
    flash(f'Alerta personalizada creada y evaluada ({produced} condición(es) activas en total).', 'success')
    return redirect(url_for('workspace_bp.notification_rules'))


@workspace_bp.post('/notification-rules/<int:rule_id>/delete')
def notification_rule_delete(rule_id):
    company_id = _company_id()
    rule = NotificationRule.query.filter_by(id=rule_id, company_id=company_id).first_or_404()
    protected_types = {item[0] for item in DEFAULT_RULES}
    if rule.rule_type in protected_types:
        flash('Las reglas base se desactivan en lugar de eliminarse.', 'warning')
        return redirect(url_for('workspace_bp.notification_rules'))
    AppNotification.query.filter(
        AppNotification.company_id == company_id,
        AppNotification.dedupe_key.like(f'rule:{rule.id}:%'),
    ).delete(synchronize_session=False)
    db.session.delete(rule)
    db.session.commit()
    flash('Regla eliminada junto con sus alertas generadas.', 'info')
    return redirect(url_for('workspace_bp.notification_rules'))


@workspace_bp.post('/notification-rules/evaluate')
def notification_rules_evaluate():
    produced = evaluate_notification_rules(_company_id())
    flash(f'Evaluación completada: {produced} condición(es) activas. La bandeja de Notificaciones ya está actualizada.', 'success')
    return redirect(url_for('backoffice_bp.notifications'))


@workspace_bp.route('/taxes', methods=['GET', 'POST'])
def taxes():
    company_id = _company_id()
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        try:
            rate = bounded_decimal(
                request.form.get('rate') or '0',
                field_name='Tasa de impuesto', places=2, minimum='0', maximum='100',
            )
        except NumericValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('workspace_bp.taxes'))
        if len(name) < 2:
            flash('El nombre del impuesto debe tener al menos 2 caracteres.', 'danger')
        else:
            if request.form.get('is_default') == 'on':
                SalesTax.query.filter_by(company_id=company_id).update({'is_default': False})
            db.session.add(SalesTax(
                company_id=company_id, name=name[:80], rate=rate,
                price_included=request.form.get('price_included') == 'on',
                is_default=request.form.get('is_default') == 'on', active=True,
            ))
            try:
                db.session.commit()
                flash('Impuesto creado.', 'success')
            except IntegrityError:
                db.session.rollback()
                flash('Ya existe un impuesto con ese nombre.', 'warning')
        return redirect(url_for('workspace_bp.taxes'))
    tax_rows = SalesTax.query.filter_by(company_id=company_id).order_by(SalesTax.is_default.desc(), SalesTax.name).all()
    products = Product.query.filter(Product.company_id == company_id, Product.archived_at.is_(None)).order_by(Product.name).limit(300).all()
    categories = Category.query.filter_by(company_id=company_id).order_by(Category.name).all()
    return render_template('workspace/taxes.html', user=_user(), taxes=tax_rows, products=products, categories=categories)


@workspace_bp.post('/taxes/<int:tax_id>/default')
def tax_set_default(tax_id):
    company_id = _company_id()
    tax = SalesTax.query.filter_by(id=tax_id, company_id=company_id, active=True).first_or_404()
    SalesTax.query.filter_by(company_id=company_id).update({'is_default': False})
    tax.is_default = True
    db.session.commit()
    flash(f'{tax.name} es ahora el impuesto predeterminado.', 'success')
    return redirect(url_for('workspace_bp.taxes'))


@workspace_bp.post('/taxes/assign')
def tax_assign():
    company_id = _company_id()
    tax_id = request.form.get('tax_id', type=int)
    tax = SalesTax.query.filter_by(id=tax_id, company_id=company_id, active=True).first_or_404()
    product_id = request.form.get('product_id', type=int)
    category_id = request.form.get('category_id', type=int)
    if product_id:
        product = Product.query.filter_by(id=product_id, company_id=company_id).filter(Product.archived_at.is_(None)).first_or_404()
        product.sales_tax_id = tax.id
        label = product.name
    elif category_id:
        category = Category.query.filter_by(id=category_id, company_id=company_id).first_or_404()
        Product.query.filter_by(company_id=company_id, category_id=category.id).filter(Product.archived_at.is_(None)).update({'sales_tax_id': tax.id}, synchronize_session=False)
        label = f'categoría {category.name}'
    else:
        flash('Selecciona un producto o categoría.', 'warning')
        return redirect(url_for('workspace_bp.taxes'))
    db.session.commit()
    flash(f'{tax.name} asignado a {label}.', 'success')
    return redirect(url_for('workspace_bp.taxes'))


@workspace_bp.route('/promotions', methods=['GET', 'POST'])
def promotions():
    company_id = _company_id()
    if request.method == 'POST':
        code = (request.form.get('code') or '').strip().upper()
        name = (request.form.get('name') or '').strip()
        discount_type = (request.form.get('discount_type') or 'PERCENT').upper()
        mechanic = (request.form.get('mechanic') or 'STANDARD').upper()
        scope = (request.form.get('scope') or 'ALL').upper()
        try:
            value = bounded_decimal(
                request.form.get('value') or '0', field_name='Valor', places=2,
                minimum='0', maximum='9999999999.99',
            )
            min_total = bounded_decimal(
                request.form.get('min_total') or '0', field_name='Compra mínima', places=2,
                minimum='0', maximum='9999999999.99',
            )
            buy_qty = bounded_decimal(
                request.form.get('buy_qty') or '1', field_name='Cantidad requerida', places=3,
                minimum='0.001', maximum='99999999999.999',
            )
            reward_qty = bounded_decimal(
                request.form.get('reward_qty') or '1', field_name='Cantidad bonificada', places=3,
                minimum='0.001', maximum='99999999999.999',
            )
            reward_percent = bounded_decimal(
                request.form.get('reward_percent') or '100', field_name='Porcentaje de beneficio', places=3,
                minimum='0', maximum='100',
            )
            max_discount = bounded_decimal(
                request.form['max_discount'], field_name='Descuento máximo', places=2,
                minimum='0', maximum='9999999999.99',
            ) if request.form.get('max_discount') else None
        except NumericValueError as exc:
            flash(str(exc), 'danger')
            return redirect(url_for('workspace_bp.promotions'))
        date_error = False
        try:
            starts_at = datetime.fromisoformat(request.form['starts_at']) if request.form.get('starts_at') else None
            ends_at = datetime.fromisoformat(request.form['ends_at']) if request.form.get('ends_at') else None
        except ValueError:
            starts_at = ends_at = None
            date_error = True
        invalid_range = bool(starts_at and ends_at and ends_at < starts_at)
        target_product_id = request.form.get('target_product_id', type=int) if scope == 'PRODUCT' else None
        target_category_id = request.form.get('target_category_id', type=int) if scope == 'CATEGORY' else None
        target_brand = (request.form.get('target_brand') or '').strip()[:100] if scope == 'BRAND' else None
        target_valid = True
        if scope == 'PRODUCT' and not Product.query.filter_by(id=target_product_id, company_id=company_id).first(): target_valid = False
        if scope == 'CATEGORY' and not Category.query.filter_by(id=target_category_id, company_id=company_id).first(): target_valid = False
        if scope == 'BRAND' and not target_brand: target_valid = False
        invalid_standard = mechanic == 'STANDARD' and (discount_type not in {'PERCENT', 'FIXED'} or value <= 0 or (discount_type == 'PERCENT' and value > 100))
        invalid_reward = mechanic in {'BUY_X_GET_Y','SECOND_PERCENT'} and (buy_qty <= 0 or reward_qty <= 0 or reward_percent < 0 or reward_percent > 100)
        if (
            len(code) < 2 or len(name) < 2 or mechanic not in {'STANDARD','BUY_X_GET_Y','SECOND_PERCENT'}
            or scope not in {'ALL','PRODUCT','CATEGORY','BRAND'} or not target_valid
            or invalid_standard or invalid_reward or min_total < 0 or (max_discount is not None and max_discount < 0)
            or date_error or invalid_range
        ):
            flash('Revisa la mecánica, alcance, valores y vigencia de la promoción.', 'danger')
        else:
            # Legacy value remains positive for the existing DB constraint even when the
            # benefit is controlled by the advanced reward fields.
            safe_value = value if value > 0 else finite_decimal('1.00')
            db.session.add(Promotion(
                company_id=company_id, code=code[:40], name=name[:120], discount_type=discount_type,
                value=safe_value, min_total=min_total, starts_at=starts_at, ends_at=ends_at, active=True,
                mechanic=mechanic, scope=scope, target_product_id=target_product_id,
                target_category_id=target_category_id, target_brand=target_brand,
                buy_qty=buy_qty, reward_qty=reward_qty, reward_percent=reward_percent,
                max_discount=max_discount,
            ))
            try:
                db.session.commit()
                flash('Promoción creada.', 'success')
            except IntegrityError:
                db.session.rollback()
                flash('Ese código ya existe.', 'warning')
        return redirect(url_for('workspace_bp.promotions'))
    rows = Promotion.query.filter_by(company_id=company_id).order_by(Promotion.active.desc(), Promotion.created_at.desc()).all()
    products = Product.query.filter_by(company_id=company_id, status=True).filter(Product.archived_at.is_(None)).order_by(Product.name.asc()).all()
    categories = Category.query.filter_by(company_id=company_id, status=True).order_by(Category.name.asc()).all()
    brands = sorted({(p.brand or '').strip() for p in products if (p.brand or '').strip()})
    return render_template('workspace/promotions.html', user=_user(), promotions=rows, now=utcnow(), products=products, categories=categories, brands=brands)


@workspace_bp.post('/promotions/<int:promotion_id>/toggle')
def promotion_toggle(promotion_id):
    promotion = Promotion.query.filter_by(id=promotion_id, company_id=_company_id()).first_or_404()
    promotion.active = not promotion.active
    db.session.commit()
    flash('Estado de promoción actualizado.', 'success')
    return redirect(url_for('workspace_bp.promotions'))


@workspace_bp.get('/labels')
def labels():
    company_id = _company_id()
    selected = request.args.getlist('product_id', type=int)
    query = Product.query.filter(Product.company_id == company_id, Product.archived_at.is_(None), Product.status.is_(True))
    products = query.order_by(Product.name).all()
    print_products = query.filter(Product.id.in_(selected)).all() if selected else []
    copies = min(max(request.args.get('copies', 1, type=int), 1), 20)
    return render_template('workspace/labels.html', user=_user(), products=products, print_products=print_products, copies=copies)


@workspace_bp.get('/labels/<int:product_id>.svg')
def product_barcode(product_id):
    product = Product.query.filter_by(id=product_id, company_id=_company_id()).filter(Product.archived_at.is_(None)).first_or_404()
    try:
        payload = barcode_svg(product.sku)
    except ValueError:
        abort(400)
    return Response(payload, mimetype='image/svg+xml', headers={'Cache-Control': 'private, max-age=3600'})


@workspace_bp.get('/activity')
def activity_feed():
    # Compatibilidad: la actividad reciente se consolidó en Auditoría general.
    return redirect(url_for('governance_bp.audit_explorer'))
