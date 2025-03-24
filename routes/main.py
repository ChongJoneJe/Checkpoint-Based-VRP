from flask import render_template
import os
import json
from routes import main_bp
from models import db
from models.location import Location, Intersection
from models.cluster import Cluster  
from models.preset import Preset, Warehouse
from sqlalchemy import desc

@main_bp.route('/')
def index():
    """Landing page with options to set up VRP problem"""
    return render_template('index.html')

@main_bp.route('/map_picker')
def map_picker():
    """Interactive map for selecting warehouse and delivery locations"""
    # Default center coordinates 
    center_lat = 3.127993  # Malaysia coordinates
    center_lng = 101.466972
    
    # Try to get the most recent warehouse from the database
    try:
        # Find the most recent preset
        latest_preset = Preset.query.order_by(desc(Preset.created_at)).first()
        
        if latest_preset:
            # Try to get warehouse for this preset
            warehouse = Warehouse.query.filter_by(preset_id=latest_preset.id).first()
            
            if warehouse:
                # Get location details
                location = Location.query.get(warehouse.location_id)
                if location:
                    center_lat = location.lat
                    center_lng = location.lon
    except Exception as e:
        print(f"Error retrieving warehouse from database: {str(e)}")
    
    return render_template('map_picker.html', center_lat=center_lat, center_lng=center_lng)

@main_bp.route('/clusters')
def clusters_page():
    """Page for analyzing location clusters"""
    return render_template('clusters.html')