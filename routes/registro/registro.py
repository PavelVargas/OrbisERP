from flask import Blueprint, render_template, request, redirect, url_for, flash
from db import db
from models.user.user import User

registrar_bp = Blueprint('registrar', __name__)

@registrar_bp.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':
        email = request.form.get('email')
        name = request.form.get('name')
        password = request.form.get('password')
        cedula = request.form.get('cedula')

        if not email or not name or not password:
            flash("Todos los campos son obligatorios", "error")
            return redirect(url_for('registrar.register'))

        if User.query.filter_by(email=email).first():
            flash("El email ya está registrado", "error")
            return redirect(url_for('registrar.register'))

        new_user = User(
            email=email,
            name=name,
            password=password,
            cedula=cedula,
            role='admin'  
        )

        db.session.add(new_user)
        db.session.commit()

        flash("Cuenta creada correctamente. Ahora inicia sesión para configurar tu empresa.", "success")
        return redirect(url_for('login_bp.login'))

    return render_template('registro/register.html')