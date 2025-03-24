from flask import request, jsonify
import os
import json
import uuid
from datetime import datetime
import numpy as np
from routes import presets_bp
from models import db
from models.location import Location, Intersection
from models.cluster import Cluster  
from models.preset import Preset, Warehouse
from algorithms.dbscan import GeoDBSCAN
from sqlalchemy import desc

@presets_bp.route('/get_presets', methods=['GET'])
def get_presets():
    """Get all available presets from the database"""
    try:
        # Query all presets ordered by date descending
        presets = Preset.query.order_by(desc(Preset.created_at)).all()
        
        # Format response
        presets_data = []
        for preset in presets:
            # Get all locations for this preset
            locations = db.session.query(Location).\
                join(db.Table('preset_locations')).\
                filter(db.Table('preset_locations').c.preset_id == preset.id).all()
            
            # Get warehouse location
            warehouse = Warehouse.query.filter_by(preset_id=preset.id).first()
            warehouse_coords = None
            
            if warehouse:
                warehouse_location = Location.query.get(warehouse.location_id)
                if warehouse_location:
                    warehouse_coords = [warehouse_location.lat, warehouse_location.lon]
            
            # Get all destination locations (excluding warehouse)
            destinations = []
            for location in locations:
                # Check if this is not the warehouse location
                if not warehouse or location.id != warehouse.location_id:
                    destinations.append([location.lat, location.lon])
            
            presets_data.append({
                'id': preset.id,
                'name': preset.name,
                'warehouse': warehouse_coords,
                'destinations': destinations,
                'created_at': preset.created_at.isoformat()
            })
        
        return jsonify({"presets": presets_data})
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@presets_bp.route('/save_preset', methods=['POST'])
def save_preset():
    """Save a preset of locations to the database"""
    data = request.json
    
    if not data.get('name') or not data.get('warehouse') or not data.get('destinations'):
        return jsonify({"status": "error", "message": "Missing required data"})
    
    try:
        # Generate a unique ID for the preset
        preset_id = str(uuid.uuid4())
        
        # Wrap database operations in a context manager
        with db.session.begin():
            # Create new preset object
            preset = Preset(id=preset_id, name=data['name'])
            db.session.add(preset)
            
            # Add warehouse location
            warehouse_lat, warehouse_lon = data['warehouse']
            
            # Check if this location already exists
            warehouse_location = Location.query.filter_by(
                lat=warehouse_lat, 
                lon=warehouse_lon
            ).first()
            
            if not warehouse_location:
                # Create new location
                warehouse_location = Location(
                    lat=warehouse_lat,
                    lon=warehouse_lon
                )
                db.session.add(warehouse_location)
                db.session.flush()  # Get the ID
            
            # Create warehouse entry
            warehouse = Warehouse(
                preset_id=preset_id,
                location_id=warehouse_location.id
            )
            db.session.add(warehouse)
            
            # Add link in preset_locations table
            db.session.execute(
                db.Table('preset_locations').insert().values(
                    preset_id=preset_id,
                    location_id=warehouse_location.id,
                    is_warehouse=True
                )
            )
            
            # Add all destinations
            for dest_coords in data['destinations']:
                dest_lat, dest_lon = dest_coords
                
                # Check if this location already exists
                dest_location = Location.query.filter_by(
                    lat=dest_lat, 
                    lon=dest_lon
                ).first()
                
                if not dest_location:
                    # Create new location
                    dest_location = Location(
                        lat=dest_lat,
                        lon=dest_lon
                    )
                    db.session.add(dest_location)
                    db.session.flush()  # Get the ID
                
                # Add link in preset_locations table
                db.session.execute(
                    db.Table('preset_locations').insert().values(
                        preset_id=preset_id,
                        location_id=dest_location.id,
                        is_warehouse=False
                    )
                )
        
        return jsonify({
            "status": "success",
            "message": "Preset saved successfully",
            "preset_id": preset_id
        })
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@presets_bp.route('/get_preset/<preset_id>', methods=['GET'])
def get_preset(preset_id):
    """Get a specific preset by ID from the database"""
    try:
        # Find preset by ID
        preset = Preset.query.get(preset_id)
        
        if not preset:
            return jsonify({"status": "error", "message": "Preset not found"})
        
        # Get warehouse location
        warehouse = Warehouse.query.filter_by(preset_id=preset_id).first()
        warehouse_coords = None
        
        if warehouse:
            warehouse_location = Location.query.get(warehouse.location_id)
            if warehouse_location:
                warehouse_coords = [warehouse_location.lat, warehouse_location.lon]
        
        # Get all destinations (excluding warehouse)
        destinations = []
        
        locations = db.session.query(Location).\
            join(db.Table('preset_locations')).\
            filter(db.Table('preset_locations').c.preset_id == preset_id).\
            filter(db.Table('preset_locations').c.is_warehouse == False).all()
            
        for location in locations:
            destinations.append([location.lat, location.lon])
        
        preset_data = {
            'id': preset.id,
            'name': preset.name,
            'warehouse': warehouse_coords,
            'destinations': destinations,
            'created_at': preset.created_at.isoformat()
        }
        
        return jsonify({
            "status": "success",
            "preset": preset_data
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@presets_bp.route('/delete_preset/<preset_id>', methods=['DELETE'])
def delete_preset(preset_id):
    """Delete a preset by ID from the database"""
    try:
        # Find preset by ID
        preset = Preset.query.get(preset_id)
        
        if not preset:
            return jsonify({"status": "error", "message": "Preset not found"})
        
        # Delete warehouse entry
        warehouse = Warehouse.query.filter_by(preset_id=preset_id).first()
        if warehouse:
            db.session.delete(warehouse)
        
        # Delete preset associations from preset_locations table
        db.session.execute(
            db.Table('preset_locations').delete().where(
                db.Table('preset_locations').c.preset_id == preset_id
            )
        )
        
        # Delete the preset itself
        db.session.delete(preset)
        
        # Commit all changes
        db.session.commit()
        
        return jsonify({
            "status": "success",
            "message": "Preset deleted successfully"
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)})

def load_presets():
    """Load all presets from the database - function for internal use by other routes"""
    try:
        # Query all presets ordered by date descending
        presets = Preset.query.order_by(desc(Preset.created_at)).all()
        
        # Format response
        presets_data = []
        for preset in presets:
            # Get warehouse location
            warehouse = Warehouse.query.filter_by(preset_id=preset.id).first()
            warehouse_coords = None
            
            if warehouse:
                warehouse_location = Location.query.get(warehouse.location_id)
                if warehouse_location:
                    warehouse_coords = [warehouse_location.lat, warehouse_location.lon]
            
            # Get all destinations (excluding warehouse)
            destinations = []
            
            locations = db.session.query(Location).\
                join(db.Table('preset_locations')).\
                filter(db.Table('preset_locations').c.preset_id == preset.id).\
                filter(db.Table('preset_locations').c.is_warehouse == False).all()
                
            for location in locations:
                destinations.append([location.lat, location.lon])
            
            presets_data.append({
                'id': preset.id,
                'name': preset.name,
                'warehouse': warehouse_coords,
                'destinations': destinations,
                'created_at': preset.created_at.isoformat() if preset.created_at else None
            })
        
        return {"presets": presets_data}
        
    except Exception as e:
        print(f"Error loading presets: {str(e)}")
        return {"presets": []}

