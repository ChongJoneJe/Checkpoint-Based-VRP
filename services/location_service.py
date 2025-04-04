import uuid
import os
from datetime import datetime
from utils.database import execute_read, execute_write
from repositories.cluster_repository import ClusterRepository
from repositories.location_repository import LocationRepository
from algorithms.dbscan import GeoDBSCAN
from flask import current_app
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LocationService:
    @staticmethod
    def get_locations():
        """Retrieve previously saved locations from database"""
        # Get most recent preset
        preset = execute_read(
            "SELECT id, name FROM presets ORDER BY created_at DESC LIMIT 1",
            one=True
        )
        
        if not preset:
            return {"warehouse": None, "destinations": []}
        
        # Get warehouse using the correct schema (preset_locations with is_warehouse flag)
        warehouse_query = """
            SELECT l.lat, l.lon 
            FROM locations l
            JOIN preset_locations pl ON l.id = pl.location_id
            WHERE pl.preset_id = ? AND pl.is_warehouse = 1
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
        
        return {
            "warehouse": [warehouse['lat'], warehouse['lon']] if warehouse else None,
            "destinations": [[d['lat'], d['lon']] for d in destinations]
        }
    
    @staticmethod
    def save_locations(name, warehouse, destinations):
        """Save warehouse and destinations with geocoding, then cluster them"""
        try:
            # Generate a UUID for the preset ID (since it's TEXT in schema, not INTEGER)
            preset_id = str(uuid.uuid4())
            
            # Create the preset first
            execute_write(
                "INSERT INTO presets (id, name) VALUES (?, ?)",
                (preset_id, name)
            )
            
            print(f"DEBUG: Created preset with ID {preset_id}")
            
            # Use the global geocoder instance
            geocoder = current_app.config['geocoder']
            
            # Save warehouse location but DON'T cluster it
            wh_lat, wh_lon = warehouse
            wh_address = geocoder.geocode_location(wh_lat, wh_lon)
            
            # Process warehouse
            if not wh_address:
                wh_address = {'street': '', 'neighborhood': '', 'town': '', 'city': '', 'postcode': '', 'country': ''}
                
            # Check if location already exists
            existing_loc = execute_read(
                "SELECT id FROM locations WHERE ABS(lat - ?) < 0.0001 AND ABS(lon - ?) < 0.0001",
                (wh_lat, wh_lon),
                one=True
            )
            
            if existing_loc:
                wh_loc_id = existing_loc['id']
                # Update address if needed
                execute_write(
                    """UPDATE locations SET 
                       street = ?, neighborhood = ?, town = ?, city = ?, postcode = ?, country = ?
                       WHERE id = ?""",
                    (
                        wh_address.get('street', ''),
                        wh_address.get('neighborhood', ''),
                        wh_address.get('town', ''),
                        wh_address.get('city', ''),
                        wh_address.get('postcode', ''),
                        wh_address.get('country', ''),
                        wh_loc_id
                    )
                )
            else:
                wh_loc_id = execute_write(
                    """INSERT INTO locations 
                       (lat, lon, street, neighborhood, town, city, postcode, country)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        wh_lat, wh_lon, 
                        wh_address.get('street', ''),
                        wh_address.get('neighborhood', ''),
                        wh_address.get('town', ''),
                        wh_address.get('city', ''),
                        wh_address.get('postcode', ''),
                        wh_address.get('country', '')
                    )
                )
            
            # Link warehouse to preset with is_warehouse flag in preset_locations
            execute_write(
                "INSERT INTO preset_locations (preset_id, location_id, is_warehouse) VALUES (?, ?, 1)",
                (preset_id, wh_loc_id)
            )
            
            # Also add to warehouses table for backwards compatibility
            execute_write(
                "INSERT INTO warehouses (preset_id, location_id) VALUES (?, ?)",
                (preset_id, wh_loc_id)
            )
            
            print(f"DEBUG: Added warehouse at location {wh_loc_id} to preset {preset_id}")
            
            # Now process destinations with clustering
            for dest in destinations:
                dest_lat, dest_lon = dest
                
                # Don't cluster if it's the same as warehouse
                if abs(dest_lat - wh_lat) < 0.0001 and abs(dest_lon - wh_lon) < 0.0001:
                    print(f"DEBUG: Destination {dest_lat}, {dest_lon} is same as warehouse - skipping")
                    continue
                    
                # Use the smart clustering which geocodes and clusters in one step
                result = geocoder.add_location_with_smart_clustering(dest_lat, dest_lon, wh_lat, wh_lon)
                
                if result and isinstance(result, tuple) and len(result) >= 2:
                    dest_loc_id, cluster_id, is_new_cluster = result
                    
                    # Link destination to preset using preset_locations table
                    execute_write(
                        "INSERT INTO preset_locations (preset_id, location_id, is_warehouse) VALUES (?, ?, 0)",
                        (preset_id, dest_loc_id)
                    )
                    
                    if is_new_cluster:
                        print(f"DEBUG: Created new cluster for destination {dest_loc_id}")
                    else:
                        print(f"DEBUG: Added destination {dest_loc_id} to existing cluster {cluster_id}")
                else:
                    print(f"WARNING: Smart clustering failed for {dest_lat}, {dest_lon}")
            
            return preset_id
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error in save_locations: {str(e)}")
            raise