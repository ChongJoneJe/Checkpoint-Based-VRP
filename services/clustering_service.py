from models import db
from models.location import Location
from models.cluster import Cluster
from models.preset import Preset, Warehouse
from algorithms.dbscan import GeoDBSCAN
from utils.database import execute_read
from services.preset_service import PresetService

class ClusteringService:
    @staticmethod
    def get_clusters(preset_id=None):
        """Get clusters for visualization"""
        if preset_id:
            try:
                # Use raw SQL to get preset data instead of SQLAlchemy
                preset_query = """
                    SELECT p.id, p.name, p.created_at
                    FROM presets p
                    WHERE p.id = ?
                """
                preset_row = execute_read(preset_query, (preset_id,), one=True)
                
                if not preset_row:
                    return [], None, {"total_locations": 0, "num_clusters": 0, "noise_points": 0}
                
                # Get warehouse
                warehouse_query = """
                    SELECT l.id, l.lat, l.lon, l.street, l.neighborhood, l.development, l.city
                    FROM locations l
                    JOIN preset_locations pl ON l.id = pl.location_id
                    WHERE pl.preset_id = ? AND pl.is_warehouse = 1
                """
                warehouse_row = execute_read(warehouse_query, (preset_id,), one=True)
                
                warehouse = None
                if warehouse_row:
                    warehouse = {
                        'id': warehouse_row['id'],
                        'lat': warehouse_row['lat'],
                        'lon': warehouse_row['lon'],
                        'street': warehouse_row['street'] or '',
                        'neighborhood': warehouse_row['neighborhood'] or '',
                        'development': warehouse_row['development'] or '',
                        'city': warehouse_row['city'] or ''
                    }
                
                # Keep existing destination query but only fetch locations
                destinations_query = """
                    SELECT l.id, l.lat, l.lon, l.street, l.neighborhood,
                           lc.cluster_id, c.name as cluster_name, 
                           c.centroid_lat, c.centroid_lon, l.development
                    FROM locations l
                    JOIN preset_locations pl ON l.id = pl.location_id
                    LEFT JOIN location_clusters lc ON l.id = lc.location_id
                    LEFT JOIN clusters c ON lc.cluster_id = c.id
                    WHERE pl.preset_id = ? AND pl.is_warehouse = 0
                """
                destination_rows = execute_read(destinations_query, (preset_id,))

                # Organize by actual clusters
                clusters = {}
                noise_points = []

                for row in destination_rows:
                    location = {
                        'id': row['id'],
                        'lat': row['lat'],
                        'lon': row['lon'],
                        'street': row['street'] or '',
                        'neighborhood': row['neighborhood'] or '',
                        'development': row['development'] or ''
                    }
                    
                    if row['cluster_id']:
                        cluster_id = row['cluster_id']
                        
                        # Initialize cluster if not seen before
                        if cluster_id not in clusters:
                            clusters[cluster_id] = {
                                'id': cluster_id,
                                'name': row['cluster_name'] or f"Cluster {cluster_id}",
                                'centroid': [row['centroid_lat'], row['centroid_lon']] if row['centroid_lat'] else [0, 0],
                                'locations': []
                            }
                        
                        # Add location to cluster
                        clusters[cluster_id]['locations'].append(location)
                    else:
                        # Add to noise points (no cluster)
                        noise_points.append(location)

                # If there are noise points, add them as a special "cluster"
                if noise_points:
                    clusters['noise'] = {
                        'id': 'noise',
                        'name': 'Unclustered Points',
                        'centroid': [0, 0],
                        'locations': noise_points
                    }
                
                # Add checkpoint data for each cluster
                for cluster_id, cluster_data in clusters.items():
                    if cluster_id == 'noise':
                        continue
                        
                    # Get security checkpoint for this cluster
                    checkpoint_query = """
                        SELECT id, lat, lon, from_road_type, to_road_type 
                        FROM security_checkpoints
                        WHERE cluster_id = ?
                        LIMIT 1
                    """
                    checkpoint = execute_read(checkpoint_query, (cluster_id,), one=True)
                    
                    if checkpoint:
                        cluster_data['checkpoint'] = {
                            'id': checkpoint['id'],
                            'lat': checkpoint['lat'],
                            'lon': checkpoint['lon'],
                            'from_road_type': checkpoint['from_road_type'] or 'unknown',
                            'to_road_type': checkpoint['to_road_type'] or 'unknown'
                        }
                
                stats = {
                    'total_locations': sum(len(c['locations']) for c in clusters.values()),
                    'num_clusters': len(clusters) - (1 if 'noise' in clusters else 0),
                    'noise_points': len(noise_points)
                }
                
                return list(clusters.values()), warehouse, stats
                
            except Exception as e:
                print(f"Error in get_clusters with preset_id: {str(e)}")
                return [], None, {"total_locations": 0, "num_clusters": 0, "noise_points": 0}
        else:
            # Original implementation for "All Locations" view
            query = """
                SELECT l.id, l.lat, l.lon, l.street, l.neighborhood, l.development, l.city,
                       c.id as cluster_id, c.name as cluster_name, 
                       c.centroid_lat, c.centroid_lon,
                       pl.is_warehouse
                FROM locations l
                LEFT JOIN location_clusters lc ON l.id = lc.location_id
                LEFT JOIN clusters c ON lc.cluster_id = c.id
                LEFT JOIN preset_locations pl ON l.id = pl.location_id
                WHERE (pl.is_warehouse IS NULL OR pl.is_warehouse = 0)
            """
            params = []
            
            # Execute query
            results = execute_read(query, params)
            
            # Organize results by cluster
            clusters = {}
            noise_points = []
            warehouse = None
            
            for row in results:
                # Check if this is a warehouse
                if row['is_warehouse'] == 1:
                    # Store the warehouse separately
                    warehouse = {
                        'id': row['id'],
                        'lat': row['lat'],
                        'lon': row['lon'],
                        'street': row['street'],
                        'neighborhood': row['neighborhood'],
                        'development': row['development'],
                        'city': row['city']
                    }
                    continue
                    
                # If location has a cluster
                if row['cluster_id']:
                    cluster_id = row['cluster_id']
                    
                    # Initialize cluster if not seen before
                    if cluster_id not in clusters:
                        clusters[cluster_id] = {
                            'id': cluster_id,
                            'name': row['cluster_name'],
                            'centroid': [row['centroid_lat'], row['centroid_lon']],
                            'locations': []
                        }
                    
                    # Add location to cluster
                    clusters[cluster_id]['locations'].append({
                        'id': row['id'],
                        'lat': row['lat'],
                        'lon': row['lon'],
                        'street': row['street'],
                        'neighborhood': row['neighborhood'],
                        'development': row['development']
                    })
                else:
                    # Add to noise points (no cluster)
                    noise_points.append({
                        'id': row['id'],
                        'lat': row['lat'],
                        'lon': row['lon'],
                        'street': row['street'],
                        'neighborhood': row['neighborhood'],
                        'development': row['development']
                    })
            
            # If there are noise points, add them as a special "cluster"
            if noise_points:
                clusters['noise'] = {
                    'id': 'noise',
                    'name': 'Noise Points',
                    'centroid': [0, 0],  # Placeholder
                    'locations': noise_points
                }
            
            # Add checkpoint data for each cluster
            for cluster_id, cluster_data in clusters.items():
                if cluster_id == 'noise':
                    continue
                    
                # Get security checkpoint for this cluster
                checkpoint_query = """
                    SELECT id, lat, lon, from_road_type, to_road_type 
                    FROM security_checkpoints
                    WHERE cluster_id = ?
                    LIMIT 1
                """
                checkpoint = execute_read(checkpoint_query, (cluster_id,), one=True)
                
                if checkpoint:
                    cluster_data['checkpoint'] = {
                        'id': checkpoint['id'],
                        'lat': checkpoint['lat'],
                        'lon': checkpoint['lon'],
                        'from_road_type': checkpoint['from_road_type'] or 'unknown',
                        'to_road_type': checkpoint['to_road_type'] or 'unknown'
                    }
            
            # Prepare stats
            total_locations = sum(len(c['locations']) for c in clusters.values())
            num_clusters = len(clusters) - (1 if 'noise' in clusters else 0)
            noise_count = len(noise_points)
            
            stats = {
                'total_locations': total_locations,
                'num_clusters': num_clusters,
                'noise_points': noise_count
            }
            
            return list(clusters.values()), warehouse, stats
    
    @staticmethod
    def run_clustering_for_preset(preset_id, eps=0.5, min_samples=2):
        """
        Run clustering on a preset's locations
        
        Args:
            preset_id: ID of the preset to cluster
            eps: DBSCAN epsilon parameter
            min_samples: DBSCAN min_samples parameter
            
        Returns:
            list: Clusters with their locations
        """
        # Get preset locations
        locations_query = """
            SELECT l.id, l.lat, l.lon, pl.is_warehouse
            FROM locations l
            JOIN preset_locations pl ON l.id = pl.location_id
            WHERE pl.preset_id = ?
        """
        
        locations = execute_read(locations_query, (preset_id,))
        
        if not locations:
            raise ValueError(f"No locations found for preset {preset_id}")
        
        # Separate warehouse and destinations
        warehouse = None
        destinations = []
        
        for loc in locations:
            if loc['is_warehouse']:
                warehouse = [loc['lat'], loc['lon']]
            else:
                destinations.append([loc['lat'], loc['lon']])
        
        if not warehouse or not destinations:
            raise ValueError("Preset must have both warehouse and destinations")
        
        # Initialize DBSCAN
        dbscan = GeoDBSCAN()
        
        # Run clustering
        result = dbscan.cluster_locations(
            warehouse_lat=warehouse[0],
            warehouse_lon=warehouse[1],
            destination_coords=destinations,
            eps=eps,
            min_samples=min_samples
        )
        
        return result

    @staticmethod
    def get_preset_with_geocoded_info(preset_id):
        """
        Get a preset with its geocoded location information for clustering
        
        Args:
            preset_id: ID of the preset
            
        Returns:
            dict: Preset with detailed location information
        """
        preset = Preset.query.get(preset_id)
        if not preset:
            return None
            
        # Get warehouse with geocoded info
        warehouse_data = None
        warehouse = Warehouse.query.filter_by(preset_id=preset_id).first()
        if warehouse:
            wh_location = Location.query.get(warehouse.location_id)
            if wh_location:
                warehouse_data = {
                    'id': wh_location.id,
                    'lat': wh_location.lat,
                    'lon': wh_location.lon,
                    'street': wh_location.street,
                    'neighborhood': wh_location.neighborhood,
                    'development': wh_location.development,
                    'city': wh_location.city
                }
        
        # Get destinations with geocoded info
        destinations = []
        locations = db.session.query(Location).\
            join(db.Table('preset_locations')).\
            filter(db.Table('preset_locations').c.preset_id == preset_id).\
            filter(db.Table('preset_locations').c.is_warehouse == False).all()
            
        for loc in locations:
            destinations.append({
                'id': loc.id,
                'lat': loc.lat,
                'lon': loc.lon,
                'street': loc.street,
                'neighborhood': loc.neighborhood,
                'development': loc.development,
                'city': loc.city
            })
        
        return {
            'id': preset.id,
            'name': preset.name,
            'warehouse': warehouse_data,
            'destinations': destinations,
            'created_at': preset.created_at.isoformat() if preset.created_at else None
        }