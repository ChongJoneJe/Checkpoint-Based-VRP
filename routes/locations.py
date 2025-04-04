from flask import request, jsonify, current_app
from routes import locations_bp
from services.location_service import LocationService
from algorithms.dbscan import GeoDBSCAN
from utils.database import execute_read

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
    """Save user-provided address for a location and cluster it properly"""
    try:
        data = request.json
        
        # Extract base components
        street = data.get('street', '').strip()
        section = data.get('section', '').strip().upper()
        subsection = data.get('subsection', '').strip()
        
        # Format street with section/subsection properly
        # This ensures consistency with geocoded addresses
        if section and subsection:
            # Check if street already includes the section/subsection
            section_pattern = f"{section}/{subsection}"
            if section_pattern.lower() not in street.lower():
                # Proper format: "Jalan Setia Duta U13/21Y"
                if street:
                    # Append section/subsection if street doesn't already have it
                    street = f"{street} {section}/{subsection}"
                else:
                    # Default format if no street name provided
                    street = f"Jalan {section}/{subsection}"
        
        # Create complete address dictionary
        address = {
            'street': street,
            'neighborhood': data.get('neighborhood', ''),
            'town': data.get('city', ''),  # Map city to town field
            'city': data.get('city', ''),
            'postcode': data.get('postcode', ''),
            'country': data.get('country', 'Malaysia')
        }
        
        print(f"DEBUG: Formatted street name: {street}")
        
        # Check if location exists
        from repositories.location_repository import LocationRepository
        existing_loc = LocationRepository.find_by_coordinates(data['lat'], data['lng'])
        
        if existing_loc:
            # Update existing location with user-provided address
            LocationRepository.update_address(existing_loc['id'], address)
            location_id = existing_loc['id']
        else:
            # Insert new location with user-provided address
            location_id = LocationRepository.insert(data['lat'], data['lng'], address)
        
        print(f"DEBUG: Saved user-provided address for location {location_id}: {address['street']}")
        
        # Perform clustering with the saved address
        # This ensures consistent clustering with automatically geocoded addresses
        try:
            # Get the geocoder instance
            geocoder = current_app.config['geocoder']
            
            # Get warehouse location (needed for clustering)
            warehouse = execute_read(
                """SELECT lat, lon FROM locations 
                   WHERE id IN (SELECT warehouse_id FROM presets ORDER BY id DESC LIMIT 1)""",
                one=True
            )
            
            if warehouse:
                wh_lat, wh_lon = warehouse['lat'], warehouse['lon']
            else:
                # Use a default if no warehouse set yet
                wh_lat, wh_lon = data['lat'], data['lng']
            
            # Perform clustering
            result = geocoder.add_location_with_smart_clustering(
                data['lat'], data['lng'], wh_lat, wh_lon
            )
            
            if result and isinstance(result, tuple) and len(result) >= 2:
                _, cluster_id, is_new = result
                
                # Get cluster name for response
                cluster_info = None
                if cluster_id:
                    cluster_info = execute_read(
                        "SELECT name FROM clusters WHERE id = ?",
                        (cluster_id,),
                        one=True
                    )
                
                return jsonify({
                    'status': 'success',
                    'address': address,
                    'location_id': location_id,
                    'cluster_id': cluster_id,
                    'cluster_name': cluster_info['name'] if cluster_info else 'None',
                    'is_new_cluster': is_new
                })
            else:
                return jsonify({
                    'status': 'success',
                    'address': address,
                    'location_id': location_id,
                    'cluster_id': None,
                    'cluster_name': 'Unclustered',
                    'is_new_cluster': False
                })
                
        except Exception as clustering_error:
            print(f"WARNING: Clustering failed: {str(clustering_error)}")
            # Return success anyway since the address was saved
            return jsonify({
                'status': 'success',
                'address': address,
                'location_id': location_id,
                'cluster_id': None,
                'cluster_name': 'Unclustered (clustering error)',
                'is_new_cluster': False
            })
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)})