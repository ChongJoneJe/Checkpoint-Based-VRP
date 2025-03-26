from models import db
from models.location import Location
from models.cluster import Cluster
from models.preset import Preset, Warehouse
from algorithms.dbscan import GeoDBSCAN
from utils.database import execute_read

class ClusteringService:
    @staticmethod
    def get_clusters(preset_id=None):
        """
        Get clusters for visualization
        
        Args:
            preset_id: Optional preset ID to filter clusters
            
        Returns:
            tuple: (clusters, warehouse, stats)
        """
        # Base query for locations, excluding warehouses from general results
        query = """
            SELECT l.id, l.lat, l.lon, l.street, l.neighborhood, l.town, l.city,
                   c.id as cluster_id, c.name as cluster_name, 
                   c.centroid_lat, c.centroid_lon,
                   pl.is_warehouse
            FROM locations l
            LEFT JOIN location_clusters lc ON l.id = lc.location_id
            LEFT JOIN clusters c ON lc.cluster_id = c.id
            LEFT JOIN preset_locations pl ON l.id = pl.location_id
        """
        
        # Add preset filter if specified
        params = []
        if preset_id:
            query += " WHERE pl.preset_id = ? "
            params.append(preset_id)
        else:
            # For all locations, exclude warehouses from regular clusters
            query += " WHERE (pl.is_warehouse IS NULL OR pl.is_warehouse = 0) "
        
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
                    'town': row['town'],
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
                    'neighborhood': row['neighborhood']
                })
            else:
                # Add to noise points (no cluster)
                noise_points.append({
                    'id': row['id'],
                    'lat': row['lat'],
                    'lon': row['lon'],
                    'street': row['street'],
                    'neighborhood': row['neighborhood']
                })
        
        # If there are noise points, add them as a special "cluster"
        if noise_points:
            clusters['noise'] = {
                'id': 'noise',
                'name': 'Noise Points',
                'centroid': [0, 0],  # Placeholder
                'locations': noise_points
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
        
        # Get warehouse if preset_id is specified but we didn't find one
        if preset_id and not warehouse:
            warehouse_query = """
                SELECT l.id, l.lat, l.lon, l.street, l.neighborhood, l.town, l.city
                FROM locations l
                JOIN preset_locations pl ON l.id = pl.location_id
                WHERE pl.preset_id = ? AND pl.is_warehouse = 1
            """
            warehouse_result = execute_read(warehouse_query, (preset_id,), one=True)
            if warehouse_result:
                warehouse = {
                    'id': warehouse_result['id'],
                    'lat': warehouse_result['lat'],
                    'lon': warehouse_result['lon'],
                    'street': warehouse_result['street'],
                    'neighborhood': warehouse_result['neighborhood'],
                    'town': warehouse_result['town'],
                    'city': warehouse_result['city']
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
                    'town': wh_location.town,
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
                'town': loc.town,
                'city': loc.city
            })
        
        return {
            'id': preset.id,
            'name': preset.name,
            'warehouse': warehouse_data,
            'destinations': destinations,
            'created_at': preset.created_at.isoformat() if preset.created_at else None
        }