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
        
        # Initialize the ORS client if API key is provided
        if self.api_key:
            self.client = openrouteservice.Client(key=self.api_key)
        else:
            self.client = None
    
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
        """
        Find transitions between road types on the route from location to warehouse
        to identify potential security checkpoints
        
        Args:
            lat (float): Location latitude
            lon (float): Location longitude
            warehouse_lat (float): Warehouse latitude
            warehouse_lon (float): Warehouse longitude
            
        Returns:
            list: List of transition points with road type information
        """
        if self.client is None:
            print("No OpenRouteService client available - cannot identify road transitions")
            return []
            
        try:
            # Get detailed directions from location to warehouse
            coords = [[lon, lat], [warehouse_lon, warehouse_lat]]
            
            # Request detailed route info including road types
            route = self.client.directions(
                coordinates=coords,
                profile='driving-car',
                format='geojson',
                extra_info=['waycategory', 'waytype'],  # Include road category info
                geometry_simplify=False  # Keep full detail
            )
            
            # Extract segments with road classification
            waypoints = route['features'][0]['geometry']['coordinates']
            segments = route['features'][0]['properties']['segments'][0]['steps']
            
            transitions = []
            current_road_type = None
            
            for step in segments:
                # Extract road type from step info
                # OpenRouteService classifies roads similarly to OSM
                road_type = self._get_road_class(step)
                
                # If road type changes, this is a transition point
                if current_road_type and road_type != current_road_type:
                    # This is a transition point - get coordinates
                    transition_point_idx = step['way_points'][0]
                    if 0 <= transition_point_idx < len(waypoints):
                        point = waypoints[transition_point_idx]
                        
                        # Record transition (residential→tertiary or tertiary→secondary are important)
                        transitions.append({
                            'lat': point[1],  # Convert from [lon, lat] to [lat, lon]
                            'lon': point[0],
                            'from_type': current_road_type,
                            'to_type': road_type,
                            'position': transition_point_idx,
                            'is_potential_checkpoint': self._is_security_checkpoint_transition(current_road_type, road_type)
                        })
                        
                        print(f"Road transition: {current_road_type} → {road_type} at [{point[1]}, {point[0]}]")
                
                current_road_type = road_type
            
            # Find most likely security checkpoint from all transitions
            security_checkpoints = [t for t in transitions if t.get('is_potential_checkpoint')]
            
            # Closest transition to origin is most likely the security checkpoint
            if security_checkpoints:
                print(f"Found {len(security_checkpoints)} potential security checkpoints")
                # Sort by position (earlier in route = closer to origin = more likely checkpoint)
                security_checkpoints.sort(key=lambda x: x['position'])
                return security_checkpoints
            
            return transitions
            
        except Exception as e:
            print(f"Error identifying road transitions: {str(e)}")
            return []

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

    def add_location_with_smart_clustering(self, lat, lon, warehouse_lat, warehouse_lon):
        """
        Add a location to the database with smart clustering based on street pattern matching
        
        Args:
            lat (float): Latitude
            lon (float): Longitude
            warehouse_lat (float): Warehouse latitude
            warehouse_lon (float): Warehouse longitude
            
        Returns:
            tuple: (location_id, cluster_id, is_new_cluster, checkpoint)
        """
        from repositories.location_repository import LocationRepository
        from repositories.cluster_repository import ClusterRepository
        
        # Geocode the location to get address components
        address = self.geocode_location(lat, lon)
        if not address:
            print(f"Warning: Could not geocode location ({lat}, {lon}) - creating without address data")
            address = {'street': '', 'neighborhood': '', 'town': '', 'city': '', 'postcode': '', 'country': ''}
        
        try:
            # Check if location exists
            existing_loc = LocationRepository.find_by_coordinates(lat, lon)
            
            if existing_loc:
                # Existing location logic
                location_id = existing_loc['id']
                LocationRepository.update_address(location_id, address)
                
                cluster_info = execute_read(
                    "SELECT cluster_id FROM location_clusters WHERE location_id = ?", 
                    (location_id,), 
                    one=True
                )
                
                return location_id, cluster_info['cluster_id'] if cluster_info else None, False, None
                
            # Insert new location
            location_id = LocationRepository.insert(lat, lon, address)
            
            # Get street info for clustering
            street = address.get('street', '')
            
            # Extract development pattern from street name - key for smarter clustering
            development_pattern = self._extract_development_pattern(street) if street else None
            
            matches = []
            match_type = None
            
            # STEP 1: First try exact street match (highest priority)
            if street:
                street_matches = LocationRepository.find_matching_street(street, location_id)
                if street_matches:
                    matches.extend(street_matches)
                    match_type = "exact_street"
                    print(f"Found {len(street_matches)} locations with exact street match: {street}")
            
            # STEP 2: If no exact street match, look for development pattern match
            if not matches and development_pattern:
                pattern_matches = LocationRepository.find_pattern_matches(development_pattern, location_id)
                if pattern_matches:
                    matches.extend(pattern_matches)
                    match_type = "development_pattern"
                    print(f"Found {len(pattern_matches)} locations with development pattern match: {development_pattern}")
            
            # Clustering logic
            cluster_id = None
            is_new_cluster = False
            
            if matches:
                # Use the first match that has a cluster assigned
                for match in matches:
                    if match['cluster_id']:
                        cluster_id = match['cluster_id']
                        print(f"Assigning to existing cluster: {cluster_id} based on {match_type} match")
                        break
                
                # If no match has a cluster, create one for all matches
                if not cluster_id:
                    # Create a new cluster with pattern-based naming
                    is_new_cluster = True
                    
                    # Generate cluster name based on the development pattern
                    cluster_name = development_pattern or self._extract_street_pattern(street)
                    
                    cluster_id = ClusterRepository.create(cluster_name, lat, lon)
                    print(f"Created new cluster: {cluster_id} ({cluster_name}) for {match_type} match")
                    
                    # Assign all matches to this cluster
                    for match in matches:
                        ClusterRepository.add_location_to_cluster(match['id'], cluster_id)
            else:
                # No matches - create a new cluster with street-based naming
                is_new_cluster = True
                
                # Determine best name for new cluster
                if development_pattern:
                    cluster_name = development_pattern
                elif street:
                    cluster_name = self._extract_street_pattern(street)
                else:
                    cluster_name = "Unknown Location"
                
                cluster_id = ClusterRepository.create(cluster_name, lat, lon)
                print(f"Created new cluster: {cluster_id} ({cluster_name}) - no matches")
            
            # Add the location to its cluster
            if cluster_id:
                ClusterRepository.add_location_to_cluster(location_id, cluster_id)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error in smart clustering: {str(e)}")
            return None, None, False, None

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

    def _extract_development_pattern(self, street):
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
        
        # If no specific pattern matches, take the first 2 words
        words = street.split()
        if len(words) >= 2:
            return ' '.join(words[:2]).title()
        elif len(words) == 1:
            return words[0].title()
            
        return street.title()

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