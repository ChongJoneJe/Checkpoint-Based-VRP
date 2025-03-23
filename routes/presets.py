from flask import request, jsonify
import os
import json
import uuid
from datetime import datetime
import numpy as np
from routes import presets_bp
from models import db, Location, Intersection, Cluster, Preset, Warehouse
from algorithms.dbscan import GeoDBSCAN

# Constants
PRESETS_FILE = 'static/data/presets.json'

def load_presets():
    """Load presets from file"""
    if os.path.exists(PRESETS_FILE):
        with open(PRESETS_FILE, 'r') as f:
            return json.load(f)
    return {"presets": []}

def save_presets_to_file(presets_data):
    """Save presets to file"""
    os.makedirs(os.path.dirname(PRESETS_FILE), exist_ok=True)
    with open(PRESETS_FILE, 'w') as f:
        json.dump(presets_data, f, indent=2)

@presets_bp.route('/get_presets', methods=['GET'])
def get_presets():
    """Get all available presets"""
    return jsonify(load_presets())

@presets_bp.route('/save_preset', methods=['POST'])
def save_preset():
    """Save a new preset using SQLAlchemy"""
    data = request.json
    
    if not data.get('name') or not data.get('warehouse') or not data.get('destinations'):
        return jsonify({"status": "error", "message": "Missing required data"})
    
    try:
        # Create new preset
        preset = Preset(
            id=str(uuid.uuid4()),
            name=data['name']
        )
        db.session.add(preset)
        
        # Process warehouse
        warehouse_loc = Location(
            lat=data['warehouse'][0],
            lon=data['warehouse'][1]
        )
        
        # Geocode warehouse
        api_key = os.environ.get('ORS_API_KEY')
        clusterer = GeoDBSCAN(api_key=api_key)
        address_info = clusterer.geocode_location(warehouse_loc.lat, warehouse_loc.lon)
        
        if address_info:
            warehouse_loc.street = address_info.get('street', '')
            warehouse_loc.neighborhood = address_info.get('neighborhood', '')
            warehouse_loc.town = address_info.get('town', '')
            warehouse_loc.city = address_info.get('city', '')
            warehouse_loc.postcode = address_info.get('postcode', '')
            warehouse_loc.country = address_info.get('country', '')
        
        db.session.add(warehouse_loc)
        
        # Create warehouse record
        warehouse = Warehouse(preset=preset, location=warehouse_loc)
        db.session.add(warehouse)
        
        # Process destinations
        destination_objs = []
        for dest in data['destinations']:
            dest_loc = Location(lat=dest[0], lon=dest[1])
            
            # Geocode destination
            address_info = clusterer.geocode_location(dest_loc.lat, dest_loc.lon)
            if address_info:
                dest_loc.street = address_info.get('street', '')
                dest_loc.neighborhood = address_info.get('neighborhood', '')
                dest_loc.town = address_info.get('town', '')
                dest_loc.city = address_info.get('city', '')
                dest_loc.postcode = address_info.get('postcode', '')
                dest_loc.country = address_info.get('country', '')
            
            db.session.add(dest_loc)
            preset.locations.append(dest_loc)
            destination_objs.append(dest_loc)
            
            # Find intersections for this destination
            intersections = clusterer.identify_intersections_for_location(
                dest_loc.lat, dest_loc.lon, 
                warehouse_loc.lat, warehouse_loc.lon
            )
            
            # Save intersections
            for intersection_data in intersections:
                intersection = Intersection(
                    lat=intersection_data['lat'], 
                    lon=intersection_data['lon']
                )
                db.session.add(intersection)
                dest_loc.intersections.append(intersection)
        
        # Run clustering if there are destinations
        if destination_objs:
            X = np.array([[loc.lat, loc.lon] for loc in destination_objs])
            clusterer.fit(X)
            
            # Create clusters
            for cluster_idx in range(clusterer.n_clusters_):
                # Get points in this cluster
                cluster_mask = clusterer.labels_ == cluster_idx
                cluster_indices = np.where(cluster_mask)[0]
                
                # Find centroid if available
                if f"cluster_{cluster_idx}" in clusterer.intersection_points:
                    centroid = clusterer.intersection_points[f"cluster_{cluster_idx}"]
                    
                    # Find neighborhood name for cluster
                    centroid_address = clusterer.geocode_location(centroid[0], centroid[1])
                    cluster_name = (centroid_address.get('neighborhood') 
                                   if centroid_address else f"Cluster {cluster_idx+1}")
                    
                    # Create cluster
                    cluster = Cluster(
                        name=cluster_name,
                        centroid_lat=centroid[0],
                        centroid_lon=centroid[1]
                    )
                    db.session.add(cluster)
                    
                    # Assign locations to cluster
                    for idx in cluster_indices:
                        destination_objs[idx].cluster = cluster
        
        # Commit all changes
        db.session.commit()
        
        return jsonify({
            "status": "success",
            "message": "Preset saved successfully",
            "id": preset.id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "status": "error",
            "message": f"Error saving preset: {str(e)}"
        })

@presets_bp.route('/get_preset/<preset_id>', methods=['GET'])
def get_preset(preset_id):
    """Get a specific preset by ID"""
    presets_data = load_presets()
    
    for preset in presets_data["presets"]:
        if preset["id"] == preset_id:
            return jsonify({"status": "success", "preset": preset})
    
    return jsonify({"status": "error", "message": "Preset not found"})

@presets_bp.route('/delete_preset/<preset_id>', methods=['DELETE'])
def delete_preset(preset_id):
    """Delete a specific preset by ID"""
    presets_data = load_presets()
    
    # Filter out the preset to delete
    presets_data["presets"] = [p for p in presets_data["presets"] if p["id"] != preset_id]
    
    # Save updated presets
    save_presets_to_file(presets_data)
    
    return jsonify({"status": "success", "message": "Preset deleted successfully"})