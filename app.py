from flask import Flask
import os

from models import db
from routes import all_blueprints

app = Flask(__name__)

# Configure SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///static/data/locations.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db.init_app(app)

# Ensure directories exist
os.makedirs('static/data', exist_ok=True)

# Register all blueprints
for blueprint in all_blueprints:
    app.register_blueprint(blueprint)

if __name__ == '__main__':
    app.run(debug=True)