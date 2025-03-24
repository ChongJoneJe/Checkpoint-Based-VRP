from models import db
from datetime import datetime
import uuid

class Preset(db.Model):
    """A saved set of locations"""
    __tablename__ = 'presets'
    __table_args__ = {'extend_existing': True} 
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
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
    preset = db.relationship('Preset')
    location = db.relationship('Location')
    
    def __repr__(self):
        return f"<Warehouse {self.id}: for preset {self.preset_id}>"