from flask import request, jsonify
from routes import locations_bp
from services.location_service import LocationService

@locations_bp.route('/get_locations', methods=['GET'])
def get_locations():
    """Retrieve previously saved locations from database"""
    try:
        location_data = LocationService.get_locations()
        return jsonify(location_data)
    except Exception as e:
        print(f"Error retrieving locations: {str(e)}")
        return jsonify({"warehouse": None, "destinations": []})

@locations_bp.route('/save_locations', methods=['POST'])
def save_locations():
    """Save the selected warehouse and delivery locations as a preset with clustering"""
    data = request.json
    
    if not data.get('name') or not data.get('warehouse') or not data.get('destinations'):
        return jsonify({"status": "error", "message": "Missing required data"})
    
    try:
        preset_id = LocationService.save_locations(
            data['name'],
            data['warehouse'],
            data['destinations']
        )
        
        return jsonify({
            "status": "success",
            "message": "Locations saved successfully with geocoding information",
            "preset_id": preset_id
        })
    except Exception as e:
        import traceback
        traceback.print_exc()  # Print full traceback for debugging
        return jsonify({
            "status": "error", 
            "message": f"Error saving locations: {str(e)}"
        })