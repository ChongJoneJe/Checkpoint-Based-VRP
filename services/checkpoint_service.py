import os
from utils.database import execute_read, execute_write

class CheckpointService:
    @staticmethod
    def get_checkpoints(cluster_id):
        """Get checkpoints for a cluster"""
        # Get cluster info
        cluster = execute_read(
            "SELECT id, name, centroid_lat, centroid_lon FROM clusters WHERE id = ?",
            (cluster_id,),
            one=True
        )
        
        if not cluster:
            raise ValueError("Cluster not found")
        
        # Get existing checkpoints and convert to dict
        checkpoints = execute_read(
            """SELECT id, lat, lon, from_road_type, to_road_type, confidence
            FROM security_checkpoints
            WHERE cluster_id = ?""",
            (cluster_id,)
        )
        
        # Convert Row objects to regular dictionaries
        checkpoints_dict = []
        for cp in checkpoints:
            checkpoints_dict.append({
                'id': cp['id'],
                'lat': cp['lat'],
                'lon': cp['lon'], 
                'from_type': cp['from_road_type'],
                'to_type': cp['to_road_type'],
                'confidence': cp['confidence']
            })
        
        cluster_dict = {
            'id': cluster['id'],
            'name': cluster['name'],
            'centroid_lat': cluster['centroid_lat'],
            'centroid_lon': cluster['centroid_lon']
        }
        
        return {
            "cluster": cluster_dict,
            "checkpoints": checkpoints_dict
        }
    
    @staticmethod
    def generate_checkpoints(cluster_id, geocoder):
        """Generate checkpoints for a cluster"""
        if not geocoder:
            raise ValueError("Geocoder not available")
            
        access_points = geocoder.identify_cluster_access_points(cluster_id)
        
        return {
            "checkpoints": access_points,
            "count": len(access_points)
        }
        
    @staticmethod
    def delete_checkpoint(checkpoint_id):
        """Delete a checkpoint"""
        # Check if checkpoint exists
        checkpoint = execute_read(
            "SELECT id FROM security_checkpoints WHERE id = ?",
            (checkpoint_id,),
            one=True
        )
        
        if not checkpoint:
            raise ValueError("Checkpoint not found")
        
        # Delete the checkpoint
        execute_write(
            "DELETE FROM security_checkpoints WHERE id = ?",
            (checkpoint_id,)
        )
        
        return True
        
    @staticmethod
    def check_visualization(cluster_id, app_root_path):
        """Check if network visualization is available"""
        viz_path = f"/static/images/clusters/cluster_{cluster_id}_network.png"
        full_path = os.path.join(app_root_path, viz_path[1:])
        
        return {
            "has_visualization": os.path.exists(full_path),
            "image_path": viz_path if os.path.exists(full_path) else None
        }