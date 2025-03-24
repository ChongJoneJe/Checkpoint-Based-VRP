from flask import Blueprint

# Create blueprints
main_bp = Blueprint('main', __name__)
locations_bp = Blueprint('locations', __name__, url_prefix='/locations')
presets_bp = Blueprint('presets', __name__, url_prefix='/presets')
vrp_bp = Blueprint('vrp', __name__, url_prefix='/vrp')

all_blueprints = [main_bp, locations_bp, presets_bp, vrp_bp]

def setup_routes(app):
    # Import route modules here to avoid early model imports
    from routes.main import main_bp
    from routes.locations import locations_bp
    from routes.presets import presets_bp
    from routes.vrp import vrp_bp
    
    # Register blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(locations_bp)
    app.register_blueprint(presets_bp)
    app.register_blueprint(vrp_bp)