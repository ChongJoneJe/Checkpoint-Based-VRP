import numpy as np
import openrouteservice
from openrouteservice.distance_matrix import distance_matrix
import requests
import json
import os
import sqlite3
from pathlib import Path

class GeoDBSCAN:
    """
    Enhanced DBSCAN algorithm with geocoding and location database integration
    Works with SQLAlchemy models
    """
    def __init__(self, eps=0.5, min_samples=2, api_key=None, distance_metric='distance', 
                 db_path='locations.db'):
        """
        Initialize the GeoDBSCAN algorithm with location database support.
        
        Args:
            eps (float): The maximum distance in kilometers
            min_samples (int): The minimum number of samples to form a cluster
            api_key (str): OpenRouteService API key
            distance_metric (str): 'distance' or 'duration'
            db_path (str): Path to the SQLite database file
        """
        self.eps = eps * 1000  # Convert to meters for OpenRouteService
        self.min_samples = min_samples
        self.labels_ = None
        self.n_clusters_ = 0
        self.core_sample_indices_ = []
        self.intersection_points = {}
        self.api_key = api_key
        self.distance_metric = distance_metric
        self.db_path = db_path
        
        # Initialize the ORS client if API key is provided
        if self.api_key:
            self.client = openrouteservice.Client(key=self.api_key)
        else:
            self.client = None
    
    def geocode_location(self, lat, lon):
        """
        Geocode a location to get address components using Nominatim
        
        Args:
            lat (float): Latitude
            lon (float): Longitude
            
        Returns:
            dict: Address components or None if geocoding failed
        """
        try:
            # Use Nominatim API
            response = requests.get(
                f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json&zoom=18&addressdetails=1",
                headers={"User-Agent": "python-clustering-app"}
            )
            
            if response.status_code == 200:
                data = response.json()
                address = data.get('address', {})
                
                result = {
                    'street': address.get('road') or address.get('pedestrian') or address.get('footway') or '',
                    'neighborhood': address.get('neighbourhood') or address.get('suburb') or '',
                    'town': address.get('town') or address.get('village') or '',
                    'city': address.get('city') or '',
                    'postcode': address.get('postcode') or '',
                    'country': address.get('country') or ''
                }
                
                return result
            
            return None
            
        except Exception as e:
            print(f"Geocoding error: {str(e)}")
            return None
    
    def add_location_to_db(self, lat, lon, address=None):
        """
        Add a location to the database with its geocoded information
        
        Args:
            lat (float): Latitude
            lon (float): Longitude
            address (dict, optional): Pre-geocoded address components
            
        Returns:
            int: Location ID in the database
        """
        if address is None:
            address = self.geocode_location(lat, lon)
            
        if address:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            # Check if this location already exists
            c.execute('''
                SELECT id FROM locations
                WHERE lat = ? AND lon = ?
            ''', (lat, lon))
            
            result = c.fetchone()
            
            if result:
                location_id = result[0]
            else:
                # Insert new location
                c.execute('''
                    INSERT INTO locations (lat, lon, street, neighborhood, town, city, postcode, country)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    lat, lon, 
                    address.get('street', ''),
                    address.get('neighborhood', ''),
                    address.get('town', ''),
                    address.get('city', ''),
                    address.get('postcode', ''),
                    address.get('country', '')
                ))
                
                location_id = c.lastrowid
                
            conn.commit()
            conn.close()
            
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
            
            # Identify potential intersection points (simplified)
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
                        'lon': coords[i-1][0],
                        'lat': coords[i-1][1],
                        'position': i-1
                    })
                    
                last_bearing = bearing
            
            return intersections
            
        except Exception as e:
            print(f"Error identifying intersections: {str(e)}")
            return []
    
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
        
        for cluster_idx in range(n_clusters):
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
        Add a location to the database with smart clustering based on street/neighborhood
        and route intersection analysis
        
        Args:
            lat (float): Latitude
            lon (float): Longitude
            warehouse_lat (float): Warehouse latitude
            warehouse_lon (float): Warehouse longitude
            
        Returns:
            tuple: (location_id, cluster_id, is_new_cluster)
        """
        # First geocode the location
        address = self.geocode_location(lat, lon)
        if not address:
            return None, None, False
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        try:
            # Start transaction
            conn.execute("BEGIN")
            
            # Check if this location already exists
            c.execute('''
                SELECT id FROM locations
                WHERE ABS(lat - ?) < 0.0001 AND ABS(lon - ?) < 0.0001
            ''', (lat, lon))
            
            result = c.fetchone()
            
            if result:
                # Location already exists, get its cluster
                location_id = result[0]
                
                c.execute('''
                    SELECT cluster_id FROM location_clusters
                    WHERE location_id = ?
                ''', (location_id,))
                
                cluster_result = c.fetchone()
                cluster_id = cluster_result[0] if cluster_result else None
                
                conn.commit()
                return location_id, cluster_id, False
            
            # Location doesn't exist, add it
            c.execute('''
                INSERT INTO locations (lat, lon, street, neighborhood, town, city, postcode, country)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                lat, lon, 
                address.get('street', ''),
                address.get('neighborhood', ''),
                address.get('town', ''),
                address.get('city', ''),
                address.get('postcode', ''),
                address.get('country', '')
            ))
            
            location_id = c.lastrowid
            
            # Find intersections for this new location
            new_location_intersections = self.identify_intersections_for_location(
                lat, lon, warehouse_lat, warehouse_lon
            )
            
            # Store the new location's route intersections
            new_intersection_ids = []
            for intersection in new_location_intersections:
                # Check if intersection already exists
                c.execute('''
                    SELECT id FROM intersections 
                    WHERE ABS(lat - ?) < 0.0001 AND ABS(lon - ?) < 0.0001
                ''', (intersection['lat'], intersection['lon']))
                
                result = c.fetchone()
                
                if result:
                    intersection_id = result[0]
                else:
                    c.execute(
                        "INSERT INTO intersections (lat, lon) VALUES (?, ?)",
                        (intersection['lat'], intersection['lon'])
                    )
                    intersection_id = c.lastrowid
                
                # Link intersection to location
                c.execute(
                    "INSERT INTO location_intersections (location_id, intersection_id, position) VALUES (?, ?, ?)",
                    (location_id, intersection_id, intersection['position'])
                )
                
                new_intersection_ids.append(intersection_id)
            
            # STEP 1: Find existing locations with the same street or neighborhood
            street = address.get('street', '')
            neighborhood = address.get('neighborhood', '')
            
            matching_query = '''
                SELECT l.id, lc.cluster_id 
                FROM locations l
                LEFT JOIN location_clusters lc ON l.id = lc.location_id
                WHERE ((l.street = ? AND l.street != '') OR (l.neighborhood = ? AND l.neighborhood != ''))
                    AND l.id != ?
            '''
            
            c.execute(matching_query, (street, neighborhood, location_id))
            matching_locations = c.fetchall()
            
            cluster_id = None
            is_new_cluster = False
            
            if matching_locations:
                # We have found locations in the same street/neighborhood
                
                best_matching_location_id = None
                best_matching_cluster_id = None
                best_intersection_match_count = 0
                
                # STEP 2: For each matching location, compare routes
                for match_id, match_cluster_id in matching_locations:
                    # Get this location's route intersections
                    c.execute('''
                        SELECT intersection_id 
                        FROM location_intersections
                        WHERE location_id = ?
                        ORDER BY position
                    ''', (match_id,))
                    
                    match_intersection_ids = [row[0] for row in c.fetchall()]
                    
                    # Count how many intersections match with our new location
                    common_intersections = set(new_intersection_ids).intersection(set(match_intersection_ids))
                    match_count = len(common_intersections)
                    
                    # If this is the best match so far, save it
                    if match_count > best_intersection_match_count:
                        best_intersection_match_count = match_count
                        best_matching_location_id = match_id
                        best_matching_cluster_id = match_cluster_id
                
                # STEP 3: Decide which cluster to use based on route comparison
                if best_matching_cluster_id is not None:
                    # Use the existing cluster with the best route match
                    cluster_id = best_matching_cluster_id
                    
                    # Link location to this cluster
                    c.execute(
                        "INSERT INTO location_clusters (location_id, cluster_id) VALUES (?, ?)",
                        (location_id, cluster_id)
                    )
                else:
                    # No good cluster match found, create a new cluster
                    is_new_cluster = True
                    
                    # Generate cluster name based on location address
                    cluster_name = neighborhood if neighborhood else (street if street else "Cluster")
                    
                    c.execute(
                        "INSERT INTO clusters (name, centroid_lat, centroid_lon) VALUES (?, ?, ?)",
                        (cluster_name, lat, lon)
                    )
                    
                    cluster_id = c.lastrowid
                    
                    # Link location to the new cluster
                    c.execute(
                        "INSERT INTO location_clusters (location_id, cluster_id) VALUES (?, ?)",
                        (location_id, cluster_id)
                    )
            else:
                # No matching locations found, create a new cluster
                is_new_cluster = True
                
                # Generate cluster name based on location address
                cluster_name = neighborhood if neighborhood else (street if street else "Cluster")
                
                c.execute(
                    "INSERT INTO clusters (name, centroid_lat, centroid_lon) VALUES (?, ?, ?)",
                    (cluster_name, lat, lon)
                )
                
                cluster_id = c.lastrowid
                
                # Link location to the new cluster
                c.execute(
                    "INSERT INTO location_clusters (location_id, cluster_id) VALUES (?, ?)",
                    (location_id, cluster_id)
                )
            
            # Commit all changes
            conn.commit()
            
            return location_id, cluster_id, is_new_cluster
            
        except Exception as e:
            conn.rollback()
            print(f"Error adding location with smart clustering: {str(e)}")
            return None, None, False
            
        finally:
            conn.close()
    
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