from flask import request, jsonify, current_app
from routes import locations_bp
from services.location_service import LocationService
from algorithms.dbscan import GeoDBSCAN
from utils.database import execute_read, execute_write
import uuid
from datetime import datetime

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
        traceback.print_exc()  
        return jsonify({
            "status": "error", 
            "message": f"Error saving locations: {str(e)}"
        })

@locations_bp.route('/verify_location', methods=['GET'])
def verify_location():
    """Verify a location and check if it needs user input for address"""
    try:
        lat = float(request.args.get('lat'))
        lng = float(request.args.get('lng'))
        
        # Get the global instance
        geocoder = current_app.config['geocoder']
        
        # Try to get address with fallback
        result = geocoder.get_address_with_fallback(lat, lng)
        
        # Return the result
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)})

@locations_bp.route('/save_address', methods=['POST'])
def save_address():
    """Save user-provided address for a location"""
    try:
        data = request.json
                
        # Get form values
        lat = float(data.get('lat', 0))
        lng = float(data.get('lng', 0))
        street = data.get('street', '').strip()
        neighborhood = data.get('neighborhood', '').strip()
        
        # Debug the incoming data
        print(f"DEBUG: Saving address - street='{street}', neighborhood='{neighborhood}'")
        
        # Extract development pattern
        geocoder = current_app.config['geocoder']
        development = geocoder._extract_development_pattern(street, neighborhood)
        
        # Create address dictionary
        address = {
            'street': street,
            'neighborhood': neighborhood,
            'development': development,
            'city': data.get('city', ''),
            'postcode': data.get('postcode', ''),
            'country': data.get('country', 'Malaysia')
        }
        
        print(f"DEBUG: Address for saving: {address}")
        
        # Get warehouse_location if provided
        warehouse_location = data.get('warehouse_location')
        warehouse_lat = None
        warehouse_lon = None
        
        if warehouse_location and len(warehouse_location) == 2:
            warehouse_lat = warehouse_location[0]
            warehouse_lon = warehouse_location[1]
            
        # Save location to database
        location_id = data.get('location_id')
        
        if location_id:
            # Update existing
            execute_write(
                """UPDATE locations SET 
                   street = ?, neighborhood = ?, development = ?, 
                   city = ?, postcode = ?, country = ?
                   WHERE id = ?""",
                (
                    address['street'],
                    address['neighborhood'],
                    address['development'],
                    address['city'],
                    address['postcode'],
                    address['country'],
                    location_id
                )
            )
        else:
            # Insert new
            location_id = execute_write(
                """INSERT INTO locations 
                   (lat, lon, street, neighborhood, development, city, postcode, country)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    lat, lng, 
                    address['street'],
                    address['neighborhood'],
                    address['development'],
                    address['city'],
                    address['postcode'],
                    address['country']
                )
            )
        
        # Try to cluster the location
        try:
            _, cluster_id, is_new = geocoder.add_location_with_smart_clustering(
                lat, lng, warehouse_lat, warehouse_lon
            )
            print(f"DEBUG: Location {location_id} assigned to cluster {cluster_id} (new: {is_new})")
        except Exception as e:
            print(f"ERROR: Error in smart clustering: {e}")
        
        return jsonify({
            'status': 'success',
            'message': 'Address saved successfully',
            'location_id': location_id
        })
        
    except Exception as e:
        print(f"ERROR: Error saving address: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Error: {str(e)}'
        })