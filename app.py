from flask import Flask
import osmnx as ox
import os
from utils.database import ensure_db_exists
from algorithms.dbscan import GeoDBSCAN

def create_app():
    app = Flask(__name__)
    app.secret_key = 'your-secure-random-key-here'
    
    # Ensure database exists
    ensure_db_exists()
    
    # Configure SQLAlchemy (we'll keep it for read operations)
    ors_api_key = '5b3ce3597851110001cf62481caff684775f4567ac619c56d44d6f05'
    app.config['ORS_API_KEY'] = ors_api_key
    os.environ['ORS_API_KEY'] = ors_api_key

    
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///static/data/locations.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'connect_args': {'timeout': 30, 'check_same_thread': False}
    }

    ox.settings.use_cache = True
    ox.settings.log_console = True
    ox.settings.cache_folder = os.path.join(os.path.dirname(__file__), 'cache', 'osmnx')
    ox.settings.timeout = 180
    ox.settings.memory = 8000
    
    cache_dir = os.path.join(os.path.dirname(__file__), 'cache', 'osmnx')
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)
    
    # Initialize geocoder only once
    geocoder = GeoDBSCAN(api_key=app.config.get('ORS_API_KEY'))
    app.config['geocoder'] = geocoder
    
    # Import and initialize database
    from models import db
    db.init_app(app)
    
    # Set up routes WITHOUT importing models
    from routes import setup_routes
    setup_routes(app)
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
else:
    app = create_app()