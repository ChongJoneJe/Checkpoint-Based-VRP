from flask import request, jsonify
import os
import json
import sqlite3  # Import sqlite3 for database operations
from routes import locations_bp  # Import the blueprint
from models import db, Location, Intersection
from algorithms.dbscan import GeoDBSCAN
from utils import load_presets, save_presets_to_file
import uuid
from datetime import datetime

@locations_bp.route('/get_locations', methods=['GET'])
def get_locations():
    """Retrieve previously saved locations"""
    # Notice we use locations_bp.route instead of app.route
    if os.path.exists('static/data/locations.json'):
        with open('static/data/locations.json', 'r') as f:
            return jsonify(json.load(f))
    else:
        return jsonify({"warehouse": None, "destinations": []})

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
        
        # Also save current locations to locations.json for compatibility
        with open('static/data/locations.json', 'w') as f:
            json.dump({
                "warehouse": data['warehouse'],
                "destinations": data['destinations']
            }, f, indent=2)
        
        # Add preset to presets.json
        from routes.presets import load_presets, save_presets_to_file
        presets_data = load_presets()
        
        # Create new preset entry
        new_preset = {
            "id": preset_id,
            "name": data['name'],
            "warehouse": data['warehouse'],
            "destinations": data['destinations'],
            "created_at": datetime.now().isoformat()
        }
        
        # Add to presets list
        presets_data["presets"].append(new_preset)
        
        # Save to file
        save_presets_to_file(presets_data)
        
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
            
        # Location exists, get its intersections and cluster
        conn = sqlite3.connect('static/data/locations.db')
        c = conn.cursor()
        
        # Get cluster information
        c.execute('''
            SELECT c.id, c.name, c.centroid_lat, c.centroid_lon
            FROM clusters c
            JOIN location_clusters lc ON c.id = lc.cluster_id
            WHERE lc.location_id = ?
        ''', (location_id,))
        
        cluster_data = c.fetchone()
        cluster = None
        
        if cluster_data:
            cluster = {
                "id": cluster_data[0],
                "name": cluster_data[1],
                "centroid": [cluster_data[2], cluster_data[3]]
            }
            
        # Get intersections
        c.execute('''
            SELECT i.id, i.lat, i.lon, li.position
            FROM intersections i
            JOIN location_intersections li ON i.id = li.intersection_id
            WHERE li.location_id = ?
            ORDER BY li.position
        ''', (location_id,))
        
        intersections = []
        for row in c.fetchall():
            intersections.append({
                "id": row[0],
                "coords": [row[1], row[2]],
                "position": row[3]
            })
            
        conn.close()
        
        return jsonify({
            "status": "success",
            "exists": True,
            "location_id": location_id,
            "address": address,
            "cluster": cluster,
            "intersections": intersections
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Error retrieving location info: {str(e)}"
        })