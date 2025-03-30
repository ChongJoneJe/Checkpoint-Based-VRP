from utils.database import execute_read, execute_write, execute_many

class LocationRepository:
    """Handles all database operations related to locations"""
    
    @staticmethod
    def find_by_coordinates(lat, lon, tolerance=0.0001):
        """Find location by coordinates with tolerance"""
        return execute_read(
            """SELECT id, street, neighborhood, town, city, postcode, country
               FROM locations
               WHERE ABS(lat - ?) < ? AND ABS(lon - ?) < ?""",
            (lat, tolerance, lon, tolerance),
            one=True
        )
    
    @staticmethod
    def insert(lat, lon, address_data):
        """Insert a new location with address data"""
        return execute_write(
            """INSERT INTO locations 
               (lat, lon, street, neighborhood, town, city, postcode, country)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                lat, lon, 
                address_data.get('street', ''),
                address_data.get('neighborhood', ''),
                address_data.get('town', ''),
                address_data.get('city', ''),
                address_data.get('postcode', ''),
                address_data.get('country', '')
            )
        )
    
    @staticmethod
    def update_address(location_id, address_data):
        """Update address data for existing location"""
        return execute_write(
            """UPDATE locations SET 
               street = COALESCE(street, ?),
               neighborhood = COALESCE(neighborhood, ?),
               town = COALESCE(town, ?),
               city = COALESCE(city, ?),
               postcode = COALESCE(postcode, ?),
               country = COALESCE(country, ?)
               WHERE id = ?""",
            (
                address_data.get('street', ''),
                address_data.get('neighborhood', ''),
                address_data.get('town', ''),
                address_data.get('city', ''),
                address_data.get('postcode', ''),
                address_data.get('country', ''),
                location_id
            )
        )
    
    @staticmethod
    def find_matching_street(street, exclude_location_id=None):
        """Find locations with the same street, excluding a specific location"""
        query = """
            SELECT l.id, l.lat, l.lon, l.street, l.neighborhood, l.city, lc.cluster_id
            FROM locations l
            LEFT JOIN location_clusters lc ON l.id = lc.location_id
            WHERE l.street = ? AND l.street != ''
        """
        
        params = [street]
        
        if exclude_location_id:
            query += " AND l.id != ?"
            params.append(exclude_location_id)
        
        return execute_read(query, params)
    
    @staticmethod
    def find_matching_neighborhood(neighborhood, exclude_location_id=None):
        """Find locations with the same neighborhood, excluding a specific location"""
        query = """
            SELECT l.id, l.lat, l.lon, l.street, l.neighborhood, l.city, lc.cluster_id
            FROM locations l
            LEFT JOIN location_clusters lc ON l.id = lc.location_id
            WHERE l.neighborhood = ? AND l.neighborhood != ''
        """
        
        params = [neighborhood]
        
        if exclude_location_id:
            query += " AND l.id != ?"
            params.append(exclude_location_id)
        
        return execute_read(query, params)
    
    @staticmethod
    def get_locations_by_cluster(cluster_id):
        """Get all locations in a specific cluster"""
        return execute_read(
            """SELECT l.id, l.lat, l.lon, l.street, l.neighborhood, l.town, l.city, l.postcode, l.country
               FROM locations l
               JOIN location_clusters lc ON l.id = lc.location_id
               WHERE lc.cluster_id = ?""",
            (cluster_id,)
        )
    
    @staticmethod
    def get_all_locations():
        """Get all locations in the database"""
        return execute_read(
            """SELECT l.id, l.lat, l.lon, l.street, l.neighborhood, l.town, l.city, l.postcode, l.country,
                     lc.cluster_id
               FROM locations l
               LEFT JOIN location_clusters lc ON l.id = lc.location_id"""
        )
    
    @staticmethod
    def find_pattern_matches(pattern, exclude_location_id=None):
        """Find locations with matching development pattern in street names"""
        pattern_with_wildcards = f"%{pattern}%"
        
        query = """
            SELECT l.id, l.lat, l.lon, l.street, l.neighborhood, l.city, lc.cluster_id
            FROM locations l
            LEFT JOIN location_clusters lc ON l.id = lc.location_id
            WHERE 
                (l.street LIKE ? OR l.street LIKE ?) 
                AND l.street != ''
        """
        
        # Add both capitalized and lowercase versions for better matching
        params = [pattern_with_wildcards, pattern_with_wildcards.lower()]
        
        if exclude_location_id:
            query += " AND l.id != ?"
            params.append(exclude_location_id)
        
        return execute_read(query, params)