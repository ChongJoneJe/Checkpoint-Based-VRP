import uuid
from datetime import datetime
from utils.database import execute_read, execute_write
from algorithms.dbscan import GeoDBSCAN
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
        
        return {
            "warehouse": [warehouse['lat'], warehouse['lon']] if warehouse else None,
            "destinations": [[d['lat'], d['lon']] for d in destinations]
        }
    
    @staticmethod
    def save_locations(name, warehouse, destinations):
        """Save the selected warehouse and delivery locations as a preset with clustering"""
        geocoder = GeoDBSCAN()
        
        try:
            # Generate preset ID
            preset_id = str(uuid.uuid4())
            
            # Insert preset
            execute_write(
                "INSERT INTO presets (id, name, created_at) VALUES (?, ?, datetime('now'))",
                (preset_id, name)
            )
            
            # Process warehouse location with geocoding
            wh_lat, wh_lon = warehouse
            wh_address = geocoder.geocode_location(wh_lat, wh_lon)
            
            # Check if location exists
            existing_wh = execute_read(
                "SELECT id FROM locations WHERE ABS(lat - ?) < 0.0001 AND ABS(lon - ?) < 0.0001",
                (wh_lat, wh_lon),
                one=True
            )
            
            if existing_wh:
                wh_loc_id = existing_wh['id']
                # Update address info if needed
                if wh_address:
                    execute_write(
                        """UPDATE locations SET 
                           street = COALESCE(street, ?),
                           neighborhood = COALESCE(neighborhood, ?),
                           town = COALESCE(town, ?),
                           city = COALESCE(city, ?),
                           postcode = COALESCE(postcode, ?),
                           country = COALESCE(country, ?)
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
                # Insert with geocoded information
                if wh_address:
                    wh_loc_id = execute_write(
                        """INSERT INTO locations 
                           (lat, lon, street, neighborhood, town, city, postcode, country, created_at) 
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
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
                else:
                    # Fall back to basic insert
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
            
            # Process destinations with smart clustering
            for dest_lat, dest_lon in destinations:
                try:
                    # Try the alternative method first
                    try:
                        dest_loc_id, cluster_id, is_new_cluster = geocoder.add_location_with_smart_clustering_alt(
                            dest_lat, dest_lon, wh_lat, wh_lon
                        )
                    except (ImportError, AttributeError):
                        # If alt method not available, fall back to original
                        dest_loc_id, cluster_id, is_new_cluster = geocoder.add_location_with_smart_clustering(
                            dest_lat, dest_lon, wh_lat, wh_lon
                        )
                    
                    if dest_loc_id:
                        # Add to preset_locations with is_warehouse=0
                        execute_write(
                            "INSERT INTO preset_locations (preset_id, location_id, is_warehouse) VALUES (?, ?, 0)",
                            (preset_id, dest_loc_id)
                        )
                    else:
                        print(f"Warning: Failed to add location ({dest_lat}, {dest_lon}) to database")
                except Exception as e:
                    print(f"Error processing destination ({dest_lat}, {dest_lon}): {str(e)}")
            
            return preset_id
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error saving locations: {str(e)}")
            return None