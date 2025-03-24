from flask import Flask
import os

def create_app():
    app = Flask(__name__)
    
    # Configure SQLAlchemy
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///static/data/locations.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'connect_args': {'timeout': 30, 'check_same_thread': False}
    }
    
    # Ensure directories exist
    os.makedirs('static/data', exist_ok=True)
    
    # Import and initialize database
    from models import db
    db.init_app(app)
    
    # Set up routes without importing models directly
    from routes import setup_routes
    setup_routes(app)
    
    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)