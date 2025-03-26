from models import db
from datetime import datetime
import uuid

class Location(db.Model):
    """A geographic location with geocoding information"""
    __tablename__ = 'locations'
    __table_args__ = {'extend_existing': True} 
    
    id = db.Column(db.Integer, primary_key=True)
    lat = db.Column(db.Float, nullable=False)
    lon = db.Column(db.Float, nullable=False)
    street = db.Column(db.String)
    neighborhood = db.Column(db.String)
    town = db.Column(db.String)
    city = db.Column(db.String)
    postcode = db.Column(db.String)
    country = db.Column(db.String)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    cluster_id = db.Column(db.Integer, db.ForeignKey('clusters.id'), nullable=True)

    cluster = db.relationship('Cluster', back_populates='locations')
    
    # Relationship with intersections
    intersections = db.relationship('Intersection', 
                                   secondary='location_intersections',
                                   backref=db.backref('locations', lazy='dynamic'))
    
    # Define relationship to presets through preset_locations table
    presets = db.relationship('Preset', 
                             secondary='preset_locations',
                             backref=db.backref('locations', lazy='dynamic'))
    
    def __repr__(self):
        return f"<Location {self.id}: {self.lat}, {self.lon}>"

class Intersection(db.Model):
    """An intersection point identified along routes"""
    __tablename__ = 'intersections'
    __table_args__ = {'extend_existing': True} 
    
    id = db.Column(db.Integer, primary_key=True)
    lat = db.Column(db.Float, nullable=False)
    lon = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<Intersection {self.id}: {self.lat}, {self.lon}>"

# Association table for location-intersection relationship
location_intersections = db.Table('location_intersections',
    db.Column('location_id', db.Integer, db.ForeignKey('locations.id'), primary_key=True),
    db.Column('intersection_id', db.Integer, db.ForeignKey('intersections.id'), primary_key=True),
    db.Column('position', db.Integer, nullable=False),
    extend_existing=True
)

class Preset(db.Model):
    """A saved set of locations"""
    __tablename__ = 'presets'
    __table_args__ = {'extend_existing': True} 
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    locations = db.relationship('Location', secondary='preset_locations', back_populates='presets')
    warehouse = db.relationship('Warehouse', uselist=False, back_populates='preset')
    
    def __repr__(self):
        return f"<Preset {self.id}: {self.name}>"

# Association table for preset-location relationship
preset_locations = db.Table('preset_locations',
    db.Column('preset_id', db.String(36), db.ForeignKey('presets.id'), primary_key=True),
    db.Column('location_id', db.Integer, db.ForeignKey('locations.id'), primary_key=True),
    db.Column('is_warehouse', db.Boolean, default=False),
    extend_existing=True
)

class Warehouse(db.Model):
    """A warehouse location"""
    __tablename__ = 'warehouses'
    __table_args__ = {'extend_existing': True} 
    
    id = db.Column(db.Integer, primary_key=True)
    preset_id = db.Column(db.String(36), db.ForeignKey('presets.id'), unique=True)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), unique=True)
    
    # Relationships
    preset = db.relationship('Preset', back_populates='warehouse')
    location = db.relationship('Location')
    
    def __repr__(self):
        return f"<Warehouse {self.id}: {self.preset_id}>"