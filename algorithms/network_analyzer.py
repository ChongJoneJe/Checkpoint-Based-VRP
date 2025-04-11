import osmnx as ox
import networkx as nx
import numpy as np
from shapely.geometry import Point, LineString, Polygon
from shapely.ops import unary_union
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import time
import random
import os
from collections import Counter

class NetworkAnalyzer:
    """Analyze road networks to identify cluster access points and bottlenecks"""
    
    def __init__(self):
        """Initialize the network analyzer"""
        # Configure osmnx using new settings API
        ox.settings.use_cache = True
        ox.settings.log_console = False
        
        # Mapping of road types to hierarchy levels (lower number = more important)
        self.road_hierarchy = {
            'motorway': 1,
            'trunk': 2,
            'primary': 3,
            'secondary': 4, 
            'tertiary': 5,
            'unclassified': 6,
            'residential': 7,
            'service': 8,
            'track': 9,
            'path': 10,
            'footway': 11,
            'cycleway': 12,
            'living_street': 7,
            'pedestrian': 11
        }
    
    def find_cluster_access_points(self, location_coords, cluster_center, buffer_radius=300):
        """
        Find access points (checkpoints) for a cluster based on network topology
        
        Args:
            location_coords: List of (lat, lon) tuples for locations in the cluster
            cluster_center: (lat, lon) tuple for the center of the cluster
            buffer_radius: Radius in meters to extend beyond the cluster boundary
            
        Returns:
            list: List of dictionaries containing access point details
        """
        print(f"Analyzing network for cluster with {len(location_coords)} locations")
        
        try:
            # 1. Create a bounding polygon from the cluster locations
            center_lat, center_lon = cluster_center
            
            # If we have very few locations, use a circle around the cluster center
            if len(location_coords) < 3:
                print("Using circular buffer around cluster center")
                circle = Point(center_lon, center_lat).buffer(0.002)  # ~200m radius
                polygon = circle
            else:
                # Create convex hull from locations
                points = [Point(lon, lat) for lat, lon in location_coords]
                polygon = unary_union(points).convex_hull
                
                # Buffer the polygon to include some area around the cluster
                polygon = polygon.buffer(0.002)  # ~200m radius
            
            # 2. Download the street network within and around the cluster
            try:
                # Try to get the network within the polygon plus a buffer
                buffered_polygon = polygon.buffer(buffer_radius/111000)  # Convert meters to degrees
                network = ox.graph_from_polygon(buffered_polygon, network_type='drive')
                print(f"Downloaded network with {len(network.nodes)} nodes and {len(network.edges)} edges")
            except Exception as e:
                print(f"Error getting network from polygon: {str(e)}")
                # Fall back to using a circle around the center
                network = ox.graph_from_point((center_lat, center_lon), dist=buffer_radius*1.5, network_type='drive')
                print(f"Using fallback: Downloaded network with {len(network.nodes)} nodes and {len(network.edges)} edges")
            
            # 3. Add edge types and hierarchies for analysis
            self._enrich_network(network)
            
            # 4. Identify nodes inside the cluster
            inside_nodes = []
            for node, data in network.nodes(data=True):
                point = Point(data['x'], data['y'])
                if polygon.contains(point):
                    inside_nodes.append(node)
            
            print(f"Identified {len(inside_nodes)} nodes inside the cluster")
            
            if len(inside_nodes) == 0:
                print("No nodes found inside the cluster, using nearest nodes to locations")
                inside_nodes = []
                for lat, lon in location_coords:
                    nearest = ox.distance.nearest_nodes(network, lon, lat)
                    inside_nodes.append(nearest)
                inside_nodes = list(set(inside_nodes))  # Remove duplicates
            
            # 5. Identify possible access points using various methods
            access_points = []
            
            # Method 1: Find articulation points (bottlenecks) connecting inside to outside
            articulation_points = self._find_articulation_points(network, inside_nodes)
            
            if articulation_points:
                print(f"Found {len(articulation_points)} articulation points")
                for node in articulation_points:
                    access_points.append(self._create_access_point(network, node, "articulation_point"))
            
            # Method 2: Look for road hierarchy transitions
            transition_points = self._find_highway_transitions(network, inside_nodes)
            
            if transition_points:
                print(f"Found {len(transition_points)} road hierarchy transition points")
                for node in transition_points:
                    access_points.append(self._create_access_point(network, node, "highway_transition"))
            
            # Method 3: Check for explicit barrier tags
            barrier_points = self._find_barrier_nodes(network, inside_nodes)
            
            if barrier_points:
                print(f"Found {len(barrier_points)} barrier points")
                for node in barrier_points:
                    access_points.append(self._create_access_point(network, node, "barrier", confidence=1.0))
            
            # 6. Deduplicate and rank access points
            access_points = self._deduplicate_access_points(access_points)
            
            # 7. If no access points found, use the nearest main road connections
            if not access_points:
                print("No access points found with topology methods, using nearest main road connections")
                access_points = self._find_nearest_main_road_connections(network, inside_nodes)
            
            print(f"Final access points: {len(access_points)}")
            return access_points
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error analyzing network: {str(e)}")
            return []
    
    def _enrich_network(self, network):
        """Add additional attributes to network edges for analysis"""
        
        # Add hierarchy value to each edge based on road type
        for u, v, k, data in network.edges(keys=True, data=True):
            # Get highway type
            highway = data.get('highway', 'unclassified')
            
            # Handle lists (some edges have multiple highway types)
            if isinstance(highway, list):
                highway = highway[0]
            
            # Assign hierarchy level
            hierarchy = self.road_hierarchy.get(highway, 9)  # Default to high number if unknown
            network.edges[u, v, k]['hierarchy'] = hierarchy
            
            # Add is_main_road flag
            network.edges[u, v, k]['is_main_road'] = hierarchy <= 5  # primary, secondary, tertiary and above
            
            # Add is_residential flag
            network.edges[u, v, k]['is_residential'] = highway in ['residential', 'living_street']
    
    def _find_articulation_points(self, network, inside_nodes):
        """Find articulation points (bottlenecks) that connect inside to outside"""
        if not inside_nodes:
            return []
            
        # Create a subgraph of inside nodes to work with
        inside_subgraph = network.subgraph(inside_nodes)
        
        # Get connected components inside the cluster
        components = list(nx.connected_components(inside_subgraph.to_undirected()))
        
        articulation_points = []
        
        # For each connected component inside the cluster
        for component in components:
            # Create a set of boundary nodes (inside nodes that connect to outside)
            boundary_nodes = set()
            
            # For each node in this component
            for node in component:
                # Get all neighbors in the full network
                neighbors = set(network.successors(node)) | set(network.predecessors(node))
                
                # If any neighbor is outside the cluster, this is a boundary node
                if any(neigh not in inside_nodes for neigh in neighbors):
                    boundary_nodes.add(node)
            
            # Add these boundary nodes as potential articulation points
            articulation_points.extend(boundary_nodes)
        
        return articulation_points
    
    def _find_highway_transitions(self, network, inside_nodes):
        """Find nodes where there's a transition from main roads to residential/service roads"""
        transitions = []
        
        for node in inside_nodes:
            # Skip if not in network
            if node not in network:
                continue
                
            # Get all edges connected to this node
            out_edges = list(network.out_edges(node, keys=True, data=True))
            in_edges = list(network.in_edges(node, keys=True, data=True))
            all_edges = out_edges + in_edges
            
            # Skip if no edges
            if not all_edges:
                continue
            
            # Check if there's a mix of main roads and residential/service roads
            has_main_road = any(data.get('is_main_road', False) for _, _, _, data in all_edges)
            has_residential = any(data.get('is_residential', False) for _, _, _, data in all_edges)
            
            # If we have both types, this is a transition point
            if has_main_road and has_residential:
                transitions.append(node)
        
        return transitions
    
    def _find_barrier_nodes(self, network, nodes_of_interest):
        """Find nodes with barrier tags like gates, bollards, etc."""
        barrier_nodes = []
        
        for node in nodes_of_interest:
            # Skip if not in network
            if node not in network.nodes:
                continue
                
            # Get node data
            node_data = network.nodes[node]
            
            # Check for barrier tag
            if 'barrier' in node_data:
                barrier_nodes.append(node)
                continue
            
            # Check edges for access restrictions that might indicate a checkpoint
            edges = list(network.out_edges(node, keys=True, data=True)) + list(network.in_edges(node, keys=True, data=True))
            
            has_restricted_access = False
            for _, _, _, data in edges:
                # Check various tags that might indicate restricted access
                if any(data.get(tag) in ['private', 'residents', 'no', 'destination'] 
                       for tag in ['access', 'motor_vehicle', 'vehicle']):
                    has_restricted_access = True
                    break
            
            if has_restricted_access:
                barrier_nodes.append(node)
        
        return barrier_nodes
    
    def _create_access_point(self, network, node, point_type, confidence=0.7):
        """Create an access point dictionary from a node"""
        # Get node coordinates
        y, x = network.nodes[node]['y'], network.nodes[node]['x']
        
        # Determine road types on both sides of this access point
        from_type = 'unknown'
        to_type = 'unknown'
        
        # Get all connected edges
        edges = list(network.out_edges(node, keys=True, data=True)) + list(network.in_edges(node, keys=True, data=True))
        
        # Extract highway types
        highway_types = [data.get('highway', 'unknown') for _, _, _, data in edges]
        
        # Handle lists (some edges have multiple highway types)
        flat_types = []
        for htype in highway_types:
            if isinstance(htype, list):
                flat_types.extend(htype)
            else:
                flat_types.append(htype)
        
        # Count occurrences to get the most common types
        type_counts = Counter(flat_types)
        
        # Get the two most common types
        most_common = type_counts.most_common(2)
        
        if most_common:
            from_type = most_common[0][0]
            
            if len(most_common) > 1:
                to_type = most_common[1][0]
            else:
                to_type = from_type
        
        # Create the access point dictionary
        access_point = {
            'lat': y,
            'lon': x,
            'from_type': from_type,
            'to_type': to_type,
            'detection_method': point_type,
            'confidence': confidence
        }
        
        return access_point
    
    def _deduplicate_access_points(self, access_points, distance_threshold=50):
        """Deduplicate access points that are very close to each other"""
        if not access_points:
            return []
            
        # Convert distance threshold from meters to approximate degrees
        degree_threshold = distance_threshold / 111000  # 111km per degree at equator
        
        # Implement a simple clustering algorithm
        clusters = []
        
        # For each access point
        for point in access_points:
            lat, lon = point['lat'], point['lon']
            
            # Check if close to an existing cluster
            found_cluster = False
            for cluster in clusters:
                for existing in cluster:
                    # Calculate approximate distance
                    dist = ((lat - existing['lat'])**2 + (lon - existing['lon'])**2)**0.5
                    
                    if dist < degree_threshold:
                        # Add to this cluster
                        cluster.append(point)
                        found_cluster = True
                        break
                
                if found_cluster:
                    break
            
            # If not close to any existing cluster, create a new one
            if not found_cluster:
                clusters.append([point])
        
        # For each cluster, select the best point (highest confidence)
        best_points = []
        for cluster in clusters:
            best = max(cluster, key=lambda p: p.get('confidence', 0))
            best_points.append(best)
        
        return best_points
    
    def _find_nearest_main_road_connections(self, network, inside_nodes):
        """Find the nearest connections to main roads as a fallback method"""
        if not inside_nodes:
            return []
            
        # 1. Identify main road edges
        main_road_edges = []
        for u, v, k, data in network.edges(keys=True, data=True):
            if data.get('is_main_road', False):
                main_road_edges.append((u, v, k, data))
        
        if not main_road_edges:
            return []
            
        # 2. For each inside node, find the distance to the nearest main road
        connections = []
        for node in inside_nodes:
            # Skip if not in network
            if node not in network:
                continue
                
            # Get coordinates of this node
            node_y, node_x = network.nodes[node]['y'], network.nodes[node]['x']
            
            # Calculate distance to each main road edge
            for u, v, k, data in main_road_edges:
                # Skip if nodes are not in network
                if u not in network.nodes or v not in network.nodes:
                    continue
                    
                # Get coordinates of edge endpoints
                u_y, u_x = network.nodes[u]['y'], network.nodes[u]['x']
                v_y, v_x = network.nodes[v]['y'], network.nodes[v]['x']
                
                # Calculate distance from node to edge (approximate)
                dist_u = ((node_y - u_y)**2 + (node_x - u_x)**2)**0.5
                dist_v = ((node_y - v_y)**2 + (node_x - v_x)**2)**0.5
                
                connections.append((node, min(dist_u, dist_v)))
        
        # Sort by distance
        connections.sort(key=lambda x: x[1])
        
        # Take the 2 closest connections (or fewer if there aren't 2)
        closest_nodes = [conn[0] for conn in connections[:2]]
        
        # Create access points from these nodes
        access_points = []
        for node in closest_nodes:
            access_points.append(self._create_access_point(network, node, "nearest_main_road", confidence=0.5))
        
        return access_points
    
    def visualize_cluster_network(self, location_coords, cluster_center, access_points=None, 
                                 warehouse_coords=None, routes=None, buffer_radius=300, output_path=None):
        """Visualize a cluster with its road network, routes, and identified access points"""
        # Skip visualization if matplotlib is not available
        try:
            import matplotlib.pyplot as plt
            import matplotlib
            matplotlib.use('Agg')  # Non-interactive backend
        except ImportError:
            print("DEBUG: Matplotlib not available, skipping visualization")
            return False
        
        try:
            # 1. Create a bounding polygon from the cluster locations
            center_lat, center_lon = cluster_center
            
            # If we have very few locations, use a circle around the cluster center
            if len(location_coords) < 3:
                circle = Point(center_lon, center_lat).buffer(0.002)  # ~200m radius
                polygon = circle
            else:
                # Create convex hull from locations
                points = [Point(lon, lat) for lat, lon in location_coords]
                polygon = unary_union(points).convex_hull
                
                # Buffer the polygon to include some area around the cluster
                polygon = polygon.buffer(0.002)  # ~200m radius
            
            # If warehouse is provided, extend the area to include it
            if warehouse_coords:
                w_lat, w_lon = warehouse_coords
                expanded_points = [Point(lon, lat) for lat, lon in location_coords] + [Point(w_lon, w_lat)]
                expanded_area = unary_union(expanded_points).convex_hull.buffer(0.003)
                plot_polygon = expanded_area
            else:
                plot_polygon = polygon.buffer(buffer_radius/111000)  # Convert meters to degrees
            
            # 2. Download the street network for the visualization area
            try:
                # Try to get the network within the polygon plus a buffer
                network = ox.graph_from_polygon(plot_polygon, network_type='drive')
            except Exception as e:
                print(f"Error getting network from polygon: {str(e)}")
                # Fall back to using a circle around the center
                network = ox.graph_from_point((center_lat, center_lon), dist=buffer_radius*1.5, network_type='drive')
            
            # 3. Create a custom color map for road hierarchy
            self._enrich_network(network)
            
            # 4. Create a base visualization of the network
            fig, ax = plt.subplots(figsize=(12, 10))
            
            # Create a GeoDataFrame for the cluster polygon
            polygon_gdf = gpd.GeoDataFrame(geometry=[polygon], crs="EPSG:4326")
            polygon_gdf.plot(ax=ax, alpha=0.2, color='lightblue', edgecolor='blue')
            
            # Plot the network with edge colors
            # FIX: Convert float edge colors to proper color values
            edge_colors = []
            for u, v, k, data in network.edges(keys=True, data=True):
                hierarchy = data.get('hierarchy', 9)
                # Create a grayscale color based on hierarchy (darker = more important)
                intensity = max(0.3, min(0.9, 0.9 - (hierarchy - 1) / 10))
                edge_colors.append(f"#{int(intensity*255):02x}{int(intensity*255):02x}{int(intensity*255):02x}")
            
            # Plot with edge colors as hex strings instead of float values
            ox.plot_graph(network, ax=ax, edge_color=edge_colors, edge_linewidth=1.5, node_size=0, 
                      bgcolor='white', show=False)
            
            # 5. Plot locations
            location_x = [lon for lat, lon in location_coords]
            location_y = [lat for lat, lon in location_coords]
            ax.scatter(location_x, location_y, c='blue', s=30, zorder=3, label='Locations')
            
            # 6. Plot cluster center
            ax.scatter(center_lon, center_lat, c='green', s=100, marker='*', zorder=3, label='Cluster Center')
            
            # 7. Plot warehouse if provided
            if warehouse_coords:
                w_lat, w_lon = warehouse_coords
                ax.scatter(w_lon, w_lat, c='purple', s=150, marker='^', zorder=3, label='Warehouse')
            
            # 8. Plot routes if provided
            if routes and len(routes) > 0:
                # Sample a few routes to avoid overcrowding the map
                max_routes_to_show = min(5, len(routes))
                sampled_routes = random.sample(routes, max_routes_to_show) if len(routes) > max_routes_to_show else routes
                
                for i, route in enumerate(sampled_routes):
                    # Extract coordinates for each node in the route
                    route_points = []
                    for node in route:
                        if node in network.nodes:
                            x = network.nodes[node]['x']
                            y = network.nodes[node]['y']
                            route_points.append((x, y))
                    
                    # Plot the route line
                    route_x = [p[0] for p in route_points]
                    route_y = [p[1] for p in route_points]
                    ax.plot(route_x, route_y, color='orange', linewidth=1.5, alpha=0.6, zorder=2)
            
            # 9. Plot access points if provided
            if access_points:
                access_x = [ap['lon'] for ap in access_points]
                access_y = [ap['lat'] for ap in access_points]
                ax.scatter(access_x, access_y, c='red', s=150, marker='o', edgecolor='black', 
                          linewidths=1, zorder=4, label='Access Points')
                
                # Add labels and confidence for access points
                for i, ap in enumerate(access_points):
                    confidence = int(ap.get('confidence', 0.7) * 100)
                    ax.annotate(f"CP{i+1}: {confidence}%", (ap['lon'], ap['lat']), 
                                textcoords="offset points", xytext=(0,10), 
                                ha='center', fontsize=9, fontweight='bold')
            
            # 10. Add legend and title
            ax.legend(loc='upper right')
            plt.title(f'Cluster Road Network Analysis')
            
            # 11. Save or display the figure
            if output_path:
                # Create directory if it doesn't exist
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                plt.savefig(output_path, dpi=300, bbox_inches='tight')
                plt.close(fig)
                return True
            else:
                plt.tight_layout()
                plt.show()
                return True
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error visualizing network: {str(e)}")
            return False

    def _calculate_fallback_checkpoint(self, cluster_id, locations):
        """
        Simple fallback method to identify a potential checkpoint based on the cluster boundary
        
        Args:
            cluster_id: ID of the cluster
            locations: List of location dictionaries with lat and lon
            
        Returns:
            list: List of checkpoint dictionaries (usually just one)
        """
        if not locations:
            return []
            
        # Calculate cluster center
        lats = [loc['lat'] for loc in locations]
        lons = [loc['lon'] for loc in locations]
        center_lat = sum(lats) / len(lats)
        center_lon = sum(lons) / len(lons)
        
        # Find the location furthest from the center
        max_dist = 0
        edge_point = None
        
        for loc in locations:
            dist = ((loc['lat'] - center_lat)**2 + (loc['lon'] - center_lon)**2)**0.5
            if dist > max_dist:
                max_dist = dist
                edge_point = loc
        
        if not edge_point:
            # If no edge point found, use the first location
            if locations:
                edge_point = locations[0]
            else:
                return []
        
        # Create a checkpoint at this edge point
        checkpoint = {
            'lat': edge_point['lat'],
            'lon': edge_point['lon'],
            'from_type': 'unknown',
            'to_type': 'residential',
            'confidence': 0.3  # Low confidence for fallback method
        }
        
        return [checkpoint]

    def find_route_based_access_points(self, location_coords, warehouse_coords, buffer_radius=300):
        """
        Find access points based on analyzing routes from all cluster locations to the warehouse.
        This method identifies common nodes where routes from cluster locations to warehouse intersect.
        
        Args:
            location_coords: List of (lat, lon) tuples for locations in the cluster
            warehouse_coords: (lat, lon) tuple for the warehouse location
            buffer_radius: Radius in meters to extend beyond the cluster boundary
                
        Returns:
            list: List of dictionaries containing access point details
        """
        print(f"Analyzing routes for {len(location_coords)} locations to warehouse")
        
        if not location_coords or not warehouse_coords:
            print("Missing locations or warehouse coordinates")
            return []
        
        try:
            # 1. Create a bounding polygon from the cluster locations
            # If we have very few locations, use a circle around the average
            avg_lat = sum(lat for lat, _ in location_coords) / len(location_coords)
            avg_lon = sum(lon for _, lon in location_coords) / len(location_coords)
            
            if len(location_coords) < 3:
                print("Using circular buffer around average location")
                polygon = Point(avg_lon, avg_lat).buffer(0.002)  # ~200m radius
            else:
                # Create convex hull from locations
                points = [Point(lon, lat) for lat, lon in location_coords]
                polygon = unary_union(points).convex_hull
                polygon = polygon.buffer(0.001)  # ~100m buffer
            
            # 2. Download a larger street network that contains both the cluster and warehouse
            try:
                # Create a larger polygon that contains both the cluster and warehouse
                w_lat, w_lon = warehouse_coords
                points = list(polygon.exterior.coords) + [(w_lon, w_lat)]
                points_gdf = gpd.GeoDataFrame(geometry=[Point(x, y) for x, y in points], crs="EPSG:4326")
                convex_hull = points_gdf.unary_union.convex_hull
                buffered_area = convex_hull.buffer(buffer_radius/111000)  # Convert meters to degrees
                
                # Get network within this larger area
                network = ox.graph_from_polygon(buffered_area, network_type='drive')
                print(f"Downloaded network with {len(network.nodes)} nodes and {len(network.edges)} edges")
            except Exception as e:
                print(f"Error getting network from polygon: {str(e)}")
                # Fall back to using a larger radius around the center
                network = ox.graph_from_point((avg_lat, avg_lon), dist=max(buffer_radius*3, 1500), network_type='drive')
                print(f"Using fallback: Downloaded network with {len(network.nodes)} nodes and {len(network.edges)} edges")
            
            # 3. Add edge types and hierarchies for analysis
            self._enrich_network(network)
            
            # 4. Find the nearest nodes in the network for locations and warehouse
            nearest_nodes = {}
            for i, (lat, lon) in enumerate(location_coords):
                try:
                    nearest = ox.distance.nearest_nodes(network, lon, lat)
                    nearest_nodes[i] = nearest
                except Exception as e:
                    print(f"Error finding nearest node for location {i}: {e}")
                    continue
            
            # Find warehouse node
            try:
                w_lat, w_lon = warehouse_coords
                warehouse_node = ox.distance.nearest_nodes(network, w_lon, w_lat)
            except Exception as e:
                print(f"Error finding warehouse node: {str(e)}")
                return []
            
            # 5. Compute routes from each location to the warehouse
            print(f"Computing routes to warehouse for {len(nearest_nodes)} locations")
            routes = []
            for loc_idx, node in nearest_nodes.items():
                try:
                    route = nx.shortest_path(network, node, warehouse_node, weight='length')
                    routes.append(route)
                except nx.NetworkXNoPath:
                    print(f"No path from location {loc_idx} to warehouse")
                except Exception as e:
                    print(f"Error computing route for location {loc_idx}: {str(e)}")
            
            if len(routes) == 0:
                print("Could not compute any routes to warehouse")
                return []
            
            # 6. Identify cluster boundary nodes
            # Create a polygon for the exact cluster boundary
            if len(location_coords) < 3:
                cluster_boundary = Point(avg_lon, avg_lat).buffer(0.0015)  # ~150m radius
            else:
                cluster_boundary = unary_union([Point(lon, lat) for lat, lon in location_coords]).convex_hull
                cluster_boundary = cluster_boundary.buffer(0.0005)  # ~50m buffer
            
            # 7. Find nodes that are part of routes and intersect with the cluster boundary
            boundary_crossings = {}
            
            for route_idx, route in enumerate(routes):
                # Check each consecutive pair of nodes in the route
                for i in range(len(route) - 1):
                    node1, node2 = route[i], route[i+1]
                    
                    # Get node coordinates
                    if node1 not in network.nodes or node2 not in network.nodes:
                        continue
                        
                    point1 = Point(network.nodes[node1]['x'], network.nodes[node1]['y'])
                    point2 = Point(network.nodes[node2]['x'], network.nodes[node2]['y'])
                    
                    # Check if one point is inside and the other is outside
                    inside1 = cluster_boundary.contains(point1)
                    inside2 = cluster_boundary.contains(point2)
                    
                    if inside1 != inside2:  # One inside, one outside = boundary crossing
                        # Use the inside node as the access point
                        crossing_node = node1 if inside1 else node2
                        
                        # Store this crossing point
                        if crossing_node not in boundary_crossings:
                            boundary_crossings[crossing_node] = 1
                        else:
                            boundary_crossings[crossing_node] += 1
            
            print(f"Found {len(boundary_crossings)} boundary crossing points")
            
            # 8. Rank boundary crossings by frequency
            ranked_crossings = sorted(boundary_crossings.items(), key=lambda x: x[1], reverse=True)
            
            # 9. Take the top 2 most common crossing points (or all if fewer than 2)
            top_crossing_nodes = [node for node, count in ranked_crossings[:min(2, len(ranked_crossings))]]
            
            # 10. Create access points from these nodes
            access_points = []
            for node in top_crossing_nodes:
                # Higher confidence for crossings used by more routes
                confidence = min(0.95, 0.5 + (boundary_crossings[node] / len(routes)) * 0.5)
                access_points.append(self._create_access_point(network, node, "route_crossing", confidence=confidence))
            
            # 11. If no access points found, fall back to the previous methods
            if not access_points:
                print("No route crossing points found, falling back to topology methods")
                return self.find_cluster_access_points(location_coords, (avg_lat, avg_lon))
            
            return access_points
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error in route analysis: {str(e)}")
            return []