from utils.database import execute_read, execute_write, execute_many

class ClusterRepository:
    """Handles all database operations related to clusters"""
    
    @staticmethod
    def create(name, centroid_lat, centroid_lon):
        """Create a new cluster"""
        return execute_write(
            "INSERT INTO clusters (name, centroid_lat, centroid_lon) VALUES (?, ?, ?)",
            (name, centroid_lat, centroid_lon)
        )
    
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
    def update_checkpoint(cluster_id, checkpoint_lat, checkpoint_lon, description=None):
        """Update cluster checkpoint information"""
        return execute_write(
            """UPDATE clusters 
               SET checkpoint_lat = ?, checkpoint_lon = ?, checkpoint_description = ?
               WHERE id = ?""",
            (checkpoint_lat, checkpoint_lon, description, cluster_id)
        )
    
    @staticmethod
    def save_checkpoint(cluster_id, checkpoint_lat, checkpoint_lon, description=None, transition_type=None):
        """Save security checkpoint information for a cluster"""
        return execute_write(
            """UPDATE clusters 
               SET checkpoint_lat = ?, checkpoint_lon = ?, 
                   checkpoint_description = ?, road_transition_type = ?
               WHERE id = ?""",
            (checkpoint_lat, checkpoint_lon, description, transition_type, cluster_id)
        )
    
    @staticmethod
    def get_cluster_locations(cluster_id):
        """Get all locations in a cluster"""
        return execute_read(
            """SELECT l.id, l.lat, l.lon, l.street, l.neighborhood, l.town, l.city
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
                            c.checkpoint_lat, c.checkpoint_lon, c.checkpoint_description
               FROM clusters c
               JOIN location_clusters lc ON c.id = lc.cluster_id
               JOIN preset_locations pl ON lc.location_id = pl.location_id
               WHERE pl.preset_id = ?""",
            (preset_id,)
        )
