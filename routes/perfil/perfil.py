from flask import Blueprint, render_template, session, redirect, url_for
from models.user.user import User

perfil_bp = Blueprint('perfil_bp', __name__)

@perfil_bp.route('/perfil')
def perfil():
    user_id = session.get('user_id')
    company_id = session.get('company_id')
    
    if not user_id:
        return redirect(url_for('login_bp.login'))
    
    current_user = User.query.get(user_id)
    
    if not current_user:
        return "Usuario no encontrado", 404

    return render_template('perfil/perfil.html', target_user=current_user, user=current_user)