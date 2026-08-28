from db import db
from models.sales.sales import Sale
from models.user.user import User


def actor(user_id):
    return db.session.get(User, user_id) if user_id else None


def can_view_all_sales(user):
    return bool(user and (
        user.role in {'admin', 'superadmin'}
        or user.has_permission('sales.cancel')
        or user.has_permission('audits.view')
    ))


def can_mutate_all_sales(user):
    return bool(user and (
        user.role in {'admin', 'superadmin'}
        or user.has_permission('sales.cancel')
    ))


def visible_sales_query(company_id, user_id):
    user = actor(user_id)
    query = Sale.query.filter_by(company_id=company_id)
    if not can_view_all_sales(user):
        query = query.filter_by(user_id=user_id)
    return query


def editable_sales_query(company_id, user_id):
    user = actor(user_id)
    query = Sale.query.filter_by(company_id=company_id)
    if not can_mutate_all_sales(user):
        query = query.filter_by(user_id=user_id)
    return query
