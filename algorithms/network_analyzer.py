import osmnx as ox
import networkx as nx
from shapely.geometry import Point, Polygon, LineString
import os
import pickle
import time
import requests
import json

class NetworkAnalyzer:
    """Analyzes road networks to find topological bottlenecks and barriers"""
    
    def __init__(self, cache_dir="cache/networks"):
        self.cache_dir = cache_dir
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
    
    def get_network(self, center_lat, center_lon, radius=300):
        """Get road network around a point with caching"""
        cache_file = os.path.join(
            self.cache_dir, 
            f"network_{center_lat:.6f}_{center_lon:.6f}_{radius}.pkl"
        )
        
        # Try to load from cache first
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'rb') as f:
                    print(f"DEBUG: Loading network from cache: {cache_file}")
                    return pickle.load(f)
            except Exception as e:
                print(f"DEBUG: Error loading cached network: {e}")
        
        # Download if not cached
        try:
            print(f"DEBUG: Downloading network for {center_lat}, {center_lon}, radius {radius}m")
            G = ox.graph_from_point(
                (center_lat, center_lon), 
                dist=radius, 
                network_type='drive',
                simplify=True
            )
            
            # Add edge bearings
            G = ox.add_edge_bearings(G)
            
            # Cache the result
            with open(cache_file, 'wb') as f:
                pickle.dump(G, f)
                
            return G
        except Exception as e:
            print(f"DEBUG: Error downloading network: {e}")
            return None
    
    def get_barriers(self, center_lat, center_lon, radius=300):
        """Get barrier data from OSM using Overpass API"""
        try:
            overpass_url = "http://overpass-api.de/api/interpreter"
            overpass_query = f"""
            [out:json];
            (
              node["barrier"](around:{radius},{center_lat},{center_lon});
              way["barrier"](around:{radius},{center_lat},{center_lon});
              node["highway"="traffic_signals"](around:{radius},{center_lat},{center_lon});
              node["highway"="stop"](around:{radius},{center_lat},{center_lon});
              node["highway"="checkpoint"](around:{radius},{center_lat},{center_lon});
              node["barrier"="toll_booth"](around:{radius},{center_lat},{center_lon});
              node["barrier"="gate"](around:{radius},{center_lat},{center_lon});
              node["barrier"="lift_gate"](around:{radius},{center_lat},{center_lon});
              node["barrier"="checkpoint"](around:{radius},{center_lat},{center_lon});
            );
            out body;
            >;
            out skel qt;
            """
            
            response = requests.get(overpass_url, params={'data': overpass_query})
            data = response.json()
            
            # Extract barrier elements
            barriers = []
            for element in data.get('elements', []):
                if element.get('type') == 'node':
                    lat = element.get('lat')
                    lon = element.get('lon')
                    tags = element.get('tags', {})
                    
                    # Only keep relevant tags
                    barrier_type = tags.get('barrier') or tags.get('highway')
                    if barrier_type:
                        barriers.append({
                            'lat': lat,
                            'lon': lon,
                            'type': barrier_type,
                            'tags': tags
                        })
            
            return barriers
        except Exception as e:
            print(f"DEBUG: Error fetching barriers: {e}")
            return []
    
    def create_alpha_shape(self, points, alpha):
        """Create an alpha shape (concave hull) from a list of points"""
        from scipy.spatial import Delaunay
        from shapely.ops import polygonize
        
        if len(points) < 4:
            # Not enough points for Delaunay triangulation
            # Fall back to buffer around points
            multi_point = Point([p for p in points])
            return multi_point.buffer(alpha)
        
        def add_edge(edges, edge_points, coords, i, j):
            """Add a line between the i-th and j-th points"""
            i, j = sorted([i, j])  # Ensure i < j
            if (i, j) in edges:
                # Already added
                return
            edges.add((i, j))
            edge_points.append(LineString([coords[i], coords[j]]))

        coords = [(p[0], p[1]) for p in points]
        tri = Delaunay(coords)
        edges = set()
        edge_points = []
        
        # Loop over triangles
        for ia, ib, ic in tri.vertices:
            pa = coords[ia]
            pb = coords[ib]
            pc = coords[ic]
            
            # Calculate lengths of sides of triangle
            a = ((pa[0] - pb[0])**2 + (pa[1] - pb[1])**2)**0.5
            b = ((pb[0] - pc[0])**2 + (pb[1] - pc[1])**2)**0.5
            c = ((pc[0] - pa[0])**2 + (pc[1] - pa[1])**2)**0.5
            
            # Calculate semi-perimeter
            s = (a + b + c) / 2.0
            
            # Calculate area using Heron's formula
            area = (s * (s - a) * (s - b) * (s - c))**0.5
            
            # Calculate the circumcircle radius
            circum_radius = a * b * c / (4.0 * area) if area > 0 else float('inf')
            
            # If radius is less than alpha, add all edges of triangle
            if circum_radius < alpha:
                add_edge(edges, edge_points, coords, ia, ib)
                add_edge(edges, edge_points, coords, ib, ic)
                add_edge(edges, edge_points, coords, ic, ia)
        
        # Create shape from the remaining edges
        try:
            return list(polygonize(edge_points))[0]
        except (IndexError, ValueError):
            # Polygonization failed, fall back to convex hull
            from shapely.geometry import MultiPoint
            return MultiPoint(coords).convex_hull
    
    def find_cluster_access_points(self, cluster_locations, cluster_center, radius=300):
        """
        Find access points for a cluster based on network topology and OSM barriers
        
        Args:
            cluster_locations: List of (lat, lon) tuples for locations in cluster
            cluster_center: (lat, lon) tuple for cluster center
            radius: Search radius in meters
            
        Returns:
            List of dicts with access point information
        """
        print(f"DEBUG: Finding access points for cluster at {cluster_center}")
        center_lat, center_lon = cluster_center
        
        # Step 1: Get the road network
        G = self.get_network(center_lat, center_lon, radius)
        
        # Step 2: Get barrier data from OSM
        barriers = self.get_barriers(center_lat, center_lon, radius)
        print(f"DEBUG: Found {len(barriers)} barrier elements")
        
        # Track the access points we find
        access_points = []
        
        # Step 3: Create a polygon representing the cluster area
        cluster_poly = None
        if len(cluster_locations) >= 3:
            try:
                # Use alpha shape for more accurate boundary
                cluster_poly = self.create_alpha_shape(cluster_locations, 0.001)
            except Exception as e:
                print(f"DEBUG: Error creating alpha shape: {e}")
                cluster_poly = None
        
        if not cluster_poly or not cluster_poly.is_valid:
            # Fall back to buffer around the center
            cluster_poly = Point(cluster_center).buffer(0.001)  # ~100m buffer
        
        # Step 4: If we have a valid network, find topological bottlenecks
        if G and cluster_poly:
            print("DEBUG: Analyzing network topology for bottlenecks")
            try:
                # Extract node positions
                node_positions = {}
                for node, data in G.nodes(data=True):
                    node_positions[node] = (data['y'], data['x'])
                
                # Track nodes inside the cluster
                inside_nodes = []
                for node, pos in node_positions.items():
                    if Point(pos).within(cluster_poly):
                        inside_nodes.append(node)
                
                print(f"DEBUG: Found {len(inside_nodes)} nodes inside cluster")
                
                # Find edges that cross the cluster boundary
                boundary_crossing_edges = []
                for u, v, data in G.edges(data=True):
                    u_pos = node_positions[u]
                    v_pos = node_positions[v]
                    
                    # Check if one node is inside and one is outside
                    u_inside = u in inside_nodes
                    v_inside = v in inside_nodes
                    
                    if u_inside != v_inside:  # One inside, one outside - boundary crossing
                        edge_line = LineString([u_pos, v_pos])
                        highway_type = data.get('highway', 'unknown')
                        if isinstance(highway_type, list):
                            highway_type = highway_type[0] if highway_type else 'unknown'
                        
                        # Add as a boundary crossing
                        intersection = edge_line.intersection(cluster_poly.boundary)
                        if intersection.geom_type == 'Point':
                            boundary_crossing_edges.append({
                                'edge': (u, v),
                                'highway': highway_type,
                                'crossing_point': (intersection.y, intersection.x)
                            })
                
                print(f"DEBUG: Found {len(boundary_crossing_edges)} boundary crossing edges")
                
                # Add boundary crossings as access points
                for edge in boundary_crossing_edges:
                    lat, lon = edge['crossing_point']
                    
                    # Check road type
                    road_type = edge['highway']
                    if road_type in ['primary', 'secondary', 'tertiary', 'trunk', 'unclassified']:
                        # Main roads are important access points
                        confidence = 0.9
                    else:
                        # Minor roads like residential, service are less important
                        confidence = 0.7
                    
                    # Add to access points
                    access_points.append({
                        'lat': lat,
                        'lon': lon,
                        'from_type': road_type,
                        'to_type': 'residential',
                        'confidence': confidence,
                        'source': 'topology_bottleneck'
                    })
                
                # If we have enough boundary crossings, we can proceed
                # Otherwise, try to calculate betweenness centrality
                if len(access_points) < 2:
                    print("DEBUG: Not enough boundary crossings, calculating betweenness centrality")
                    
                    # Calculate edge betweenness centrality
                    edge_bc = nx.edge_betweenness_centrality(G.to_undirected())
                    
                    # Find high betweenness edges near the cluster
                    threshold = 0.5  # Relative threshold
                    max_bc = max(edge_bc.values()) if edge_bc else 0
                    
                    high_bc_edges = []
                    for (u, v), bc in edge_bc.items():
                        if bc / max_bc >= threshold:
                            u_pos = node_positions[u]
                            v_pos = node_positions[v]
                            
                            # Check if this edge is near the cluster boundary
                            edge_line = LineString([u_pos, v_pos])
                            if edge_line.distance(cluster_poly) < 0.0005:  # ~50m
                                # Get edge data
                                if G.has_edge(u, v):
                                    data = G.get_edge_data(u, v)
                                elif G.has_edge(v, u):
                                    data = G.get_edge_data(v, u)
                                else:
                                    data = {}
                                
                                highway_type = data.get('highway', 'unknown')
                                if isinstance(highway_type, list):
                                    highway_type = highway_type[0] if highway_type else 'unknown'
                                
                                high_bc_edges.append({
                                    'edge': (u, v),
                                    'bc': bc / max_bc,
                                    'highway': highway_type,
                                    'midpoint': ((u_pos[0] + v_pos[0])/2, (u_pos[1] + v_pos[1])/2)
                                })
                    
                    # Sort by betweenness and add top edges
                    for edge in sorted(high_bc_edges, key=lambda x: x['bc'], reverse=True)[:2]:
                        lat, lon = edge['midpoint']
                        access_points.append({
                            'lat': lat,
                            'lon': lon,
                            'from_type': edge['highway'],
                            'to_type': 'residential',
                            'confidence': edge['bc'],
                            'source': 'betweenness_centrality'
                        })
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"DEBUG: Error in topology analysis: {e}")
        
        # Step 5: Check for barrier tags
        if barriers:
            print("DEBUG: Processing barrier tags")
            for barrier in barriers:
                barrier_lat = barrier['lat']
                barrier_lon = barrier['lon']
                
                # Check if barrier is near the cluster boundary
                barrier_point = Point(barrier_lat, barrier_lon)
                if cluster_poly.buffer(0.0002).contains(barrier_point):  # ~20m buffer
                    barrier_type = barrier['type']
                    tags = barrier['tags']
                    
                    # Checkpoints and gates are high-confidence barriers
                    if barrier_type in ['checkpoint', 'gate', 'lift_gate', 'toll_booth']:
                        confidence = 0.95
                    # Traffic signals and stops are medium confidence
                    elif barrier_type in ['traffic_signals', 'stop']:
                        confidence = 0.75
                    # Other barriers are lower confidence
                    else:
                        confidence = 0.6
                    
                    # Determine road type if available
                    road_type = tags.get('highway', 'unknown')
                    
                    # Add to access points
                    access_points.append({
                        'lat': barrier_lat,
                        'lon': barrier_lon,
                        'from_type': road_type,
                        'to_type': 'residential',
                        'barrier_type': barrier_type,
                        'confidence': confidence,
                        'source': 'osm_barrier'
                    })
        
        # Step 6: Deduplicate access points
        unique_points = []
        for point in access_points:
            # Check if we already have a similar point
            is_duplicate = False
            for existing in unique_points:
                if (abs(point['lat'] - existing['lat']) < 0.0001 and 
                    abs(point['lon'] - existing['lon']) < 0.0001):
                    is_duplicate = True
                    # Keep the higher confidence one
                    if point.get('confidence', 0) > existing.get('confidence', 0):
                        existing.update(point)
                    break
            
            if not is_duplicate:
                unique_points.append(point)
        
        # Step 7: Ensure at least one access point (fallback to directional checkpoints)
        if not unique_points:
            print("DEBUG: No access points found, creating fallbacks")
            
            # Create checkpoints in cardinal directions from cluster center
            directions = [
                (0.001, 0),      # North
                (0, 0.001),      # East
                (-0.001, 0),     # South
                (0, -0.001)      # West
            ]
            
            # Add at least one fallback checkpoint
            lat, lon = center_lat + directions[0][0], center_lon + directions[0][1]
            unique_points.append({
                'lat': lat,
                'lon': lon,
                'from_type': 'residential',
                'to_type': 'residential',
                'confidence': 0.5,
                'source': 'fallback_direction'
            })
        
        print(f"DEBUG: Returning {len(unique_points)} access points")
        return unique_points