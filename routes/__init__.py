from flask import Blueprint

# Create blueprints
main_bp = Blueprint('main', __name__)
locations_bp = Blueprint('locations', __name__, url_prefix='/locations')
presets_bp = Blueprint('presets', __name__, url_prefix='/presets')
vrp_bp = Blueprint('vrp', __name__, url_prefix='/vrp')

all_blueprints = [main_bp, locations_bp, presets_bp, vrp_bp]

def setup_routes(app):
    from routes.main import main_bp
    from routes.presets import presets_bp
    from routes.locations import locations_bp
    from routes.clustering import clustering_bp
    from routes.vrp import vrp_bp
    from routes.debug import debug_bp
    from routes.checkpoints import checkpoints_bp
    from routes.vrp_testing import vrp_testing_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(presets_bp, url_prefix='/presets')
    app.register_blueprint(locations_bp, url_prefix='/locations')
    app.register_blueprint(clustering_bp, url_prefix='/clustering')
    app.register_blueprint(vrp_bp, url_prefix='/vrp')
    app.register_blueprint(debug_bp)
    app.register_blueprint(checkpoints_bp, url_prefix='/checkpoint')
    app.register_blueprint(vrp_testing_bp)