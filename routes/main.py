from flask import render_template
import os
import json
from routes import main_bp

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
    
    # Check if we have previously saved locations
    if os.path.exists('static/data/locations.json'):
        try:
            with open('static/data/locations.json', 'r') as f:
                data = json.load(f)
                if data.get('warehouse'):
                    center_lat = data['warehouse'][0]
                    center_lng = data['warehouse'][1]
        except:
            pass
    
    return render_template('map_picker.html', center_lat=center_lat, center_lng=center_lng)

@main_bp.route('/clusters')
def clusters_page():
    """Page for analyzing location clusters"""
    return render_template('clusters.html')