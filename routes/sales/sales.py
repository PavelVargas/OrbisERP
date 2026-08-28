from flask import Blueprint

sales_bp = Blueprint('sales_bp', __name__, url_prefix='/sales')

from .core import *
from .actions import *
from .views import *
from .exports import *
from .quotes import *
