from flask import Flask, render_template, request, jsonify, redirect, url_for
import json
import os
import uuid
from datetime import datetime

app = Flask(__name__)

# Ensure directories exist
os.makedirs('static/data', exist_ok=True)

# Location to store presets
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

@app.route('/')
def index():
    """Landing page with options to set up VRP problem"""
    return render_template('index.html')

@app.route('/map_picker')
def map_picker():
    """Interactive map for selecting warehouse and delivery locations"""
    # Default center coordinates (can be your local area)
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

@app.route('/save_locations', methods=['POST'])
def save_locations():
    """Save the selected warehouse and delivery locations as a preset"""
    data = request.json
    
    if not data.get('name') or not data.get('warehouse') or not data.get('destinations'):
        return jsonify({"status": "error", "message": "Missing required data"})
    
    # Create data directory if it doesn't exist
    os.makedirs('static/data', exist_ok=True)
    
    # Save current locations to locations.json
    with open('static/data/locations.json', 'w') as f:
        json.dump({
            "warehouse": data['warehouse'],
            "destinations": data['destinations']
        }, f, indent=2)
    
    # Also save as a preset
    presets_data = load_presets()
    
    # Generate a unique ID for the preset
    preset_id = str(uuid.uuid4())
    
    # Create new preset
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
        "preset_id": preset_id
    })

@app.route('/get_locations', methods=['GET'])
def get_locations():
    """Retrieve previously saved locations"""
    if os.path.exists('static/data/locations.json'):
        with open('static/data/locations.json', 'r') as f:
            return jsonify(json.load(f))
    else:
        return jsonify({"warehouse": None, "destinations": []})

@app.route('/get_presets', methods=['GET'])
def get_presets():
    """Get all available presets"""
    return jsonify(load_presets())

@app.route('/save_preset', methods=['POST'])
def save_preset():
    """Save a new preset"""
    data = request.json
    
    if not data.get('name') or not data.get('warehouse') or not data.get('destinations'):
        return jsonify({"status": "error", "message": "Missing required data"})
    
    presets_data = load_presets()
    
    # Generate a unique ID for the preset
    preset_id = str(uuid.uuid4())
    
    # Create new preset
    new_preset = {
        "id": preset_id,
        "name": data['name'],
        "warehouse": data['warehouse'],
        "destinations": data['destinations']
    }
    
    # Add to presets list
    presets_data["presets"].append(new_preset)
    
    # Save to file
    save_presets_to_file(presets_data)
    
    return jsonify({"status": "success", "message": "Preset saved successfully", "id": preset_id})

@app.route('/get_preset/<preset_id>', methods=['GET'])
def get_preset(preset_id):
    """Get a specific preset by ID"""
    presets_data = load_presets()
    
    for preset in presets_data["presets"]:
        if preset["id"] == preset_id:
            return jsonify({"status": "success", "preset": preset})
    
    return jsonify({"status": "error", "message": "Preset not found"})

@app.route('/delete_preset/<preset_id>', methods=['DELETE'])
def delete_preset(preset_id):
    """Delete a specific preset by ID"""
    presets_data = load_presets()
    
    # Filter out the preset to delete
    presets_data["presets"] = [p for p in presets_data["presets"] if p["id"] != preset_id]
    
    # Save updated presets
    save_presets_to_file(presets_data)
    
    return jsonify({"status": "success", "message": "Preset deleted successfully"})

@app.route('/solve_vrp', methods=['POST'])
def solve_vrp():
    """Solve the VRP based on the selected preset and algorithm"""
    data = request.json
    
    if not data.get('preset_id'):
        return jsonify({"status": "error", "message": "No preset selected"})
    
    # Get the preset data
    presets_data = load_presets()
    preset = None
    for p in presets_data["presets"]:
        if p["id"] == data['preset_id']:
            preset = p
            break
    
    if not preset:
        return jsonify({"status": "error", "message": "Preset not found"})
    
    # Get algorithm and vehicle count
    algorithm = data.get('algorithm', 'nearest_neighbor')
    vehicle_count = data.get('vehicle_count', 1)
    
    # Here you would implement or call your VRP solving algorithm
    # For now, we'll return a dummy result
    import time
    import random
    
    # Record start time
    start_time = time.time()
    
    # Dummy processing time
    time.sleep(1)
    
    # Generate dummy routes
    routes = []
    destinations = list(range(len(preset["destinations"])))
    random.shuffle(destinations)
    
    # Divide destinations between vehicles
    chunk_size = len(destinations) // vehicle_count
    if chunk_size == 0:
        chunk_size = 1
    
    for i in range(vehicle_count):
        start_idx = i * chunk_size
        end_idx = start_idx + chunk_size if i < vehicle_count - 1 else len(destinations)
        
        if start_idx >= len(destinations):
            break
            
        vehicle_stops = destinations[start_idx:end_idx]
        
        # Calculate dummy distance
        distance = random.uniform(10, 50)
        
        routes.append({
            "stops": vehicle_stops,
            "distance": distance
        })
    
    # Calculate total distance and computation time
    total_distance = sum(route["distance"] for route in routes)
    computation_time = time.time() - start_time
    
    return jsonify({
        "status": "success",
        "routes": routes,
        "total_distance": total_distance,
        "computation_time": computation_time
    })

if __name__ == '__main__':
    app.run(debug=True)