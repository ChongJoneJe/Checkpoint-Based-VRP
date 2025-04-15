import os
import sqlite3
import math
import numpy as np
from sklearn.cluster import DBSCAN
from flask import current_app
from utils.database import execute_read, execute_write

class CheckpointService:
    """Service for managing security checkpoints"""

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

    @staticmethod
    def get_all_checkpoints():
        """
        Get all security checkpoints from the database
        
        Returns:
            list: List of checkpoint dictionaries with lat, lon and other data
        """
        try:
            db_path = os.path.join(current_app.root_path, 'static', 'data', 'locations.db')
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get all checkpoints with the correct schema columns
            cursor.execute("""
                SELECT id, lat, lon, cluster_id, from_road_type, to_road_type, confidence
                FROM security_checkpoints
                ORDER BY id
            """)
            
            checkpoints = []
            for row in cursor.fetchall():
                checkpoints.append({
                    'id': row['id'],
                    'lat': float(row['lat']),
                    'lon': float(row['lon']),
                    'cluster_id': row['cluster_id'],
                    'from_road_type': row['from_road_type'],
                    'to_road_type': row['to_road_type'],
                    'confidence': row['confidence']
                })
            
            conn.close()
            return checkpoints
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error fetching checkpoints: {str(e)}")
            return []

    @staticmethod
    def get_checkpoint_by_id(checkpoint_id):
        """
        Get a specific checkpoint by ID
        
        Args:
            checkpoint_id: ID of the checkpoint
            
        Returns:
            dict: Checkpoint data or None if not found
        """
        try:
            db_path = os.path.join(current_app.root_path, 'static', 'data', 'locations.db')
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get specific checkpoint with correct schema
            cursor.execute("""
                SELECT id, lat, lon, cluster_id, from_road_type, to_road_type, confidence
                FROM security_checkpoints
                WHERE id = ?
            """, (checkpoint_id,))
            
            row = cursor.fetchone()
            
            if not row:
                return None
                
            checkpoint = {
                'id': row['id'],
                'lat': float(row['lat']),
                'lon': float(row['lon']),
                'cluster_id': row['cluster_id'],
                'from_road_type': row['from_road_type'],
                'to_road_type': row['to_road_type'],
                'confidence': row['confidence']
            }
            
            conn.close()
            return checkpoint
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error fetching checkpoint: {str(e)}")
            return None
    
    @staticmethod
    def get_checkpoints_by_cluster(cluster_id):
        """
        Get checkpoints for a specific cluster
        
        Args:
            cluster_id: ID of the cluster
            
        Returns:
            list: List of checkpoint dictionaries for the cluster
        """
        try:
            db_path = os.path.join(current_app.root_path, 'static', 'data', 'locations.db')
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get checkpoints for cluster with correct schema
            cursor.execute("""
                SELECT id, lat, lon, cluster_id, from_road_type, to_road_type, confidence
                FROM security_checkpoints
                WHERE cluster_id = ?
                ORDER BY id
            """, (cluster_id,))
            
            checkpoints = []
            for row in cursor.fetchall():
                checkpoints.append({
                    'id': row['id'],
                    'lat': float(row['lat']),
                    'lon': float(row['lon']),
                    'cluster_id': row['cluster_id'],
                    'from_road_type': row['from_road_type'],
                    'to_road_type': row['to_road_type'],
                    'confidence': row['confidence']
                })
            
            conn.close()
            return checkpoints
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error fetching checkpoints for cluster: {str(e)}")
            return []

    @staticmethod
    def create_checkpoint(lat, lon, cluster_id, from_road_type=None, to_road_type=None, confidence=0.7):
        """
        Create a new security checkpoint
        
        Args:
            lat: Latitude
            lon: Longitude
            cluster_id: Associated cluster ID
            from_road_type: Type of road the checkpoint is coming from (optional)
            to_road_type: Type of road the checkpoint is going to (optional)
            confidence: Confidence score for this checkpoint (optional)
            
        Returns:
            int: ID of the newly created checkpoint or None on failure
        """
        try:
            db_path = os.path.join(current_app.root_path, 'static', 'data', 'locations.db')
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO security_checkpoints (lat, lon, cluster_id, from_road_type, to_road_type, confidence)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (lat, lon, cluster_id, from_road_type, to_road_type, confidence))
            
            checkpoint_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return checkpoint_id
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error creating checkpoint: {str(e)}")
            return None
    
    @staticmethod
    def get_checkpoints_for_snapshot(snapshot_path):
        """
        Get checkpoints from a database snapshot file
        
        Args:
            snapshot_path: Path to the database snapshot file
            
        Returns:
            list: List of checkpoint dictionaries
        """
        try:
            if not os.path.exists(snapshot_path):
                return []
                
            conn = sqlite3.connect(snapshot_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Check if the security_checkpoints table exists in this snapshot
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='security_checkpoints'
            """)
            
            if not cursor.fetchone():
                conn.close()
                return []
                
            # Get all checkpoints with the correct schema
            try:
                cursor.execute("""
                    SELECT id, lat, lon, cluster_id, from_road_type, to_road_type, confidence
                    FROM security_checkpoints
                    ORDER BY id
                """)
            except sqlite3.OperationalError:
                # If the schema doesn't match, try a more basic query
                cursor.execute("""
                    SELECT id, lat, lon, cluster_id
                    FROM security_checkpoints
                    ORDER BY id
                """)
            
            checkpoints = []
            for row in cursor.fetchall():
                checkpoint = {
                    'id': row['id'],
                    'lat': float(row['lat']),
                    'lon': float(row['lon']),
                    'cluster_id': row['cluster_id']
                }
                
                # Add optional fields if they exist
                for field in ['from_road_type', 'to_road_type', 'confidence']:
                    if field in row.keys():
                        checkpoint[field] = row[field]
                
                checkpoints.append(checkpoint)
            
            conn.close()
            return checkpoints
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error fetching checkpoints from snapshot: {str(e)}")
            return []
        
    @staticmethod
    def get_all_multi_checkpoints():
        """Get all checkpoints with cluster grouping"""
        try:
            conn = sqlite3.connect(os.path.join(current_app.root_path, 'static', 'data', 'locations.db'))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            checkpoints = []
            cursor.execute("""
                SELECT sc.id, sc.cluster_id, sc.lat, sc.lon, sc.from_road_type,
                    sc.to_road_type, sc.confidence, c.name as cluster_name
                FROM security_checkpoints sc
                JOIN clusters c ON sc.cluster_id = c.id
                ORDER BY sc.cluster_id, sc.id
            """)
            
            for row in cursor:
                checkpoint = dict(row)
                checkpoints.append(checkpoint)
            
            conn.close()
            return checkpoints
        except Exception as e:
            print(f"Error fetching multi-checkpoints: {str(e)}")
            return []

    @staticmethod
    def get_multi_checkpoints_for_snapshot(snapshot_path):
        """Get all checkpoints from a snapshot database"""
        try:
            conn = sqlite3.connect(snapshot_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            checkpoints = []
            cursor.execute("""
                SELECT sc.id, sc.cluster_id, sc.lat, sc.lon, sc.from_road_type,
                    sc.to_road_type, sc.confidence, c.name as cluster_name
                FROM security_checkpoints sc
                JOIN clusters c ON sc.cluster_id = c.id
                ORDER BY sc.cluster_id, sc.id
            """)
            
            for row in cursor:
                checkpoint = dict(row)
                checkpoints.append(checkpoint)
            
            conn.close()
            return checkpoints
        except Exception as e:
            print(f"Error fetching multi-checkpoints from snapshot: {str(e)}")
            return []

    @staticmethod
    def get_cluster_for_location(location, snapshot_path=None):
        """
        Maps a location to a cluster based on closest cluster centroid
        
        Args:
            location (list): [lat, lon] of the new location
            snapshot_path (str): Path to the snapshot database
            
        Returns:
            int: cluster_id of closest cluster or None if no clusters found
        """
        try:
            conn = sqlite3.connect(snapshot_path)
            conn.row_factory = sqlite3.Row
            
            # Get all clusters with their centroids
            clusters_query = """
                SELECT c.id, c.name, AVG(l.lat) as avg_lat, AVG(l.lon) as avg_lon, COUNT(l.id) as location_count
                FROM clusters c
                JOIN location_clusters lc ON c.id = lc.cluster_id
                JOIN locations l ON lc.location_id = l.id
                GROUP BY c.id
                HAVING location_count > 0
            """
            
            clusters = []
            for row in conn.execute(clusters_query):
                clusters.append({
                    'id': row['id'],
                    'name': row['name'],
                    'lat': row['avg_lat'],
                    'lon': row['avg_lon']
                })
            
            conn.close()
            
            if not clusters:
                print("No clusters found in database")
                return None
            
            # Find closest cluster using Haversine distance
            closest_cluster = None
            min_distance = float('inf')
            
            for cluster in clusters:
                distance = CheckpointService._haversine_distance(
                    location[0], location[1],
                    cluster['lat'], cluster['lon']
                )
                
                if distance < min_distance:
                    min_distance = distance
                    closest_cluster = cluster
            
            return closest_cluster['id'] if closest_cluster else None
            
        except Exception as e:
            print(f"Error finding cluster for location: {e}")
            return None

    @staticmethod
    def consolidate_checkpoints(checkpoints, eps=50, min_samples=1):
        """
        Identify and consolidate checkpoints that are physically close
        despite belonging to different clusters.
        
        Args:
            checkpoints: List of checkpoint dictionaries with lat/lon
            eps: Maximum distance (in meters) to consider checkpoints as shared
            min_samples: Min points to form a cluster in DBSCAN
            
        Returns:
            Dict with consolidated checkpoints, mapping, and grouping
        """
        if not checkpoints:
            return {
                'consolidated_checkpoints': [],
                'original_to_consolidated': {},
                'consolidated_groups': []
            }
        
        # Extract coordinates for clustering
        coords = np.array([[cp['lat'], cp['lon']] for cp in checkpoints])
        checkpoint_ids = [cp['id'] for cp in checkpoints]
        
        # Convert eps from meters to approximate degrees (rough estimate)
        # 111,111 meters = 1 degree latitude
        eps_degrees = eps / 111111
        
        # Apply DBSCAN clustering
        clustering = DBSCAN(eps=eps_degrees, min_samples=min_samples, algorithm='ball_tree', 
                          metric='haversine').fit(np.radians(coords))
        
        # Get cluster labels (-1 means noise/outlier)
        labels = clustering.labels_
        
        # Create consolidated checkpoints
        consolidated_checkpoints = []
        consolidated_groups = []
        original_to_consolidated = {}
        
        # Process each spatial cluster
        unique_labels = set(labels)
        for label in unique_labels:
            if label == -1:  # Handle outliers
                # Each outlier becomes its own consolidated checkpoint
                for i, orig_id in enumerate(checkpoint_ids):
                    if labels[i] == -1:
                        cp = checkpoints[i]
                        consolidated_id = len(consolidated_checkpoints) + 1
                        consolidated_checkpoints.append({
                            'id': consolidated_id,
                            'lat': cp['lat'],
                            'lon': cp['lon'],
                            'original_ids': [orig_id],
                            'cluster_ids': [cp['cluster_id']]
                        })
                        original_to_consolidated[orig_id] = consolidated_id
            else:
                # Group checkpoints in this spatial cluster
                indices = np.where(labels == label)[0]
                original_ids = [checkpoint_ids[i] for i in indices]
                cluster_ids = [checkpoints[i]['cluster_id'] for i in indices]
                
                # Calculate centroid (average position)
                centroid_lat = np.mean([checkpoints[i]['lat'] for i in indices])
                centroid_lon = np.mean([checkpoints[i]['lon'] for i in indices])
                
                # Create consolidated checkpoint
                consolidated_id = len(consolidated_checkpoints) + 1
                consolidated_checkpoints.append({
                    'id': consolidated_id,
                    'lat': float(centroid_lat),
                    'lon': float(centroid_lon),
                    'original_ids': original_ids,
                    'cluster_ids': list(set(cluster_ids))  # Unique cluster IDs
                })
                
                # Record grouping information
                consolidated_groups.append({
                    'consolidated_id': consolidated_id,
                    'original_ids': original_ids,
                    'cluster_ids': list(set(cluster_ids)),
                    'checkpoint_count': len(original_ids)
                })
                
                # Update mapping from original to consolidated
                for orig_id in original_ids:
                    original_to_consolidated[orig_id] = consolidated_id
        
        return {
            'consolidated_checkpoints': consolidated_checkpoints,
            'original_to_consolidated': original_to_consolidated,
            'consolidated_groups': consolidated_groups
        }

    @staticmethod
    def aggregate_demand_by_checkpoint(locations, checkpoints, consolidated_mapping):
        """
        Aggregate delivery/pickup demand by consolidated checkpoint
        
        Args:
            locations: List of location dicts with cluster_id and demand info
            checkpoints: List of checkpoint dicts
            consolidated_mapping: Dict mapping original checkpoint IDs to consolidated IDs
            
        Returns:
            Dict mapping consolidated checkpoint ID to aggregated demand
        """
        # Create mapping from cluster_id to consolidated_checkpoint_id
        cluster_to_consolidated = {}
        
        for cp in checkpoints:
            cluster_id = cp['cluster_id']
            original_id = cp['id']
            consolidated_id = consolidated_mapping.get(original_id)
            
            if consolidated_id and cluster_id not in cluster_to_consolidated:
                cluster_to_consolidated[cluster_id] = consolidated_id
        
        # Initialize demand for each consolidated checkpoint
        demand = {}
        
        # Process each location
        for loc in locations:
            cluster_id = loc.get('cluster_id')
            if not cluster_id:
                continue
                
            consolidated_id = cluster_to_consolidated.get(cluster_id)
            if not consolidated_id:
                continue
                
            if consolidated_id not in demand:
                demand[consolidated_id] = {
                    'delivery_count': 0,
                    'pickup_count': 0,
                    'locations': []
                }
            
            # Increment appropriate demand counter
            loc_type = loc.get('type', 'delivery')
            if loc_type.lower() == 'pickup':
                demand[consolidated_id]['pickup_count'] += 1
            else:
                demand[consolidated_id]['delivery_count'] += 1
                
            # Add location to list
            demand[consolidated_id]['locations'].append(loc['id'])
        
        return demand

    @staticmethod
    def get_distance_matrix(warehouse, consolidated_checkpoints, use_cache=True):
        """
        Calculate distance/time matrix between warehouse and consolidated checkpoints
        
        Args:
            warehouse: [lat, lon] of warehouse
            consolidated_checkpoints: List of dicts with consolidated checkpoint data
            use_cache: Whether to check cache before calculating
            
        Returns:
            NxN numpy array with distances between all nodes (warehouse + checkpoints)
        """
        # Import here to avoid circular imports
        from services.cache_service import CacheService
        import hashlib
        import json
        
        # Create nodes list (warehouse first, then checkpoints)
        nodes = [warehouse]
        for cp in consolidated_checkpoints:
            nodes.append([cp['lat'], cp['lon']])
        
        if not nodes:
            return np.zeros((1, 1))
        
        # Generate cache key
        cache_key = hashlib.md5(json.dumps(nodes, sort_keys=True).encode()).hexdigest()
        
        # Check cache if enabled
        if use_cache:
            cached_matrix = CacheService.get_cached_matrix(cache_key)
            if cached_matrix is not None:
                return cached_matrix
        
        # If not in cache, calculate matrix
        n = len(nodes)
        matrix = np.zeros((n, n))
        
        # Get API key
        import os
        api_key = os.environ.get('ORS_API_KEY')
        
        if api_key:
            # Use OpenRouteService API if available
            try:
                import openrouteservice as ors
                client = ors.Client(key=api_key)
                
                # ORS expects [lon, lat] format, so we need to swap
                ors_coords = [[node[1], node[0]] for node in nodes]
                
                # Calculate full matrix (in chunks if needed due to API limits)
                chunk_size = 50  # Adjust based on API limits
                
                for i in range(0, n, chunk_size):
                    i_end = min(i + chunk_size, n)
                    
                    for j in range(0, n, chunk_size):
                        j_end = min(j + chunk_size, n)
                        
                        # Get source and destination subsets
                        sources = list(range(i, i_end))
                        destinations = list(range(j, j_end))
                        
                        # Skip if same point
                        if i == j and len(sources) == 1:
                            continue
                        
                        # Call API
                        response = client.distance_matrix(
                            locations=ors_coords,
                            sources=sources,
                            destinations=destinations,
                            metrics=['distance'],
                            units='km'
                        )
                        
                        # Fill matrix with results
                        for src_idx, src in enumerate(sources):
                            for dest_idx, dest in enumerate(destinations):
                                matrix[src, dest] = response['distances'][src_idx][dest_idx]
                                
            except Exception as e:
                print(f"Error using OpenRouteService API: {str(e)}")
                # Fall back to Haversine distance if API fails
                for i in range(n):
                    for j in range(n):
                        if i != j:
                            matrix[i, j] = CheckpointService._haversine_distance(
                                nodes[i][0], nodes[i][1],
                                nodes[j][0], nodes[j][1]
                            )
        else:
            # Use Haversine distance if no API key
            for i in range(n):
                for j in range(n):
                    if i != j:
                        matrix[i, j] = CheckpointService._haversine_distance(
                            nodes[i][0], nodes[i][1],
                            nodes[j][0], nodes[j][1]
                        )
        
        # Cache the result
        if use_cache:
            CacheService.cache_matrix(cache_key, matrix)
        
        return matrix

    @staticmethod
    def _haversine_distance(lat1, lon1, lat2, lon2):
        """Calculate the Haversine distance between two points in kilometers"""
        R = 6371  # Earth radius in km
        
        # Convert to radians
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        return R * c  # Distance in kilometers