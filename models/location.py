from models import db
from models.preset import Preset, Warehouse
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
    development = db.Column(db.String)
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
                             back_populates='locations')
        
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

# Association table for preset-location relationship
preset_locations = db.Table('preset_locations',
    db.Column('preset_id', db.String(36), db.ForeignKey('presets.id'), primary_key=True),
    db.Column('location_id', db.Integer, db.ForeignKey('locations.id'), primary_key=True),
    db.Column('is_warehouse', db.Boolean, default=False),
    extend_existing=True
)