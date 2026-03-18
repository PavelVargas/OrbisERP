from flask import Blueprint
from .sales import sales_bp
sales_bp = Blueprint('sales_bp', __name__, url_prefix='/sales')



from .core import *
from .actions import *
from .views import *
from .exports import *

