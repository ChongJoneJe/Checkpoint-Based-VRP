import sys
import os
import osmnx as ox
from shapely.geometry import Point
from shapely.ops import unary_union
from utils.database import execute_read

class DebugService:
    @staticmethod
    def debug_checkpoint(cluster_id, geocoder):
        """
        Debug function for testing checkpoint generation
        """
        # Get cluster info
        cluster = execute_read(
            "SELECT id, name, centroid_lat, centroid_lon FROM clusters WHERE id = ?",
            (cluster_id,),
            one=True
        )
        
        if not cluster:
            raise ValueError("Cluster not found")
        
        # Get locations in this cluster
        locations = execute_read(
            """SELECT l.id, l.lat, l.lon, l.street 
            FROM locations l
            JOIN location_clusters lc ON l.id = lc.location_id
            WHERE lc.cluster_id = ?""",
            (cluster_id,)
        )
        
        # Simple diagnostic information
        diagnostic = {
            "cluster_id": cluster_id,
            "cluster_name": cluster["name"],
            "locations_count": len(locations),
            "network_analyzer_initialized": geocoder.network_analyzer is not None,
            "osmnx_version": ox.__version__,
            "matplotlib_available": "matplotlib.pyplot" in sys.modules
        }
        
        # Simulate the start of checkpoint identification
        location_coords = [(loc['lat'], loc['lon']) for loc in locations]
        cluster_center = (cluster['centroid_lat'], cluster['centroid_lon'])
        
        # Check if we can create a test polygon
        try:
            if len(location_coords) < 3:
                polygon = Point(cluster['centroid_lon'], cluster['centroid_lat']).buffer(0.002)
            else:
                points = [Point(lon, lat) for lat, lon in location_coords]
                polygon = unary_union(points).convex_hull
            
            diagnostic["polygon_created"] = True
            diagnostic["polygon_area"] = polygon.area
        except Exception as e:
            diagnostic["polygon_created"] = False
            diagnostic["polygon_error"] = str(e)
        
        # Try to download a small test network
        try:
            buffer_radius = 300
            test_network = ox.graph_from_point(
                (cluster['centroid_lat'], cluster['centroid_lon']), 
                dist=buffer_radius, 
                network_type='drive'
            )
            diagnostic["network_download"] = True
            diagnostic["network_nodes"] = len(test_network.nodes)
            diagnostic["network_edges"] = len(test_network.edges)
        except Exception as e:
            diagnostic["network_download"] = False
            diagnostic["network_error"] = str(e)
            
        return {
            "diagnostic": diagnostic,
            "cluster": cluster,
            "locations": [
                {"id": loc["id"], "lat": loc["lat"], "lon": loc["lon"], "street": loc["street"]}
                for loc in locations[:5]  # Just first 5 for brevity
            ]
        }