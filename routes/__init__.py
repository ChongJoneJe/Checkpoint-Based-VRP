from flask import Blueprint

# Create blueprints for different sections of your app
main_bp = Blueprint('main', __name__)
locations_bp = Blueprint('locations', __name__)
presets_bp = Blueprint('presets', __name__, url_prefix='/presets')
clustering_bp = Blueprint('clustering', __name__)
vrp_bp = Blueprint('vrp', __name__)

# Import routes (after blueprint creation to avoid circular imports)
from routes.main import *
from routes.locations import *
from routes.presets import *
from routes.clustering import *
from routes.vrp import *

# List of all blueprints to register with app
all_blueprints = [main_bp, locations_bp, presets_bp, clustering_bp, vrp_bp]