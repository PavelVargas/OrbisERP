from flask import Blueprint, render_template, request, redirect, url_for, flash
from db import db
from models.user.user import User
from security import password_error

registrar_bp = Blueprint('registrar', __name__)

@registrar_bp.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        name = (request.form.get('name') or '').strip()
        password = request.form.get('password')
        cedula = request.form.get('cedula')

        if not email or not name or not password:
            flash("Todos los campos son obligatorios", "error")
            return redirect(url_for('registrar.register'))

        issue = password_error(password)
        if issue:
            flash(issue, 'error')
            return redirect(url_for('registrar.register'))

        if User.query.filter_by(email=email).first():
            flash("El email ya está registrado", "error")
            return redirect(url_for('registrar.register'))

        new_user = User(
            email=email,
            name=name,
            password='pending-hash',
            cedula=cedula,
            role='admin'  
        )
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        flash("Cuenta creada correctamente. Ahora inicia sesión para configurar tu empresa.", "success")
        return redirect(url_for('login_bp.login'))

    return render_template('registro/register.html')
