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
        """Save the selected warehouse and delivery locations as a preset with geocoding"""
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
            print(f"Geocoding warehouse result: {wh_address}")
            
            # Check if location exists
            existing_wh = execute_read(
                "SELECT id FROM locations WHERE ABS(lat - ?) < 0.0001 AND ABS(lon - ?) < 0.0001",
                (wh_lat, wh_lon),
                one=True
            )
            
            if existing_wh:
                wh_loc_id = existing_wh['id']
                # Force update of address info whether it exists or not
                if wh_address:
                    execute_write(
                        """UPDATE locations SET 
                           street = ?,
                           neighborhood = ?,
                           town = ?,
                           city = ?,
                           postcode = ?,
                           country = ?
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
                    print(f"Updated warehouse location in database with ID {wh_loc_id}")
            else:
                # Insert with geocoded information
                if wh_address:
                    query = """INSERT INTO locations 
                           (lat, lon, street, neighborhood, town, city, postcode, country, created_at) 
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))"""
                    params = (
                        wh_lat, wh_lon,
                        wh_address.get('street', ''),
                        wh_address.get('neighborhood', ''),
                        wh_address.get('town', ''),
                        wh_address.get('city', ''),
                        wh_address.get('postcode', ''),
                        wh_address.get('country', '')
                    )
                    wh_loc_id = execute_write(query, params)
                    print(f"Inserted new warehouse location with ID {wh_loc_id}")
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
            
            # Process destinations with geocoding
            for dest_lat, dest_lon in destinations:
                logger.info(f"Geocoding destination location: {dest_lat}, {dest_lon}")
                dest_address = geocoder.geocode_location(dest_lat, dest_lon)
                logger.info(f"Geocoding result: {dest_address}")
                
                # Check if location exists
                existing_dest = execute_read(
                    "SELECT id FROM locations WHERE lat = ? AND lon = ?",
                    (dest_lat, dest_lon),
                    one=True
                )
                
                if existing_dest:
                    dest_loc_id = existing_dest['id']
                    # Update address info if it doesn't exist
                    if dest_address:
                        logger.info(f"Updating database with geocoded information for destination")
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
                                dest_address.get('street', ''),
                                dest_address.get('neighborhood', ''),
                                dest_address.get('town', ''),
                                dest_address.get('city', ''),
                                dest_address.get('postcode', ''),
                                dest_address.get('country', ''),
                                dest_loc_id
                            )
                        )
                else:
                    # Insert with geocoded information
                    if dest_address:
                        logger.info(f"Inserting new destination location with geocoded information")
                        dest_loc_id = execute_write(
                            """INSERT INTO locations 
                               (lat, lon, street, neighborhood, town, city, postcode, country, created_at) 
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                            (
                                dest_lat, dest_lon,
                                dest_address.get('street', ''),
                                dest_address.get('neighborhood', ''),
                                dest_address.get('town', ''),
                                dest_address.get('city', ''),
                                dest_address.get('postcode', ''),
                                dest_address.get('country', '')
                            )
                        )
                    else:
                        # Fall back to basic insert if geocoding fails
                        logger.info(f"Inserting new destination location without geocoded information")
                        dest_loc_id = execute_write(
                            "INSERT INTO locations (lat, lon, created_at) VALUES (?, ?, datetime('now'))",
                            (dest_lat, dest_lon)
                        )
                
                # Add to preset_locations with is_warehouse=0
                execute_write(
                    "INSERT INTO preset_locations (preset_id, location_id, is_warehouse) VALUES (?, ?, 0)",
                    (preset_id, dest_loc_id)
                )
            
            return preset_id
        except Exception as e:
            print(f"Error saving locations: {str(e)}")
            raise e