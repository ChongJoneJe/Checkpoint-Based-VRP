from flask import request, jsonify
import os
import sqlite3
from routes import locations_bp
from models import db
from models.location import Location, Intersection
from models.cluster import Cluster  
from models.preset import Preset, Warehouse
from algorithms.dbscan import GeoDBSCAN
import uuid
from datetime import datetime
from sqlalchemy import desc

@locations_bp.route('/get_locations', methods=['GET'])
def get_locations():
    """Retrieve previously saved locations from database"""
    try:
        # Try to get the most recent preset
        latest_preset = Preset.query.order_by(desc(Preset.created_at)).first()
        
        if not latest_preset:
            return jsonify({"warehouse": None, "destinations": []})
        
        # Get warehouse location
        warehouse = Warehouse.query.filter_by(preset_id=latest_preset.id).first()
        warehouse_coords = None
        
        if warehouse:
            warehouse_location = Location.query.get(warehouse.location_id)
            if warehouse_location:
                warehouse_coords = [warehouse_location.lat, warehouse_location.lon]
        
        # Get all destinations for this preset (excluding warehouse)
        destinations = []
        
        # Query for destinations using the association table
        dest_locations = db.session.query(Location).\
            join(db.Table('preset_locations')).\
            filter(db.Table('preset_locations').c.preset_id == latest_preset.id).\
            filter(db.Table('preset_locations').c.is_warehouse == False).all()
        
        for loc in dest_locations:
            destinations.append([loc.lat, loc.lon])
        
        return jsonify({
            "warehouse": warehouse_coords,
            "destinations": destinations
        })
    
    except Exception as e:
        print(f"Error retrieving locations: {str(e)}")
        return jsonify({"warehouse": None, "destinations": [], "error": str(e)})

@locations_bp.route('/save_locations', methods=['POST'])
def save_locations():
    """Save the selected warehouse and delivery locations as a preset with clustering"""
    data = request.json
    
    if not data.get('name') or not data.get('warehouse') or not data.get('destinations'):
        return jsonify({"status": "error", "message": "Missing required data"})
    
    # Create data directory if it doesn't exist
    os.makedirs('static/data', exist_ok=True)
    
    # Generate a unique ID for the preset
    preset_id = str(uuid.uuid4())
    
    try:
        # Initialize enhanced clustering with location database
        api_key = os.environ.get('ORS_API_KEY')  # Get from environment variable
        clusterer = GeoDBSCAN(
            api_key=api_key, 
            db_path='static/data/locations.db'
        )
        
        # Save preset with clustering
        result = clusterer.save_preset_with_clustering(
            preset_id=preset_id,
            preset_name=data['name'],
            warehouse=data['warehouse'],
            destinations=data['destinations']
        )
        
        return jsonify({
            "status": "success", 
            "message": "Locations saved successfully",
            "preset_id": preset_id,
            "clusters": result.get('clusters', [])
        })
    
    except Exception as e:
        return jsonify({
            "status": "error", 
            "message": f"Error saving locations: {str(e)}"
        })

@locations_bp.route('/location_info', methods=['GET'])
def location_info():
    """Get information about a location including its intersections and cluster"""
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    
    if not lat or not lon:
        return jsonify({"status": "error", "message": "Missing latitude/longitude"})
    
    try:
        lat = float(lat)
        lon = float(lon)
        
        # Initialize GeoDBSCAN with database connection
        api_key = os.environ.get('ORS_API_KEY')
        clusterer = GeoDBSCAN(api_key=api_key, db_path='static/data/locations.db')
        
        # Check if this location exists in database
        location_id, address = clusterer.find_matching_location(lat, lon)
        
        if not location_id:
            # Geocode the location
            address = clusterer.geocode_location(lat, lon)
            return jsonify({
                "status": "success",
                "exists": False,
                "geocoded_address": address
            })
            
        # Get the location from SQLAlchemy
        location = Location.query.get(location_id)
        
        if not location:
            return jsonify({
                "status": "error",
                "message": "Location found in raw DB but not in ORM"
            })
        
        # Get cluster information
        cluster_data = None
        if location.cluster:
            cluster_data = {
                "id": location.cluster.id,
                "name": location.cluster.name,
                "centroid": [location.cluster.centroid_lat, location.cluster.centroid_lon]
            }
        
        # Get intersections
        intersections_data = []
        for i, intersection in enumerate(location.intersections):
            # Find position from the association table
            position = db.session.query(db.Table('location_intersections').c.position).\
                filter(db.Table('location_intersections').c.location_id == location_id).\
                filter(db.Table('location_intersections').c.intersection_id == intersection.id).scalar() or i
                
            intersections_data.append({
                "id": intersection.id,
                "coords": [intersection.lat, intersection.lon],
                "position": position
            })
        
        # Sort by position
        intersections_data.sort(key=lambda x: x["position"])
        
        return jsonify({
            "status": "success",
            "exists": True,
            "location_id": location_id,
            "address": {
                "street": location.street,
                "neighborhood": location.neighborhood,
                "town": location.town,
                "city": location.city,
                "postcode": location.postcode,
                "country": location.country
            },
            "cluster": cluster_data,
            "intersections": intersections_data
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Error retrieving location info: {str(e)}"
        })