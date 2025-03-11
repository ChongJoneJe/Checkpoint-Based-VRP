from flask import Flask, render_template, request, jsonify, redirect, url_for
import json
import os

app = Flask(__name__)

# Ensure directories exist
os.makedirs('static/data', exist_ok=True)

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
    """Save the selected warehouse and delivery locations"""
    data = request.json
    
    # Create data directory if it doesn't exist
    os.makedirs('static/data', exist_ok=True)
    
    # Save to JSON file
    with open('static/data/locations.json', 'w') as f:
        json.dump(data, f, indent=2)
    
    return jsonify({"status": "success", "message": "Locations saved successfully"})

@app.route('/get_locations', methods=['GET'])
def get_locations():
    """Retrieve previously saved locations"""
    if os.path.exists('static/data/locations.json'):
        with open('static/data/locations.json', 'r') as f:
            return jsonify(json.load(f))
    else:
        return jsonify({"warehouse": None, "destinations": []})

if __name__ == '__main__':
    app.run(debug=True)