from flask import Flask
import os
from utils.database import ensure_db_exists

def create_app():
    app = Flask(__name__)
    
    # Ensure database exists
    ensure_db_exists()
    
    # Configure SQLAlchemy (we'll keep it for read operations)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///static/data/locations.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'connect_args': {'timeout': 30, 'check_same_thread': False}
    }
    
    # Import and initialize database
    from models import db
    db.init_app(app)
    
    # Set up routes WITHOUT importing models
    from routes import setup_routes
    setup_routes(app)
    
    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)