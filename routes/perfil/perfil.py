import uuid
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from db import db
from models.divisas.divisas import ExchangeRate
from models.user.user import User


perfil_bp = Blueprint('perfil_bp', __name__)
ALLOWED_AVATAR_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
ALLOWED_AVATAR_MIMES = {'image/png', 'image/jpeg', 'image/webp'}


def _avatar_file(relative_path):
    if not relative_path:
        return None
    static_root = (Path(current_app.root_path) / 'static').resolve()
    avatar_root = (static_root / 'uploads' / 'avatars').resolve()
    candidate = (static_root / relative_path).resolve()
    if avatar_root not in candidate.parents:
        return None
    return candidate


def _delete_avatar(relative_path):
    path = _avatar_file(relative_path)
    if path and path.is_file():
        try:
            path.unlink()
        except OSError:
            current_app.logger.warning('No se pudo eliminar el avatar %s', path)


@perfil_bp.route('/perfil', methods=['GET', 'POST'])
def perfil():
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    if not user_id:
        return redirect(url_for('login_bp.login'))

    current_user = db.session.get(User, user_id)
    if not current_user or (company_id and current_user.company_id != company_id):
        session.clear()
        return redirect(url_for('login_bp.login'))

    if request.method == 'POST':
        action = (request.form.get('action') or 'profile').strip()

        if action == 'profile':
            name = (request.form.get('name') or '').strip()
            if len(name) < 2 or len(name) > 150:
                flash('El nombre debe tener entre 2 y 150 caracteres.', 'danger')
                return redirect(url_for('perfil_bp.perfil'))
            currency = (request.form.get('default_currency') or 'DOP').upper()[:3]
            if currency != 'DOP' and not ExchangeRate.query.filter_by(company_id=current_user.company_id, currency_code=currency).first():
                flash('La moneda predeterminada seleccionada no está configurada.', 'danger')
                return redirect(url_for('perfil_bp.perfil'))
            current_user.name = name
            current_user.default_currency = currency
            db.session.commit()
            session['selected_currency'] = currency
            flash('Perfil actualizado.', 'success')

        elif action == 'avatar':
            upload = request.files.get('avatar')
            if not upload or not upload.filename:
                flash('Selecciona una imagen.', 'danger')
                return redirect(url_for('perfil_bp.perfil'))
            extension = upload.filename.rsplit('.', 1)[-1].lower() if '.' in upload.filename else ''
            mimetype = (upload.mimetype or '').lower()
            if extension not in ALLOWED_AVATAR_EXTENSIONS or mimetype not in ALLOWED_AVATAR_MIMES:
                flash('Usa una imagen PNG, JPG o WEBP.', 'danger')
                return redirect(url_for('perfil_bp.perfil'))
            if request.content_length and request.content_length > 4 * 1024 * 1024:
                flash('La foto de perfil no puede superar 4 MB.', 'danger')
                return redirect(url_for('perfil_bp.perfil'))
            try:
                image = Image.open(upload.stream)
                image.verify()
                upload.stream.seek(0)
                image = Image.open(upload.stream)
                if image.format not in {'PNG', 'JPEG', 'WEBP'}:
                    raise UnidentifiedImageError('Formato no permitido')
                image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                if image.mode not in {'RGB', 'RGBA'}:
                    image = image.convert('RGBA' if 'A' in image.getbands() else 'RGB')
            except (UnidentifiedImageError, OSError, ValueError):
                flash('El archivo no contiene una imagen válida.', 'danger')
                return redirect(url_for('perfil_bp.perfil'))
            relative = f'uploads/avatars/company_{current_user.company_id}/{uuid.uuid4().hex}.webp'
            target = (Path(current_app.root_path) / 'static' / relative).resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            image.save(target, format='WEBP', quality=88, method=6)
            old_avatar = current_user.avatar_path
            current_user.avatar_path = relative
            db.session.commit()
            _delete_avatar(old_avatar)
            flash('Foto de perfil actualizada.', 'success')

        elif action == 'remove_avatar':
            old_avatar = current_user.avatar_path
            current_user.avatar_path = None
            db.session.commit()
            _delete_avatar(old_avatar)
            flash('Foto de perfil eliminada.', 'info')

        return redirect(url_for('perfil_bp.perfil'))

    currencies = ['DOP'] + [
        row.currency_code for row in ExchangeRate.query.filter_by(company_id=current_user.company_id).order_by(ExchangeRate.currency_code).all()
        if row.currency_code != 'DOP'
    ]
    return render_template(
        'perfil/perfil.html', target_user=current_user, user=current_user,
        currencies=currencies,
    )
