"""Sales package public blueprint.

The blueprint is defined and populated in ``routes.sales.sales``.  Re-export the
same object here so ``from routes.sales import sales_bp`` registers the routes
that core/actions/views/exports/quotes decorate.
"""

from .sales import sales_bp

__all__ = ['sales_bp']
