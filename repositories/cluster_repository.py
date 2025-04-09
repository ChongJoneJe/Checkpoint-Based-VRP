from utils.database import execute_read, execute_write, execute_many
import json

class ClusterRepository:
    """Handles all database operations related to clusters"""
    
    @staticmethod
    def create(name, lat, lon):
        """Create a new cluster with name and centroid coordinates"""
        try:
            cluster_id = execute_write(
                """
                INSERT INTO clusters (name, centroid_lat, centroid_lon)
                VALUES (?, ?, ?)
                """,
                (name, lat, lon)
            )
            return cluster_id
        except Exception as e:
            print(f"Error creating cluster: {str(e)}")
            return None
    
    @staticmethod
    def add_location_to_cluster(location_id, cluster_id):
        """Add a location to a cluster"""
        # Check if already assigned
        existing = execute_read(
            "SELECT 1 FROM location_clusters WHERE location_id = ?",
            (location_id,),
            one=True
        )
        
        if existing:
            # Update existing assignment
            return execute_write(
                "UPDATE location_clusters SET cluster_id = ? WHERE location_id = ?",
                (cluster_id, location_id)
            )
        else:
            # Create new assignment
            return execute_write(
                "INSERT INTO location_clusters (location_id, cluster_id) VALUES (?, ?)",
                (location_id, cluster_id)
            )
    
    @staticmethod
    def update_checkpoint(cluster_id, checkpoint_lat, checkpoint_lon):
        """Update cluster checkpoint information"""
        return execute_write(
            """UPDATE clusters 
               SET checkpoint_lat = ?, checkpoint_lon = ? WHERE id = ?""",
            (checkpoint_lat, checkpoint_lon,  cluster_id)
        )
    
    @staticmethod
    def save_checkpoint(cluster_id, checkpoint_lat, checkpoint_lon, ransition_type=None):
        """Save security checkpoint information for a cluster"""
        return execute_write(
            """UPDATE clusters 
               SET checkpoint_lat = ?, checkpoint_lon = ?, 
                   road_transition_type = ?
               WHERE id = ?"""
            (checkpoint_lat, checkpoint_lon, cluster_id)
        )
    
    @staticmethod
    def get_cluster_locations(cluster_id):
        """Get all locations in a cluster"""
        return execute_read(
            """SELECT l.id, l.lat, l.lon, l.street, l.neighborhood, l.development, l.city
            FROM locations l
            JOIN location_clusters lc ON l.id = lc.location_id
            WHERE lc.cluster_id = ?""",
            (cluster_id,)
        )
    
    @staticmethod
    def get_clusters_for_preset(preset_id):
        """Get all clusters for a preset"""
        return execute_read(
            """SELECT DISTINCT c.id, c.name, c.centroid_lat, c.centroid_lon, 
                            c.checkpoint_lat, c.checkpoint_lon
               FROM clusters c
               JOIN location_clusters lc ON c.id = lc.cluster_id
               JOIN preset_locations pl ON lc.location_id = pl.location_id
               WHERE pl.preset_id = ?""",
            (preset_id,)
        )
    
    @staticmethod
    def get_cluster_checkpoint(cluster_id):
        """Get the security checkpoint for a cluster"""
        return execute_read(
            """SELECT id, cluster_id, lat, lon, from_road_type, to_road_type
               FROM security_checkpoints
               WHERE cluster_id = ?
               LIMIT 1""",
            (cluster_id,),
            one=True
        )

    @staticmethod
    def save_route_cache(cache_key, route_data):
        """Save a route to the cache"""
        return execute_write(
            """INSERT OR REPLACE INTO route_cache (cache_key, route_data, created_at)
               VALUES (?, ?, datetime('now'))""",
            (cache_key, json.dumps(route_data))
        )

    @staticmethod
    def get_cached_route(cache_key):
        """Get a cached route by key"""
        result = execute_read(
            """SELECT route_data FROM route_cache WHERE cache_key = ?""",
            (cache_key,),
            one=True
        )
        return json.loads(result['route_data']) if result else None
