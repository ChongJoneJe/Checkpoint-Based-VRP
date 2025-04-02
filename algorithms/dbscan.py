import numpy as np
import openrouteservice
from openrouteservice.distance_matrix import distance_matrix
import requests
import json
import os
import random
import time
import sqlite3
import re  # Import the re module for regular expressions
from utils.database import execute_read, execute_write, execute_many

class GeoDBSCAN:
    """
    Enhanced DBSCAN algorithm with geocoding and location database integration
    Works with SQLAlchemy models
    """
    def __init__(self, eps=0.5, min_samples=2, api_key=None, distance_metric='distance'):
        """
        Initialize the GeoDBSCAN algorithm with location database support.
        """
        self.eps = eps * 1000  # Convert to meters for OpenRouteService
        self.min_samples = min_samples
        self.labels_ = None
        self.n_clusters_ = 0
        self.core_sample_indices_ = []
        self.intersection_points = {}
        self.api_key = api_key
        self.distance_metric = distance_metric
        self.client = None
        
        # Initialize OpenRouteService client if API key provided
        if self.api_key:
            try:
                self.client = openrouteservice.Client(key=self.api_key)
                print(f"OpenRouteService client initialized successfully")
            except Exception as e:
                print(f"Error initializing OpenRouteService client: {str(e)}")
        else:
            print("No API key provided for OpenRouteService")
    
    def geocode_location(self, lat, lon, max_retries=3):
        """Geocode a location to get address components using Nominatim"""
        for attempt in range(max_retries):
            try:
                response = requests.get(
                    f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json&zoom=18&addressdetails=1",
                    headers={"User-Agent": "python-clustering-app"}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    address = data.get('address', {})
                    
                    result = {
                        'street': address.get('road') or address.get('pedestrian') or address.get('footway') or '',
                        'neighborhood': address.get('suburb') or address.get('neighbourhood') or address.get('residential') or '',
                        'town': address.get('town') or address.get('village') or '',
                        'city': address.get('city') or address.get('county') or '',
                        'postcode': address.get('postcode', ''),
                        'country': address.get('country', '')
                    }
                    
                    print(f"Successfully geocoded location: {lat}, {lon} → {result['street']}, {result['neighborhood']}")
                    return result
                
                elif response.status_code == 429:  # Too Many Requests
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    print(f"Rate limited by Nominatim, waiting {wait_time:.2f} seconds...")
                    time.sleep(wait_time)
                    continue
                    
                else:
                    print(f"Geocoding error: {response.status_code} - {response.text}")
                    time.sleep(1)
                    
            except Exception as e:
                print(f"Geocoding exception: {str(e)}")
                time.sleep(1)
        
        print(f"Failed to geocode location after {max_retries} attempts: {lat}, {lon}")
        return None
    
    def add_location_to_db(self, lat, lon, address=None):
        """Add a location to the database with its geocoded information"""
        if address is None:
            address = self.geocode_location(lat, lon)
            if address is None:
                print(f"WARNING: Failed to geocode location ({lat}, {lon})")
            else:
                print(f"Successfully geocoded ({lat}, {lon}) to {address.get('street', 'unknown street')}")
        
        if address:
            # Check if location exists
            existing = execute_read(
                "SELECT id FROM locations WHERE lat = ? AND lon = ?",
                (lat, lon),
                one=True
            )
            
            if existing:
                return existing['id']
            
            # Insert new location
            location_id = execute_write(
                """INSERT INTO locations 
                   (lat, lon, street, neighborhood, town, city, postcode, country)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    lat, lon, 
                    address.get('street', ''),
                    address.get('neighborhood', ''),
                    address.get('town', ''),
                    address.get('city', ''),
                    address.get('postcode', ''),
                    address.get('country', '')
                )
            )
            
            return location_id
        
        return None
    
    def find_matching_location(self, lat, lon, tolerance=0.0001):
        """
        Find if a location already exists in the database within tolerance
        
        Args:
            lat (float): Latitude
            lon (float): Longitude
            tolerance (float): Maximum distance to consider a match (in degrees)
            
        Returns:
            tuple: (location_id, address) if found, (None, None) otherwise
        """
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('''
            SELECT id, street, neighborhood, town, city, postcode, country
            FROM locations
            WHERE ABS(lat - ?) < ? AND ABS(lon - ?) < ?
        ''', (lat, tolerance, lon, tolerance))
        
        result = c.fetchone()
        conn.close()
        
        if result:
            location_id = result[0]
            address = {
                'street': result[1],
                'neighborhood': result[2],
                'town': result[3],
                'city': result[4],
                'postcode': result[5],
                'country': result[6]
            }
            return location_id, address
        
        return None, None
    
    def identify_intersections_for_location(self, lat, lon, warehouse_lat, warehouse_lon):
        """
        Find key intersections on the route from location to warehouse
        
        Args:
            lat (float): Location latitude
            lon (float): Location longitude
            warehouse_lat (float): Warehouse latitude
            warehouse_lon (float): Warehouse longitude
            
        Returns:
            list: List of intersection points
        """
        if self.client is None:
            print("No OpenRouteService client available - cannot identify intersections")
            return []
            
        try:
            # Get directions from location to warehouse
            coords = [[lon, lat], [warehouse_lon, warehouse_lat]]
            
            route = self.client.directions(
                coordinates=coords,
                profile='driving-car',
                format='geojson'
            )
            
            # Extract geometry from route
            geometry = route['features'][0]['geometry']
            coords = geometry['coordinates']
            
            if len(coords) < 3:
                print(f"Route too short to identify intersections: {len(coords)} points")
                return []
            
            # Identify potential intersection points
            intersections = []
            last_bearing = None
            
            for i in range(1, len(coords)):
                # Calculate bearing between consecutive points
                y = np.sin(coords[i][0] - coords[i-1][0]) * np.cos(coords[i][1])
                x = (np.cos(coords[i-1][1]) * np.sin(coords[i][1])) - \
                    (np.sin(coords[i-1][1]) * np.cos(coords[i][1]) * np.cos(coords[i][0] - coords[i-1][0]))
                bearing = np.degrees(np.arctan2(y, x)) % 360
                
                # If significant bearing change, mark as intersection
                if last_bearing is not None and abs(bearing - last_bearing) > 30:
                    intersections.append({
                        'lat': coords[i-1][1],  # Fix coordinate order (lat/lon)
                        'lon': coords[i-1][0], 
                        'position': i-1
                    })
                    
                last_bearing = bearing
            
            print(f"Identified {len(intersections)} intersections on route")
            return intersections
            
        except Exception as e:
            print(f"Error identifying intersections: {str(e)}")
            return []
    
    def identify_road_transitions(self, lat, lon, warehouse_lat, warehouse_lon):
        """Find transitions between road types on the route"""
        if not self.client:
            print("No OpenRouteService client available - cannot identify road transitions")
            return []
            
        try:
            # Calculate route from warehouse to destination
            route = self.client.directions(
                coordinates=[[warehouse_lon, warehouse_lat], [lon, lat]],
                profile='driving-car',
                format='geojson'
            )
            
            # Extract route geometry
            if not route or 'features' not in route or not route['features']:
                return []
                
            # Get route coordinates
            coords = route['features'][0]['geometry']['coordinates']
            
            # Now detect road type transitions
            # This is simplified - a real implementation would decode road types from OSM data
            transitions = []
            
            # Look for transitions where the bearing changes significantly
            last_bearing = None
            for i in range(1, len(coords)):
                # Calculate bearing
                y = np.sin(coords[i][0] - coords[i-1][0]) * np.cos(coords[i][1])
                x = (np.cos(coords[i-1][1]) * np.sin(coords[i][1])) - \
                    (np.sin(coords[i-1][1]) * np.cos(coords[i][1]) * np.cos(coords[i][0] - coords[i-1][0]))
                bearing = np.degrees(np.arctan2(y, x)) % 360
                
                # If significant bearing change, mark as potential transition point
                if last_bearing is not None and abs(bearing - last_bearing) > 45:
                    transitions.append({
                        'lat': coords[i][1],
                        'lon': coords[i][0],
                        'position': i,
                        'from_type': 'secondary',  # Simplified - would get from OSM in real impl
                        'to_type': 'residential',
                        'is_potential_checkpoint': True
                    })
                    
                last_bearing = bearing
            
            print(f"Identified {len(transitions)} potential checkpoint locations")
            return transitions
            
        except Exception as e:
            print(f"Error identifying road transitions: {str(e)}")
            return []

    def identify_access_points_from_segments(self, src_lat, src_lon, warehouse_lat, warehouse_lon):
        """
        Alternative method that uses OpenRouteService segments to identify road transitions
        """
        if self.client is None:
            print("No OpenRouteService client available")
            return []
            
        try:
            # Request directions with more detail
            route = self.client.directions(
                coordinates=[[src_lon, src_lat], [warehouse_lon, warehouse_lat]],
                profile='driving-car',
                format='json',  # Use JSON format which includes segments
                extra_info=['waytype', 'steepness']
            )
            
            # Extract segments
            segments = route.get('routes', [{}])[0].get('segments', [])
            print(f"DEBUG: Route has {len(segments)} segments")
            
            access_points = []
            prev_type = None
            
            # Process each segment
            for i, segment in enumerate(segments):
                # Get steps within segment
                steps = segment.get('steps', [])
                for j, step in enumerate(steps):
                    road_type = step.get('type', '')
                    way_type = step.get('way_type', 0)  # OpenRouteService way type
                    
                    # Map way_type numbers to road classifications (from ORS documentation)
                    way_types = {
                        0: 'unknown',
                        1: 'motorway', 
                        2: 'trunk',
                        3: 'primary',
                        4: 'secondary',
                        5: 'tertiary',
                        6: 'residential',
                        7: 'service',
                        8: 'path'
                    }
                    
                    current_type = way_types.get(way_type, 'unknown')
                    
                    # Check for transitions from residential to higher-class roads
                    if prev_type and prev_type != current_type:
                        if (prev_type == 'residential' and current_type in ['tertiary', 'secondary', 'primary']) or \
                           (prev_type == 'tertiary' and current_type in ['secondary', 'primary']):
                            
                            # Extract the location of this transition (beginning of current step)
                            location = step.get('location', [])
                            if location:
                                access_points.append({
                                    'lon': location[0],
                                    'lat': location[1],
                                    'position': i*100 + j,  # Synthetic position 
                                    'from_type': prev_type,
                                    'to_type': current_type
                                })
                                print(f"DEBUG: Found transition from {prev_type} to {current_type}")
                    
                    prev_type = current_type
            
            print(f"DEBUG: Found {len(access_points)} access points using segments approach")
            return access_points
            
        except Exception as e:
            print(f"ERROR: Failed to identify access points from segments: {str(e)}")
            import traceback
            traceback.print_exc()
            return []

    def identify_access_points_by_bearing(self, src_lat, src_lon, warehouse_lat, warehouse_lon):
        """
        Identify potential access points by detecting significant bearing changes
        """
        if self.client is None:
            return []
            
        try:
            # Get route
            route = self.client.directions(
                coordinates=[[src_lon, src_lat], [warehouse_lon, warehouse_lat]],
                profile='driving-car',
                format='geojson'
            )
            
            # Extract coordinates
            coords = route['features'][0]['geometry']['coordinates']
            
            # Look for significant bearing changes
            access_points = []
            last_bearing = None
            MIN_ANGLE_CHANGE = 60  # Minimum angle change to consider a significant turn
            
            for i in range(1, len(coords)):
                # Calculate bearing between consecutive points
                lon1, lat1 = coords[i-1]
                lon2, lat2 = coords[i]
                
                y = np.sin(lon2 - lon1) * np.cos(lat2)
                x = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(lon2 - lon1)
                bearing = np.degrees(np.arctan2(y, x)) % 360
                
                if last_bearing is not None:
                    # Calculate absolute bearing difference
                    diff = min(abs(bearing - last_bearing), 360 - abs(bearing - last_bearing))
                    
                    if diff > MIN_ANGLE_CHANGE:
                        # This is a significant turn, could be a security checkpoint
                        access_points.append({
                            'lat': lat1,
                            'lon': lon1,
                            'position': i-1,
                            'from_type': 'unknown',
                            'to_type': 'unknown',
                            'bearing_change': diff
                        })
                
                last_bearing = bearing
            
            # Sort by bearing change, most significant first
            access_points.sort(key=lambda x: x.get('bearing_change', 0), reverse=True)
            
            # Return the most significant turn if any found
            if access_points:
                # Just return the strongest candidate
                return [access_points[0]]
            
            return []
        
        except Exception as e:
            print(f"ERROR in bearing-based detection: {str(e)}")
            return []

    def identify_access_points_with_fallbacks(self, src_lat, src_lon, warehouse_lat, warehouse_lon):
        """
        Try multiple methods to identify access points with fallbacks
        """
        print(f"DEBUG: Trying to identify access points using multiple methods")
        
        # First try the tag-based approach
        access_points = self.identify_access_points(src_lat, src_lon, warehouse_lat, warehouse_lon)
        if access_points:
            print(f"DEBUG: Found {len(access_points)} access points using tag-based approach")
            return access_points
        
        # Then try segment-based approach
        print(f"DEBUG: Tag-based approach failed, trying segment-based approach")
        access_points = self.identify_access_points_from_segments(src_lat, src_lon, warehouse_lat, warehouse_lon)
        if access_points:
            print(f"DEBUG: Found {len(access_points)} access points using segment-based approach")
            return access_points
        
        # Finally, try bearing-based approach
        print(f"DEBUG: Segment-based approach failed, trying bearing-based approach")
        access_points = self.identify_access_points_by_bearing(src_lat, src_lon, warehouse_lat, warehouse_lon)
        if access_points:
            print(f"DEBUG: Found {len(access_points)} access points using bearing-based approach")
            return access_points
        
        # If all approaches fail, use a fallback coordinate at 1/3 the distance from destination to warehouse
        print(f"DEBUG: All approaches failed, using distance-based fallback")
        fallback = {
            'lat': src_lat + (warehouse_lat - src_lat) / 3,
            'lon': src_lon + (warehouse_lon - src_lon) / 3,
            'position': 0,
            'from_type': 'unknown',
            'to_type': 'unknown',
            'is_fallback': True
        }
        
        return [fallback]

    def _get_road_class(self, step):
        """Extract the road classification from route step"""
        # The actual field might vary depending on the ORS API version
        if 'highway_class' in step:
            return step['highway_class']
        elif 'road_class' in step:
            return step['road_class']
        elif 'type' in step:
            return step['type']
        
        # If no specific class, try to infer from name
        name = step.get('name', '').lower()
        if 'motorway' in name or 'highway' in name:
            return 'motorway'
        elif 'trunk' in name:
            return 'trunk'
        elif 'primary' in name:
            return 'primary'
        elif 'secondary' in name:
            return 'secondary'
        elif 'tertiary' in name:
            return 'tertiary'
        elif 'residential' in name or 'jalan' in name:
            return 'residential'
        elif 'service' in name:
            return 'service'
        else:
            return 'unclassified'

    def _is_security_checkpoint_transition(self, from_type, to_type):
        """
        Determine if a road transition is likely to be a security checkpoint
        
        Most security checkpoints are at transitions from residential to higher class roads
        """
        # Road hierarchy from smallest to largest
        hierarchy = [
            'service', 
            'living_street',
            'residential', 
            'unclassified',
            'tertiary', 
            'secondary', 
            'primary', 
            'trunk', 
            'motorway'
        ]
        
        # Get positions in hierarchy
        try:
            from_index = hierarchy.index(from_type)
            to_index = hierarchy.index(to_type)
        except ValueError:
            return False
        
        # Check if going from smaller to larger road class
        # Security checkpoints are typically at:
        # 1. residential → tertiary
        # 2. residential → secondary
        # 3. tertiary → secondary
        if from_type == 'residential' and to_type in ['tertiary', 'secondary', 'primary']:
            return True
        if from_type == 'tertiary' and to_type in ['secondary', 'primary']:
            return True
        
        return False

    def save_preset_with_clustering(self, preset_id, preset_name, warehouse, destinations):
        """
        Save a preset with all locations geocoded and clustered
        
        Args:
            preset_id (str): Unique preset ID
            preset_name (str): Name of the preset
            warehouse (list): [lat, lon] of warehouse
            destinations (list): List of [lat, lon] destination points
            
        Returns:
            dict: Result with preset_id and clusters
        """
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        try:
            # Start transaction
            conn.execute("BEGIN")
            
            # Add preset
            c.execute(
                "INSERT INTO presets (id, name) VALUES (?, ?)",
                (preset_id, preset_name)
            )
            
            # Process warehouse
            warehouse_id = self.add_location_to_db(warehouse[0], warehouse[1])
            
            # Link warehouse to preset
            c.execute(
                "INSERT INTO preset_locations (preset_id, location_id, is_warehouse) VALUES (?, ?, 1)",
                (preset_id, warehouse_id)
            )
            
            # Process destinations with smart clustering
            clusters = {}  # To track clusters and their points
            
            for dest in destinations:
                location_id, cluster_id, is_new = self.add_location_with_smart_clustering(
                    dest[0], dest[1], warehouse[0], warehouse[1]
                )
                
                if location_id and cluster_id:
                    # Link destination to preset
                    c.execute(
                        "INSERT INTO preset_locations (preset_id, location_id, is_warehouse) VALUES (?, ?, 0)",
                        (preset_id, location_id)
                    )
                    
                    # Track clusters for the response
                    if cluster_id not in clusters:
                        # Get cluster info
                        c.execute(
                            "SELECT name, centroid_lat, centroid_lon FROM clusters WHERE id = ?",
                            (cluster_id,)
                        )
                        cluster_info = c.fetchone()
                        
                        clusters[cluster_id] = {
                            'id': cluster_id,
                            'name': cluster_info[0],
                            'points': [],
                            'centroid': [cluster_info[1], cluster_info[2]]
                        }
                    
                    # Add this point to its cluster
                    clusters[cluster_id]['points'].append(dest)
            
            # Commit transaction
            conn.commit()
            
            # Convert clusters dict to list for the response
            clusters_list = list(clusters.values())
            
            return {
                'preset_id': preset_id,
                'clusters': clusters_list
            }
            
        except Exception as e:
            # Rollback transaction on error
            conn.rollback()
            print(f"Error saving preset with clustering: {str(e)}")
            raise
            
        finally:
            conn.close()
    
    def _calculate_distance_matrix(self, X):
        """
        Calculate distance matrix using OpenRouteService
        
        Args:
            X: Array of shape (n_samples, 2) with lat/lon coordinates [lat, lon]
            
        Returns:
            Distance matrix in meters
        """
        if self.client is None:
            raise ValueError("API key is required for distance matrix calculation")
            
        n_samples = len(X)
        
        # OpenRouteService expects coordinates as [lon, lat]
        locations = [[point[1], point[0]] for point in X]
        
        # Request distance matrix from OpenRouteService
        # Note: OpenRouteService has limits on the number of locations
        # For larger datasets, you may need to split this into multiple requests
        try:
            result = self.client.distance_matrix(
                locations=locations,
                metrics=[self.distance_metric],
                profile='driving-car'
            )
            
            # Extract the distances (in meters)
            if self.distance_metric == 'duration':
                distances = np.array(result['durations'])
            else:
                distances = np.array(result['distances'])
                
            return distances
        except Exception as e:
            print(f"Error calculating distance matrix: {str(e)}")
            # Fall back to great circle distance if API fails
            print("Falling back to great circle distance")
            from geopy.distance import great_circle
            
            distances = np.zeros((n_samples, n_samples))
            for i in range(n_samples):
                for j in range(i+1, n_samples):
                    distance = great_circle((X[i][0], X[j][0]), (X[j][0], X[j][1])).meters
                    distances[i, j] = distance
                    distances[j, i] = distance
            
            return distances
    
    def fit(self, X):
        """
        Perform clustering on the input data using road network distances.
        
        Args:
            X: Array of shape (n_samples, 2) with lat/lon coordinates
        
        Returns:
            self
        """
        if len(X) == 0:
            self.labels_ = np.array([])
            return self
        
        n_samples = len(X)
        
        # Calculate distance matrix using OpenRouteService
        distances = self._calculate_distance_matrix(X)
        
        # Initialize labels as noise (-1)
        self.labels_ = np.full(n_samples, -1, dtype=np.intp)
        
        # Find neighbors for each point based on eps threshold
        neighbors = [np.where(distances[i] <= self.eps)[0] for i in range(n_samples)]
        
        # Find core points
        core_points = np.array([i for i in range(n_samples) if len(neighbors[i]) >= self.min_samples])
        self.core_sample_indices_ = core_points
        
        # Find clusters
        cluster_index = 0
        for point in core_points:
            if self.labels_[point] != -1:
                continue
                
            # Start a new cluster
            self.labels_[point] = cluster_index
            
            # Process neighbors
            queue = [point]
            while queue:
                current = queue.pop(0)
                # Add neighbors to cluster
                for neighbor_idx in neighbors[current]:
                    if self.labels_[neighbor_idx] == -1:
                        self.labels_[neighbor_idx] = cluster_index
                        
                        # If core point, add its neighbors to queue
                        if neighbor_idx in core_points:
                            queue.append(neighbor_idx)
            
            # Move to next cluster
            cluster_index += 1
        
        self.n_clusters_ = cluster_index
        
        # Generate intersection points (simplified as cluster centroids)
        self._create_centroids(X)
        
        return self
        
    def _create_centroids(self, X):
        """Create centroid points for each cluster as intersection points"""
        n_clusters = self.n_clusters_
        
        for cluster_idx in n_clusters:
            # Get points in this cluster
            cluster_mask = self.labels_ == cluster_idx
            cluster_points = np.array([X[i] for i, is_member in enumerate(cluster_mask) if is_member])
            
            if len(cluster_points) >= 2:
                # Calculate cluster centroid
                centroid = np.mean(cluster_points, axis=0)
                self.intersection_points[f"cluster_{cluster_idx}"] = centroid.tolist()
        
        return self

    def get_road_tags(self, lat, lon):
        """
        Use Nominatim to get road type information from a coordinate with multiple fallbacks.
        Tries different zoom levels and handles missing data gracefully.
        """
        try:
            print(f"DEBUG: Fetching road tags for ({lat}, {lon})")
            
            # Try with different zoom levels - zoom 18 for detail, 17 for broader view, 16 for even broader
            for zoom in [18, 17, 16]:
                response = requests.get(
                    f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json&zoom={zoom}&addressdetails=1&extratags=1",
                    headers={"User-Agent": "python-clustering-app"},
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Create a combined tags dictionary
                    result = {}
                    
                    # Track what data we found in debug log
                    found_data = []
                    
                    # 1. Check OSM class and type fields (primary source)
                    osm_class = data.get("class")
                    osm_type = data.get("type")
                    if osm_class and osm_type:
                        result["class"] = osm_class
                        result["type"] = osm_type
                        found_data.append(f"osm_class={osm_class}, osm_type={osm_type}")
                        
                        # If it's a "highway" type, this is what we're looking for
                        if osm_class == "highway":
                            result["highway"] = osm_type
                            found_data.append(f"highway={osm_type}")
                    
                    # 2. Check extratags (secondary source, less reliable)
                    extratags = data.get("extratags", {})
                    if extratags:
                        # Merge extratags into our result
                        result.update(extratags)
                        found_data.append(f"extratags={extratags}")
                    
                    # 3. Try to extract from address components (tertiary source)
                    address = data.get("address", {})
                    if address:
                        road = address.get("road")
                        if road:
                            result["road_name"] = road
                            found_data.append(f"road_name={road}")
                        
                        # See if the address contains hints about road type
                        for key in ["road_type", "highway", "street_type"]:
                            if key in address:
                                result["inferred_type"] = address[key]
                                found_data.append(f"inferred_type={address[key]}")
                    
                    # 4. If we have a name but not a type, try to infer type from name
                    if "name" in data and "highway" not in result:
                        name = data["name"].lower()
                        road_indicators = {
                            "highway": "primary",
                            "expressway": "primary", 
                            "freeway": "primary",
                            "motorway": "primary",
                            "jalan raya": "primary",
                            "jalan utama": "primary",
                            "main road": "primary",
                            "jalan": "secondary",
                            "lebuh": "secondary",
                            "persiaran": "secondary",
                            "lorong": "residential",
                            "lrg": "residential",
                            "jln": "secondary"
                        }
                        
                        for indicator, road_type in road_indicators.items():
                            if indicator in name:
                                result["inferred_highway"] = road_type
                                found_data.append(f"inferred_highway={road_type} from name={name}")
                                break
                    
                    print(f"DEBUG: Road tags found at zoom {zoom}: {', '.join(found_data)}")
                    
                    # If we found any useful data, return it
                    if result and ("highway" in result or "type" in result):
                        print(f"DEBUG: ✓ Successfully identified road information: {result}")
                        return result
                    
                    print(f"DEBUG: Found data but no explicit road type, trying lower zoom level")
                
                elif response.status_code == 429:  # Rate limit
                    print(f"DEBUG: Rate limited by Nominatim at zoom {zoom}, waiting 1s...")
                    time.sleep(1)
                else:
                    print(f"DEBUG: Nominatim error {response.status_code} at zoom {zoom}")
            
            # If we get here, we've tried all zoom levels with no success
            print(f"DEBUG: Failed to find road type after trying all zoom levels")
            
            # Last resort - use Overpass API to find nearest road
            return self.find_nearest_road(lat, lon)
            
        except Exception as e:
            print(f"ERROR: Exception in get_road_tags: {str(e)}")
            return {}

    def identify_access_points(self, src_lat, src_lon, warehouse_lat, warehouse_lon):
        """
        Identify access points along the route from a destination (src) to the warehouse.
        For each coordinate in the route, it reverse geocodes to extract 'highway' tags.
        Returns a list of checkpoint dicts for points where highway type is 'secondary' or 'primary'.
        """
        if self.client is None:
            print("No OpenRouteService client available - cannot identify access points")
            return []
        try:
            # Get the route from destination (src) to warehouse.
            print(f"DEBUG: Calculating route from ({src_lat}, {src_lon}) to warehouse ({warehouse_lat}, {warehouse_lon})")
            coords = [[src_lon, src_lat], [warehouse_lon, warehouse_lat]]
            
            try:
                route = self.client.directions(
                    coordinates=coords,
                    profile='driving-car',
                    format='geojson'
                )
                print(f"DEBUG: Route calculation successful, checking response structure...")
            except Exception as route_err:
                print(f"ERROR: Failed to calculate route: {str(route_err)}")
                return []
            
            # Validate route structure
            if not route:
                print("ERROR: Empty route response received")
                return []
            if 'features' not in route:
                print(f"ERROR: Unexpected route response structure - missing 'features' key: {route.keys()}")
                return []
            if not route['features']:
                print("ERROR: No features found in route response")
                return []
            if 'geometry' not in route['features'][0]:
                print(f"ERROR: No geometry in first feature: {route['features'][0].keys()}")
                return []
            
            geometry = route['features'][0]['geometry']
            if 'coordinates' not in geometry:
                print(f"ERROR: No coordinates in geometry: {geometry.keys()}")
                return []
                
            route_coords = geometry['coordinates']
            print(f"DEBUG: Route has {len(route_coords)} coordinate points")
            
            access_points = []
            # Iterate the route coordinates in order.
            points_checked = 0
            for i, pt in enumerate(route_coords):
                # Only check every 5th point to avoid excessive API calls
                if i % 5 != 0 and i != len(route_coords) - 1:  # Always check last point
                    continue
                
                points_checked += 1
                try:
                    # pt is [lon, lat]; call our helper to get road tags.
                    tags = self.get_road_tags(pt[1], pt[0])
                    if tags:
                        highway_val = tags.get("highway", "").lower()
                        print(f"DEBUG: Point {i}: ({pt[1]}, {pt[0]}) - Highway type: {highway_val}")
                        if highway_val in ("secondary", "primary"):
                            access_points.append({
                                'lat': pt[1],
                                'lon': pt[0],
                                'position': i,
                                'from_type': highway_val,
                                'to_type': highway_val  # In this context they are the same.
                            })
                            print(f"DEBUG: ✓ Found access point at position {i} - highway type: {highway_val}")
                    else:
                        print(f"DEBUG: No tags returned for point {i}: ({pt[1]}, {pt[0]})")
                except Exception as tag_err:
                    print(f"ERROR: Failed to get tags for point {i}: {str(tag_err)}")
            
            print(f"DEBUG: Checked {points_checked} out of {len(route_coords)} route points")
            print(f"DEBUG: Identified {len(access_points)} access point(s) along the route")
            
            if not access_points:
                print("DEBUG: No access points found - investigating first/last points...")
                # Check first and last points specifically
                for idx, desc in [(0, "first"), (-1, "last")]:
                    try:
                        pt = route_coords[idx]
                        tags = self.get_road_tags(pt[1], pt[0])
                        highway_val = tags.get("highway", "") if tags else "no tags"
                        print(f"DEBUG: {desc.upper()} point ({pt[1]}, {pt[0]}) - Highway type: {highway_val}")
                    except Exception as e:
                        print(f"ERROR: Failed to check {desc} point: {str(e)}")
            
            return access_points
        except Exception as e:
            print(f"ERROR: Error identifying access points: {str(e)}")
            import traceback
            traceback.print_exc()
            return []

    def add_location_with_smart_clustering(self, lat, lon, warehouse_lat, warehouse_lon):
        """
        Add a location to the database with smart clustering based on street pattern matching
        with enhanced fallback logic.
        """
        from repositories.location_repository import LocationRepository
        from repositories.cluster_repository import ClusterRepository
        
        print(f"DEBUG: Starting smart clustering for location ({lat}, {lon})")
        
        # Geocode the location to get address components
        address = self.geocode_location(lat, lon)
        if not address:
            print(f"WARNING: Could not geocode location ({lat}, {lon}) - creating without address data")
            address = {'street': '', 'neighborhood': '', 'town': '', 'city': '', 'postcode': '', 'country': ''}
        else:
            print(f"DEBUG: Address components: {address}")
        
        try:
            # Check if location exists
            existing_loc = LocationRepository.find_by_coordinates(lat, lon)
            if existing_loc:
                print(f"DEBUG: Found existing location ID: {existing_loc['id']}")
                location_id = existing_loc['id']
                LocationRepository.update_address(location_id, address)
                cluster_info = execute_read(
                    "SELECT cluster_id FROM location_clusters WHERE location_id = ?", 
                    (location_id,), 
                    one=True
                )
                cluster_id = cluster_info['cluster_id'] if cluster_info else None
                print(f"DEBUG: Existing location has cluster_id: {cluster_id}")
                return location_id, cluster_id, False
            
            # Insert new location
            location_id = LocationRepository.insert(lat, lon, address)
            print(f"DEBUG: Inserted new location with ID: {location_id}")
            
            # REFINED CLUSTERING LOGIC: Follow strict fallback sequence
            matches = []
            match_type = None
            
            # 1. FIRST TRY: Exact street name matching
            street = address.get('street', '')
            if street:
                print(f"DEBUG: Attempting street matching with: '{street}'")
                street_matches = LocationRepository.find_matching_street(street, location_id)
                if street_matches:
                    matches.extend(street_matches)
                    match_type = "exact_street"
                    print(f"DEBUG: Found {len(street_matches)} locations with exact street match: {street}")
                else:
                    print(f"DEBUG: No exact street matches found for: {street}")
            else:
                print(f"DEBUG: No street name available for matching")
            
            # 2. SECOND TRY: Development pattern matching
            if not matches:
                development_pattern = self._extract_development_pattern(street, address)
                if development_pattern:
                    print(f"DEBUG: Attempting development pattern matching with: '{development_pattern}'")
                    pattern_matches = LocationRepository.find_pattern_matches(development_pattern, location_id)
                    if pattern_matches:
                        matches.extend(pattern_matches)
                        match_type = "development_pattern"
                        print(f"DEBUG: Found {len(pattern_matches)} locations with development pattern match: {development_pattern}")
                    else:
                        print(f"DEBUG: No pattern matches found for: {development_pattern}")
                else:
                    print(f"DEBUG: No development pattern extracted")
            
            # 3. THIRD TRY: Neighborhood matching
            if not matches:
                neighborhood = address.get('neighborhood', '')
                if neighborhood:
                    print(f"DEBUG: Attempting neighborhood matching with: '{neighborhood}'")
                    neighborhood_matches = LocationRepository.find_matching_neighborhood(neighborhood, location_id)
                    if neighborhood_matches:
                        matches.extend(neighborhood_matches)
                        match_type = "neighborhood"
                        print(f"DEBUG: Found {len(neighborhood_matches)} locations with neighborhood match: {neighborhood}")
                    else:
                        print(f"DEBUG: No neighborhood matches found for: {neighborhood}")
                else:
                    print(f"DEBUG: No neighborhood available for matching")
            
            # 4. FOURTH TRY: Proximity matching
            if not matches:
                print(f"DEBUG: Attempting proximity matching within 0.002 degrees")
                proximity_matches = LocationRepository.find_nearby_locations(lat, lon, 0.002, location_id)
                if proximity_matches:
                    matches.extend(proximity_matches)
                    match_type = "proximity"
                    print(f"DEBUG: Found {len(proximity_matches)} locations within proximity range")
                    
                    # For proximity matches, try to refine by section identifier
                    section_id = self._extract_section_identifier(street)
                    if section_id:
                        print(f"DEBUG: Identified section identifier: {section_id}")
                        section_matches = [m for m in proximity_matches if 
                                           self._extract_section_identifier(m['street']) == section_id]
                        if section_matches:
                            matches = section_matches
                            match_type = "section_proximity"
                            print(f"DEBUG: Refined to {len(section_matches)} locations in same section: {section_id}")
                        else:
                            print(f"DEBUG: No locations with matching section '{section_id}' found")
                else:
                    print(f"DEBUG: No proximity matches found within 0.002 degrees")
            
            # Determine cluster based on matches
            cluster_id = None
            is_new_cluster = False
            
            if matches:
                print(f"DEBUG: Processing {len(matches)} matches of type: {match_type}")
                # First try to find an existing cluster in the matches
                for match in matches:
                    if match['cluster_id']:
                        cluster_id = match['cluster_id']
                        print(f"DEBUG: Assigning to existing cluster: {cluster_id} based on {match_type} match")
                        break
                
                # If no existing cluster found, create a new one
                if not cluster_id:
                    is_new_cluster = True
                    # Choose appropriate cluster name
                    if match_type == "development_pattern":
                        cluster_name = self._extract_development_pattern(street, address)
                    elif match_type == "neighborhood":
                        cluster_name = address.get('neighborhood', 'Unknown Area')
                    else:
                        cluster_name = self._extract_street_pattern(street)
                    
                    print(f"DEBUG: Creating new cluster with name: '{cluster_name}'")
                    cluster_id = ClusterRepository.create(cluster_name, lat, lon)
                    print(f"DEBUG: Created new cluster ID: {cluster_id}")
                    
                    # Add all matching locations to this new cluster
                    for match in matches:
                        print(f"DEBUG: Adding matched location {match['id']} to new cluster {cluster_id}")
                        ClusterRepository.add_location_to_cluster(match['id'], cluster_id)
            else:
                print(f"DEBUG: No matches found, creating new standalone cluster")
                is_new_cluster = True
                
                # Determine best cluster name when no matches found
                if address.get('neighborhood'):
                    cluster_name = address.get('neighborhood')
                    print(f"DEBUG: Using neighborhood as cluster name: '{cluster_name}'")
                elif street:
                    development_pattern = self._extract_development_pattern(street, address)
                    if development_pattern:
                        cluster_name = development_pattern
                        print(f"DEBUG: Using development pattern as cluster name: '{cluster_name}'")
                    else:
                        cluster_name = self._extract_street_pattern(street)
                        print(f"DEBUG: Using street pattern as cluster name: '{cluster_name}'")
                else:
                    cluster_name = "Unknown Location"
                    print(f"DEBUG: No identifiable name, using 'Unknown Location'")
                
                cluster_id = ClusterRepository.create(cluster_name, lat, lon)
                print(f"DEBUG: Created new cluster ID: {cluster_id}")
            
            # Add the current location to its cluster
            if cluster_id:
                print(f"DEBUG: Adding location {location_id} to cluster {cluster_id}")
                ClusterRepository.add_location_to_cluster(location_id, cluster_id)
            else:
                print(f"ERROR: Failed to determine cluster for location {location_id}")
            
            # If this location initiated a new cluster, identify access points
            if is_new_cluster:
                print(f"DEBUG: New cluster created - identifying access points")
                # Try multiple methods to find checkpoints with various fallbacks
                access_points = self.identify_access_points_with_fallbacks(lat, lon, warehouse_lat, warehouse_lon)
                
                if access_points:
                    print(f"DEBUG: Found {len(access_points)} access points")
                    for i, ap in enumerate(access_points):
                        checkpoint_id = self.save_cluster_checkpoint(cluster_id, ap)
                        print(f"DEBUG: Saved access point #{i+1} (ID: {checkpoint_id}) for cluster {cluster_id} at {ap['lat']}, {ap['lon']}")
                else:
                    print(f"ERROR: No access points found after trying all methods")
            
            return location_id, cluster_id, is_new_cluster
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"ERROR: Error in smart clustering: {str(e)}")
            return None, None, False

    def save_cluster_checkpoint(self, cluster_id, checkpoint_data):
        """Save a security checkpoint for a cluster"""
        try:
            print(f"DEBUG: Saving checkpoint for cluster {cluster_id}: {checkpoint_data}")
            
            # Check if checkpoint already exists
            existing = execute_read(
                "SELECT id FROM security_checkpoints WHERE cluster_id = ?",
                (cluster_id,),
                one=True
            )
            
            if existing:
                print(f"DEBUG: Updating existing checkpoint ID: {existing['id']}")
                # Update existing checkpoint
                execute_write(
                    """UPDATE security_checkpoints 
                       SET lat = ?, lon = ?, from_road_type = ?, to_road_type = ?
                       WHERE cluster_id = ?""",
                    (
                        checkpoint_data['lat'],
                        checkpoint_data['lon'],
                        checkpoint_data.get('from_type', ''),
                        checkpoint_data.get('to_type', ''),
                        cluster_id
                    )
                )
                print(f"DEBUG: Checkpoint updated successfully")
                return existing['id']
            else:
                print(f"DEBUG: Creating new checkpoint for cluster {cluster_id}")
                # Insert new checkpoint
                checkpoint_id = execute_write(
                    """INSERT INTO security_checkpoints
                       (cluster_id, lat, lon, from_road_type, to_road_type, confidence)
                       VALUES (?, ?, ?, ?, ?, 1.0)""",
                    (
                        cluster_id,
                        checkpoint_data['lat'],
                        checkpoint_data['lon'],
                        checkpoint_data.get('from_type', ''),
                        checkpoint_data.get('to_type', '')
                    )
                )
                print(f"DEBUG: New checkpoint created with ID: {checkpoint_id}")
                return checkpoint_id
        except Exception as e:
            print(f"ERROR: Failed to save cluster checkpoint: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    def _extract_street_pattern(self, street):
        """
        Extract a meaningful pattern from street names for cluster naming
        
        Args:
            street (str): Full street name
            
        Returns:
            str: Extracted pattern suitable for cluster naming
        """
        if not street:
            return "Unknown"
        
        # Remove common prefixes like "Jalan", "Lorong", etc.
        prefixes = ["jalan ", "jln ", "lorong ", "persiaran ", "lebuh "]
        street_lower = street.lower()
        
        for prefix in prefixes:
            if street_lower.startswith(prefix):
                street = street[len(prefix):]
                break
        
        # Split by common separators
        parts = street.split()
        
        # For multi-part street names like "Setia Nusantara U13/22T"
        if len(parts) >= 2:
            # If it has a section/identifier pattern (like U13/22T), remove that part
            last_part = parts[-1]
            if ('/' in last_part) or (last_part[0].upper() == 'U' and last_part[1:].isdigit()):
                parts = parts[:-1]
            
            # Take up to first 3 parts for reasonable length
            if len(parts) > 3:
                parts = parts[:3]
            
            return ' '.join(parts).title()
        
        return street.title()

    def _extract_development_pattern(self, street, neighborhood, address=None):
        """
        Extract housing development name from street patterns
        
        Args:
            street (str): Street name like "Jalan Setia Nusantara U13/22T"
            
        Returns:
            str: Development name like "Setia Nusantara"
        """
        if not street:
            return None
            
        street_lower = street.lower()
        
        # Remove common prefixes
        prefixes = ["jalan ", "jln ", "lorong ", "persiaran ", "lebuh ", "lebuhraya "]
        for prefix in prefixes:
            if street_lower.startswith(prefix):
                street = street[len(prefix):]
                break
        
        # Handle special patterns in Malaysian addresses
        
        # Pattern 1: Development with section numbers (common in Shah Alam, Setia Alam, etc.)
        # Example: "Setia Nusantara U13/22T" -> "Setia Nusantara"
        section_pattern = r'(.+?)\s+(?:U\d+|\d+/\d+|S\d+|Section \d+)'
        section_match = re.search(section_pattern, street, re.IGNORECASE)
        if section_match:
            return section_match.group(1).strip().title()
        
        # Pattern 2: Development with numbered streets (common in Taman areas)
        # Example: "Mawar 1" -> "Mawar"
        numbered_street_pattern = r'(.+?)\s+\d+\s*$'
        numbered_match = re.search(numbered_street_pattern, street, re.IGNORECASE)
        if numbered_match:
            return numbered_match.group(1).strip().title()
        
        # Pattern 3: Extract Taman name if present
        # Example: "Taman Sri Muda 25/1" -> "Sri Muda"
        taman_pattern = r'taman\s+(.+?)(?:\s+\d|\s*$)'
        taman_match = re.search(taman_pattern, street_lower, re.IGNORECASE)
        if taman_match:
            return taman_match.group(1).strip().title()
        
        # Pattern 4: Housing estates with "Apartment", "Kondominium", "Residensi", etc.
        residence_pattern = r'((?:apartment|kondominium|residensi|residency|condo|condominium)\s+.+?)(?:\s+\d|\s*$)'
        residence_match = re.search(residence_pattern, street_lower, re.IGNORECASE)
        if residence_match:
            return residence_match.group(1).strip().title()
        
        # If street is empty but we have neighborhood info, use that
        if (not street or street.strip() == '') and address and address.get('neighborhood'):
            neighborhood = address.get('neighborhood')
            print(f"DEBUG: Using neighborhood '{neighborhood}' for development pattern (no street)")
        
        # If no specific pattern matches, take the first 2 words
        words = street.split()
        if len(words) >= 2:
            return ' '.join(words[:2]).title()
        elif len(words) == 1:
            return words[0].title()
            
        return street.title()

    def _extract_section_identifier(self, street):
        """
        Extract section identifier from addresses like "Jalan U13/56C"
        
        Args:
            street (str): Street name
            
        Returns:
            str: Section identifier (e.g., "U13") or None
        """
        if not street:
            return None
            
        # Look for section patterns in Malaysian addresses
        # Common patterns: U13/56C, 25/3, SS15/3D
        section_patterns = [
            r'([A-Z]\d+)(?:/\d+[A-Z]?)?',  # U13/56C -> U13
            r'(SS\d+)(?:/\d+[A-Z]?)?',     # SS15/3D -> SS15
            r'(USJ\d+)(?:/\d+[A-Z]?)?',    # USJ1/3A -> USJ1
            r'(PJU\d+(?:/\d+)?)(?:/\d+[A-Z]?)?',  # PJU10/11D -> PJU10
            r'(Section \d+)',               # Section 13
            r'^(\d+)(?:/\d+[A-Z]?)'        # 25/3B -> 25
        ]
        
        for pattern in section_patterns:
            match = re.search(pattern, street, re.IGNORECASE)
            if match:
                return match.group(1).upper()
                
        return None

    def compare_routes(self, route1_intersections, route2_intersections):
        """
        Compare two routes based on their intersections
        
        Args:
            route1_intersections: List of intersection IDs for first route
            route2_intersections: List of intersection IDs for second route
            
        Returns:
            float: Similarity score between 0-1 (higher = more similar)
        """
        # Convert to sets for faster intersection calculation
        set1 = set(route1_intersections)
        set2 = set(route2_intersections)
        
        # Find common intersections
        common = set1.intersection(set2)
        
        # Simple Jaccard similarity: intersection size / union size
        union = set1.union(set2)
        if not union:
            return 0
        
        return len(common) / len(union)

    def get_cluster_checkpoint(self, cluster_id):
        """Get the security checkpoint for a cluster"""
        try:
            checkpoint = execute_read(
                """SELECT id, lat, lon, from_road_type, to_road_type
                   FROM security_checkpoints 
                   WHERE cluster_id = ?""",
                (cluster_id,),
                one=True
            )
            return checkpoint
        except Exception as e:
            print(f"Error retrieving cluster checkpoint: {str(e)}")
            return None

    def find_nearest_road(self, lat, lon, radius=100):
        """
        Find the nearest road to a coordinate using Overpass API.
        This is a fallback when direct nominatim reverse doesn't yield road type.
        
        Args:
            lat: Latitude
            lon: Longitude
            radius: Search radius in meters
        
        Returns:
            dict: Road tags or empty dict if none found
        """
        try:
            print(f"DEBUG: Trying to find nearest road within {radius}m of ({lat}, {lon})")
            
            # Overpass API query to find roads near point
            overpass_url = "https://overpass-api.de/api/interpreter"
            overpass_query = f"""
            [out:json];
            way["highway"](around:{radius},{lat},{lon});
            out body;
            """
            
            response = requests.post(overpass_url, data={"data": overpass_query}, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                elements = data.get("elements", [])
                
                if elements:
                    # Sort by distance (if we could calculate it) or just take first
                    nearest_road = elements[0]
                    tags = nearest_road.get("tags", {})
                    
                    result = {
                        "highway": tags.get("highway", "unknown"),
                        "name": tags.get("name", "unnamed"),
                        "is_nearest_match": True,
                        "source": "overpass"
                    }
                    
                    print(f"DEBUG: ✓ Found nearest road ({result['highway']}): {result['name']}")
                    return result
                
                print(f"DEBUG: No roads found within {radius}m")
                return {}
            
            print(f"DEBUG: Overpass API error {response.status_code}")
            return {}
            
        except Exception as e:
            print(f"ERROR: Exception finding nearest road: {str(e)}")
            return {}