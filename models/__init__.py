from flask_sqlalchemy import SQLAlchemy

# Initialize SQLAlchemy without an app yet
db = SQLAlchemy()

# Import all models (AFTER db is defined)
from models.location import Location, Intersection 
from models.cluster import Cluster
from models.preset import Preset, Warehouse

# Make all models available when importing from models
__all__ = [
    'db', 
    'Location', 
    'Intersection', 
    'Cluster', 
    'Preset', 
    'Warehouse'
]