from flask import render_template
from routes import main_bp
from services.main_service import MainService
from services.preset_service import PresetService
from routes.presets import load_presets

@main_bp.route('/')
def index():
    """Landing page with options to set up VRP problem"""
    return render_template('index.html')

@main_bp.route('/map_picker')
def map_picker():
    """Interactive map for selecting warehouse and delivery locations"""
    center_lat, center_lng = MainService.get_default_map_center()
    
    return render_template('map_picker.html', center_lat=center_lat, center_lng=center_lng)

@main_bp.route('/clusters')
def clusters_page():
    """Page for analyzing location clusters"""
    return render_template('clusters.html')

@main_bp.route('/vrp_solver')
def vrp_solver():
    """Page for solving vehicle routing problems"""
    presets = PresetService.get_all_presets()
    return render_template('vrp_solver.html', presets=presets)
