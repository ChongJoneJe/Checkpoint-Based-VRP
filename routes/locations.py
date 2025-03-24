from flask import request, jsonify
import os
import uuid
from datetime import datetime
from routes import locations_bp
from utils.database import execute_read, execute_write, execute_many

@locations_bp.route('/get_locations', methods=['GET'])
def get_locations():
    """Retrieve previously saved locations from database"""
    try:
        # Get most recent preset
        preset = execute_read(
            "SELECT id, name FROM presets ORDER BY created_at DESC LIMIT 1",
            one=True
        )
        
        if not preset:
            return jsonify({"warehouse": None, "destinations": []})
        
        # Get warehouse
        warehouse_query = """
            SELECT l.lat, l.lon 
            FROM locations l
            JOIN warehouses w ON l.id = w.location_id
            WHERE w.preset_id = ?
        """
        warehouse = execute_read(warehouse_query, (preset['id'],), one=True)
        
        # Get destinations
        dest_query = """
            SELECT l.lat, l.lon 
            FROM locations l
            JOIN preset_locations pl ON l.id = pl.location_id
            WHERE pl.preset_id = ? AND pl.is_warehouse = 0
        """
        destinations = execute_read(dest_query, (preset['id'],))
        
        return jsonify({
            "warehouse": [warehouse['lat'], warehouse['lon']] if warehouse else None,
            "destinations": [[d['lat'], d['lon']] for d in destinations]
        })
        
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
        # Generate preset ID
        preset_id = str(uuid.uuid4())
        
        # Insert preset
        execute_write(
            "INSERT INTO presets (id, name, created_at) VALUES (?, ?, datetime('now'))",
            (preset_id, data['name'])
        )
        
        # Insert warehouse location
        wh_lat, wh_lon = data['warehouse']
        
        # Check if location exists
        existing_wh = execute_read(
            "SELECT id FROM locations WHERE lat = ? AND lon = ?",
            (wh_lat, wh_lon),
            one=True
        )
        
        if existing_wh:
            wh_loc_id = existing_wh['id']
        else:
            wh_loc_id = execute_write(
                "INSERT INTO locations (lat, lon, created_at) VALUES (?, ?, datetime('now'))",
                (wh_lat, wh_lon)
            )
        
        # Create warehouse entry
        execute_write(
            "INSERT INTO warehouses (preset_id, location_id) VALUES (?, ?)",
            (preset_id, wh_loc_id)
        )
        
        # Add to preset_locations with is_warehouse=1
        execute_write(
            "INSERT INTO preset_locations (preset_id, location_id, is_warehouse) VALUES (?, ?, 1)",
            (preset_id, wh_loc_id)
        )
        
        # Process destinations
        for dest in data['destinations']:
            dest_lat, dest_lon = dest
            
            # Check if location exists
            existing_dest = execute_read(
                "SELECT id FROM locations WHERE lat = ? AND lon = ?",
                (dest_lat, dest_lon),
                one=True
            )
            
            if existing_dest:
                dest_loc_id = existing_dest['id']
            else:
                dest_loc_id = execute_write(
                    "INSERT INTO locations (lat, lon, created_at) VALUES (?, ?, datetime('now'))",
                    (dest_lat, dest_lon)
                )
            
            # Add to preset_locations with is_warehouse=0
            execute_write(
                "INSERT INTO preset_locations (preset_id, location_id, is_warehouse) VALUES (?, ?, 0)",
                (preset_id, dest_loc_id)
            )
        
        return jsonify({
            "status": "success",
            "message": "Locations saved successfully",
            "preset_id": preset_id
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()  # Print full traceback for debugging
        return jsonify({
            "status": "error", 
            "message": f"Error saving locations: {str(e)}"
        })