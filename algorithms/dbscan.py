import numpy as np
import openrouteservice
from openrouteservice.distance_matrix import distance_matrix
import requests
import random
import json
import os
import time
import re
from utils.database import execute_read, execute_write
from algorithms.network_analyzer import NetworkAnalyzer

class GeoDBSCAN:
    """Enhanced DBSCAN algorithm with geocoding and checkpoint detection"""
    
    def __init__(self, eps=0.5, min_samples=2, api_key=None, distance_metric='distance'):
        """Initialize the algorithm with OpenRouteService integration"""
        self.eps = eps * 1000  # Convert to meters
        self.min_samples = min_samples
        self.api_key = api_key
        self.distance_metric = distance_metric
        self.client = None
        
        # Initialize OpenRouteService client
        if self.api_key:
            try:
                self.client = openrouteservice.Client(key=self.api_key)
                print("DEBUG: OpenRouteService client initialized successfully")
            except Exception as e:
                print(f"Error initializing OpenRouteService client: {str(e)}")
        else:
            print("No API key provided for OpenRouteService")
        
        # Initialize NetworkAnalyzer for checkpoint detection
        self.network_analyzer = NetworkAnalyzer()

    def geocode_location(self, lat, lon):
        """
        Geocode a location to get address components using Nominatim with one attempt per zoom level
        """
        # Try each zoom level only once, in order from most precise to least precise
        zoom_levels = [18, 17, 16, 15]
        
        try:
            print(f"DEBUG: Starting geocoding for location ({lat}, {lon})")
            
            for zoom in zoom_levels:
                print(f"DEBUG: Trying zoom level {zoom}")
                
                # Add a small random jitter to avoid rate limiting issues with cached results
                jitter = 0.00001
                jittered_lat = lat + random.uniform(-jitter, jitter)
                jittered_lon = lon + random.uniform(-jitter, jitter)
                
                response = requests.get(
                    f"https://nominatim.openstreetmap.org/reverse?lat={jittered_lat}&lon={jittered_lon}&format=json&zoom={zoom}&addressdetails=1",
                    headers={"User-Agent": "python-clustering-app"},
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    address = data.get('address', {})
                    
                    # Check if we have street information
                    street = address.get('road') or address.get('pedestrian') or address.get('footway')
                    if street:
                        print(f"DEBUG: Found street '{street}' with zoom {zoom}")
                        
                        # Extract development pattern from street
                        development = self._extract_development_pattern(street, address.get('neighbourhood', ''))
                        formatted_street = street  # Use proper street formatting
                        
                        result = {
                            'street': formatted_street,
                            'neighborhood': address.get('neighbourhood', ''),
                            'development': development,  
                            'city': address.get('city', ''),
                            'postcode': address.get('postcode', ''),
                            'country': address.get('country', '')
                        }
                        
                        # Clean up any stray letters in street names
                        result = self._cleanup_geocoded_address(result)
                        return result
                    print(f"DEBUG: No street found at zoom level {zoom}")
                
                elif response.status_code == 429:  # Too Many Requests
                    # Wait longer because we're rate limited
                    print(f"DEBUG: Rate limited, waiting 1 second...")
                    time.sleep(1)
                    # Skip to next zoom level
                
                # Sleep briefly between zoom levels to avoid rate limiting
                time.sleep(0.25)
                
        except Exception as e:
            print(f"DEBUG: Error in geocoding: {type(e).__name__}: {str(e)}")
        
        print(f"DEBUG: Geocoding failed for location ({lat}, {lon})")
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
                   (lat, lon, street, neighborhood, development, city, postcode, country)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    lat, lon, 
                    address.get('street', ''),
                    address.get('neighborhood', ''),
                    address.get('development', ''),  
                    address.get('city', ''),
                    address.get('postcode', ''),
                    address.get('country', '')
                )
            )
            
            return location_id
        
        return None

    def add_location_with_smart_clustering(self, lat, lon, warehouse_lat, warehouse_lon):
        """
        Add a location with improved clustering logic and fallbacks
        """
        from repositories.location_repository import LocationRepository
        from repositories.cluster_repository import ClusterRepository
        
        print(f"DEBUG: ===== START CLUSTERING FOR {lat}, {lon} =====")
        
        print(f"DEBUG: Starting smart clustering for location ({lat}, {lon})")
        
        try:
            # Check if location already exists with user-provided address
            existing_loc = LocationRepository.find_by_coordinates(lat, lon)
            
            if existing_loc and existing_loc.get('street'):
                print(f"DEBUG: Found existing location with address: {existing_loc['street']}")
                # Use the existing address - respect user input
                address = {
                    'street': existing_loc.get('street', ''),
                    'neighborhood': existing_loc.get('neighborhood', ''),
                    'development': existing_loc.get('development', ''), 
                    'city': existing_loc.get('city', ''),
                    'postcode': existing_loc.get('postcode', ''),
                    'country': existing_loc.get('country', '')
                }
                location_id = existing_loc['id']
                
                # Check if it's already assigned to a cluster
                cluster_info = execute_read(
                    "SELECT cluster_id FROM location_clusters WHERE location_id = ?", 
                    (location_id,), 
                    one=True
                )
                if cluster_info and cluster_info['cluster_id']:
                    print(f"DEBUG: Location already in cluster: {cluster_info['cluster_id']}")
                    return location_id, cluster_info['cluster_id'], False
            else:
                # Geocode the location only if we don't have user-provided data
                existing_address = execute_read(
                    "SELECT street, neighborhood, development, city, postcode, country FROM locations WHERE lat = ? AND lon = ?",
                    (lat, lon),
                    one=True
                )

                if existing_address and existing_address.get('street'):
                    # Use existing geocoded address from database
                    address = {
                        'street': existing_address.get('street', ''),
                        'neighborhood': existing_address.get('neighborhood', ''),
                        'development': existing_address.get('development', ''),  
                        'city': existing_address.get('city', ''),
                        'postcode': existing_address.get('postcode', ''),
                        'country': existing_address.get('country', '')
                    }
                    print(f"DEBUG: Using existing geocoded address from database")
                else:
                    address = self.geocode_location(lat, lon)
                
                if not address:
                    print(f"WARNING: Could not geocode location ({lat}, {lon}) - creating without address data")
                    address = {'street': '', 'neighborhood': '', 'development': '', 'city': '', 'postcode': '', 'country': ''}
                else:
                    print(f"DEBUG: Address components from geocoding: {address}")
                
                # Continue with existing location check and insertion
                if existing_loc:
                    location_id = existing_loc['id']
                    LocationRepository.update_address(location_id, address)
                else:
                    location_id = LocationRepository.insert(lat, lon, address)
                    print(f"DEBUG: Inserted new location with ID: {location_id}")
            
            # Check if warehouse coordinates are provided
            if warehouse_lat is None or warehouse_lon is None:
                print(f"DEBUG: No warehouse found for clustering")
                return location_id, None, False

            # Ensure warehouse coordinates are converted to float when comparing
            if warehouse_lat and warehouse_lon:
                warehouse_lat = float(warehouse_lat)
                warehouse_lon = float(warehouse_lon)
                
                if abs(lat - warehouse_lat) < 0.0001 and abs(lon - warehouse_lon) < 0.0001:
                    print(f"DEBUG: Location ({lat}, {lon}) is the warehouse - excluding from clustering")
                    return location_id, None, False
            
            # Get the street from address and clean it
            street = address.get('street', '').strip()
            neighborhood = address.get('neighborhood', '')
            
            if not street:
                print(f"DEBUG: No street information for location {location_id}, skipping clustering")
                return location_id, None, False
            
            # Extract development pattern
            development = self._extract_development_pattern(street, neighborhood)
            
            # Get street stem (without last character for pattern matching)
            street_stem = self._get_street_stem(self._normalize_street_name(street))
            
            print(f"INPUT LOCATION DETAILS:")
            print(f"  - Street: '{street}'")
            print(f"  - Street Stem: '{street_stem}'")
            print(f"  - Development: '{development}'")
            print(f"  - Neighborhood: '{neighborhood}'")
            
            # Initialize cluster variables
            cluster_id = None
            is_new_cluster = False
            
            # Level 1: Try exact street match first
            exact_matches = execute_read(
                """
                SELECT lc.cluster_id, l.street, l.development, c.name as cluster_name 
                FROM locations l
                JOIN location_clusters lc ON l.id = lc.location_id
                JOIN clusters c ON lc.cluster_id = c.id
                WHERE LOWER(l.street) = LOWER(?) AND l.street != ''
                LIMIT 1
                """,
                (street,)
            )
            
            if exact_matches:
                cluster_id = exact_matches[0]['cluster_id']
                print(f"Level 1 Match: Exact street match with '{exact_matches[0]['street']}'")
                # Assign to this cluster
                execute_write(
                    "INSERT OR REPLACE INTO location_clusters (location_id, cluster_id) VALUES (?, ?)",
                    (location_id, cluster_id)
                )
                return location_id, cluster_id, False
            
            # Level 2: Try street stem match for Malaysian address pattern
            if street_stem != self._normalize_street_name(street):  # Only if stem differs
                stem_matches = execute_read(
                    """
                    SELECT l.id, l.street, lc.cluster_id, c.name as cluster_name
                    FROM locations l
                    JOIN location_clusters lc ON l.id = lc.location_id
                    JOIN clusters c ON lc.cluster_id = c.id
                    WHERE l.street IS NOT NULL AND l.street != ''
                    AND l.id != ?
                    LIMIT 50
                    """,
                    (location_id,)
                )
                
                if stem_matches:
                    for loc in stem_matches:
                        other_street = loc['street']
                        other_stem = self._get_street_stem(self._normalize_street_name(other_street))
                        
                        # Only match stems if they both follow the pattern and match
                        if (other_stem != self._normalize_street_name(other_street) and 
                            other_stem == street_stem):
                            cluster_id = loc['cluster_id']
                            print(f"Level 2 Match: Street stem match '{street_stem}' with '{other_street}'")
                            # Assign to this cluster
                            execute_write(
                                "INSERT OR REPLACE INTO location_clusters (location_id, cluster_id) VALUES (?, ?)",
                                (location_id, cluster_id)
                            )
                            return location_id, cluster_id, False
            
            # Level 3: Try any other matching streets via component comparison
            matching_locations = execute_read(
                """
                SELECT l.id, l.street, lc.cluster_id, c.name as cluster_name
                FROM locations l
                JOIN location_clusters lc ON l.id = lc.location_id
                JOIN clusters c ON lc.cluster_id = c.id
                WHERE l.street IS NOT NULL AND l.street != ''
                AND l.id != ?
                LIMIT 50
                """,
                (location_id,)
            )
            
            if matching_locations:
                for loc in matching_locations:
                    if self._compare_street_paths(street, loc['street']):
                        cluster_id = loc['cluster_id']
                        print(f"Level 3 Match: Component-based match with '{loc['street']}'")
                        # Assign to this cluster
                        execute_write(
                            "INSERT OR REPLACE INTO location_clusters (location_id, cluster_id) VALUES (?, ?)",
                            (location_id, cluster_id)
                        )
                        return location_id, cluster_id, False
            
            # Level 4: Try development pattern match (if available)
            if development:
                dev_matches = execute_read(
                    """
                    SELECT DISTINCT lc.cluster_id, c.name
                    FROM locations l
                    JOIN location_clusters lc ON l.id = lc.location_id
                    JOIN clusters c ON lc.cluster_id = c.id
                    WHERE LOWER(l.development) = LOWER(?)
                    LIMIT 1
                    """,
                    (development,)
                )
                
                if dev_matches:
                    cluster_id = dev_matches[0]['cluster_id']
                    print(f"Level 4 Match: Development match '{development}' to cluster '{dev_matches[0]['name']}'")
                    execute_write(
                        "INSERT INTO location_clusters (location_id, cluster_id) VALUES (?, ?)",
                        (location_id, cluster_id)
                    )
                    return location_id, cluster_id, False
            
            # Level 5: Try neighborhood match (if available)
            if neighborhood:
                neighborhood_matches = execute_read(
                    """
                    SELECT DISTINCT lc.cluster_id, c.name
                    FROM locations l
                    JOIN location_clusters lc ON l.id = lc.location_id
                    JOIN clusters c ON lc.cluster_id = c.id
                    WHERE LOWER(l.neighborhood) = LOWER(?) AND l.neighborhood != ''
                    LIMIT 1
                    """,
                    (neighborhood,)
                )
                
                if neighborhood_matches:
                    cluster_id = neighborhood_matches[0]['cluster_id']
                    print(f"Level 5 Match: Neighborhood match '{neighborhood}' to cluster '{neighborhood_matches[0]['name']}'")
                    execute_write(
                        "INSERT INTO location_clusters (location_id, cluster_id) VALUES (?, ?)",
                        (location_id, cluster_id)
                    )
                    return location_id, cluster_id, False
            
            # Level 6: Last resort - proximity matching
            print(f"DEBUG: No logical matches found, trying proximity clustering")
            print(f"DEBUG: Starting proximity-based clustering")

            # Find nearby clusters first
            nearby_clusters = execute_read(
                """
                SELECT c.id, c.name, c.centroid_lat, c.centroid_lon,
                       SQRT(POWER(c.centroid_lat - ?, 2) + POWER(c.centroid_lon - ?, 2)) AS distance
                FROM clusters c
                ORDER BY distance ASC
                LIMIT 3
                """,
                (lat, lon)
            )

            for cluster in nearby_clusters:
                cluster_id = cluster['id']
                distance_km = cluster['distance'] * 111  # Rough conversion from degrees to km

                print(f"DEBUG: Checking proximity to cluster {cluster['name']} (ID: {cluster_id}, distance: {distance_km:.2f} km)")

                # Check if any locations in this cluster are within a close proximity
                very_close = execute_read(
                    """
                    SELECT COUNT(*) as count
                    FROM locations l
                    JOIN location_clusters lc ON l.id = lc.location_id
                    WHERE lc.cluster_id = ? AND
                    (l.lat BETWEEN ? AND ?) AND 
                    (l.lon BETWEEN ? AND ?)
                    """,
                    (
                        cluster_id,
                        lat - 0.001, lat + 0.001,  # About 100m radius
                        lon - 0.001, lon + 0.001   # Properly formatted parameters
                    ),
                    one=True
                )

                if very_close and very_close['count'] > 0:
                    print(f"DEBUG: Found {very_close['count']} locations in close proximity to cluster {cluster_id}")

                    # Assign to this cluster based on proximity
                    execute_write(
                        "INSERT OR REPLACE INTO location_clusters (location_id, cluster_id) VALUES (?, ?)",
                        (location_id, cluster_id)
                    )
                    return location_id, cluster_id, False

            # If no match found after all levels, create a new cluster
            print(f"DEBUG: No matching cluster found, creating new cluster")
            
            # Extract components for cluster naming
            components = self._extract_street_parts(self._normalize_street_name(street))
            section = components['section']
            subsection = components['subsection']
            
            # Create a more appropriate cluster name
            if section and subsection:
                # Remove the last character for cluster name if it follows the pattern
                clean_subsection = re.sub(r'(\d+)[a-zA-Z]$', r'\1', subsection)
                
                if development:
                    cluster_name = f"{development} {section}/{clean_subsection}"
                else:
                    cluster_name = f"{section}/{clean_subsection}"
            elif development:
                cluster_name = development
            elif neighborhood:
                cluster_name = neighborhood.title()
            else:
                # Clean up street name for cluster
                clean_street = re.sub(r'([0-9]+)[a-zA-Z]$', r'\1', street)
                cluster_name = clean_street.title()
            
            print(f"DEBUG: Creating new cluster: {cluster_name}")
            
            # Create a new cluster
            cluster_name = cluster_name.title()
            cluster_id = execute_write(
                "INSERT INTO clusters (name, centroid_lat, centroid_lon) VALUES (?, ?, ?)",
                (cluster_name, lat, lon)
            )
            
            # Add location to new cluster
            execute_write(
                "INSERT INTO location_clusters (location_id, cluster_id) VALUES (?, ?)",
                (location_id, cluster_id)
            )
            
            print(f"DEBUG: Created new cluster '{cluster_name}' (ID: {cluster_id}) for location {location_id}")
            
            print(f"========== CLUSTERING PROCESS END ==========\n\n")
            return location_id, cluster_id, True

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"ERROR: Error in smart clustering: {str(e)}")
            print(f"========== CLUSTERING PROCESS END (ERROR) ==========\n\n")
            return None, None, False

    def debug_clustering(self, location_id=None):
        """
        Debug clustering for all locations or a specific location
        """
        print("\n\n====== CLUSTERING DEBUG REPORT ======")

        # Query to get all locations
        if location_id:
            locations = execute_read(
                """
                SELECT id, lat, lon, street, neighborhood, development 
                FROM locations 
                WHERE id = ?
                """,
                (location_id,)
            )
        else:
            locations = execute_read(
                """
                SELECT id, lat, lon, street, neighborhood, development 
                FROM locations 
                WHERE street IS NOT NULL AND street != ''
                ORDER BY id DESC
                LIMIT 20
                """
            )

        print(f"Debugging {len(locations)} location(s)")

        for loc in locations:
            loc_id = loc['id']
            lat = loc['lat']
            lon = loc['lon']
            street = loc['street']
            
            print(f"\n--- LOCATION {loc_id}: {street} ({lat}, {lon}) ---")
            
            # Check if already in a cluster
            cluster_info = execute_read(
                """
                SELECT lc.cluster_id, c.name 
                FROM location_clusters lc
                JOIN clusters c ON lc.cluster_id = c.id
                WHERE lc.location_id = ?
                """,
                (loc_id,),
                one=True
            )
            
            if cluster_info:
                print(f"✓ Already assigned to cluster: {cluster_info['name']} (ID: {cluster_info['cluster_id']})")
                continue
            
            # Normalize the street name
            normalized = self._normalize_street_name(street)
            print(f"Normalized street name: {normalized}")
            
            # Get street stem
            street_stem = self._get_street_stem(normalized)
            print(f"Street stem: {street_stem}")
            
            # Extract components
            components = self._extract_street_parts(normalized)
            print(f"Street components: {components}")
            
            # Test exact match
            exact_matches = execute_read(
                """
                SELECT l.id, l.street, lc.cluster_id, c.name
                FROM locations l
                JOIN location_clusters lc ON l.id = lc.location_id
                JOIN clusters c ON lc.cluster_id = c.id
                WHERE LOWER(l.street) = LOWER(?) AND l.id != ?
                LIMIT 5
                """,
                (street, loc_id)
            )
            
            if exact_matches:
                print(f"✓ Found {len(exact_matches)} exact matches:")
                for match in exact_matches:
                    print(f"  - '{match['street']}' in cluster {match['name']} (ID: {match['cluster_id']})")
            else:
                print("✗ No exact matches found")
            
            # Test stem match
            if street_stem != normalized:
                stem_matches = []
                
                # Test against all locations in clusters
                all_clustered = execute_read(
                    """
                    SELECT l.id, l.street, lc.cluster_id, c.name
                    FROM locations l
                    JOIN location_clusters lc ON l.id = lc.location_id
                    JOIN clusters c ON lc.cluster_id = c.id
                    WHERE l.id != ?
                    LIMIT 50
                    """,
                    (loc_id,)
                )
                
                for other in all_clustered:
                    other_street = other['street']
                    other_normalized = self._normalize_street_name(other_street)
                    other_stem = self._get_street_stem(other_normalized)
                    
                    if other_stem != other_normalized and other_stem == street_stem:
                        stem_matches.append(other)
                
                if stem_matches:
                    print(f"✓ Found {len(stem_matches)} stem matches:")
                    for match in stem_matches:
                        print(f"  - '{match['street']}' (stem: {self._get_street_stem(self._normalize_street_name(match['street']))}) in cluster {match['name']}")
                else:
                    print("✗ No stem matches found")
            else:
                print("✗ Location doesn't follow Malaysian address pattern (no letter suffix)")
            
            # Test component-based matches
            component_matches = []
            all_clustered = execute_read(
                """
                SELECT l.id, l.street, lc.cluster_id, c.name
                FROM locations l
                JOIN location_clusters lc ON l.id = lc.location_id
                JOIN clusters c ON lc.cluster_id = c.id
                WHERE l.id != ?
                LIMIT 50
                """,
                (loc_id,)
            )
            
            for other in all_clustered:
                if self._compare_street_paths(street, other['street']):
                    component_matches.append(other)
            
            if component_matches:
                print(f"✓ Found {len(component_matches)} component-based matches:")
                for match in component_matches:
                    print(f"  - '{match['street']}' in cluster {match['name']}")
            else:
                print("✗ No component-based matches found")
            
            # Test development matches
            if loc['development']:
                dev_matches = execute_read(
                    """
                    SELECT COUNT(DISTINCT c.id) as count
                    FROM locations l
                    JOIN location_clusters lc ON l.id = lc.location_id
                    JOIN clusters c ON lc.cluster_id = c.id
                    WHERE LOWER(l.development) = LOWER(?) AND l.id != ?
                    """,
                    (loc['development'], loc_id),
                    one=True
                )
                
                if dev_matches and dev_matches['count'] > 0:
                    print(f"✓ Found development matches: {dev_matches['count']} clusters with development '{loc['development']}'")
                else:
                    print(f"✗ No development matches found for '{loc['development']}'")
            else:
                print("✗ No development name available")
            
            # Test neighborhood matches
            if loc['neighborhood']:
                neighborhood_matches = execute_read(
                    """
                    SELECT COUNT(DISTINCT c.id) as count
                    FROM locations l
                    JOIN location_clusters lc ON l.id = lc.location_id
                    JOIN clusters c ON lc.cluster_id = c.id
                    WHERE LOWER(l.neighborhood) = LOWER(?) AND l.id != ?
                    """,
                    (loc['neighborhood'], loc_id),
                    one=True
                )
                
                if neighborhood_matches and neighborhood_matches['count'] > 0:
                    print(f"✓ Found neighborhood matches: {neighborhood_matches['count']} clusters with neighborhood '{loc['neighborhood']}'")
                else:
                    print(f"✗ No neighborhood matches found for '{loc['neighborhood']}'")
            else:
                print("✗ No neighborhood name available")
        
        print("\n====== END CLUSTERING DEBUG REPORT ======\n")

    def _normalize_street_for_clustering(self, street):
        """
        Normalize a street name for clustering by removing the last character identifier after '/'
        Example: 'jalan setia nusantara u13/22t' -> 'jalan setia nusantara u13/22'
        
        Args:
            cluster_id: ID of the cluster
            
        Returns:
            str: Normalized street name
        """
        if not street:
            return ""
        
        # Check if there's a slash pattern with a character at the end
        match = re.search(r'(.+/\d+)[a-zA-Z]$', street)
        if match:
            # Return everything except the last character
            return match.group(1)
        
        # No modification needed
        return street

    def _normalize_street_name(self, street):
        """
        Normalize a street name for comparison by:
        1. Converting to lowercase
        2. Removing common prefixes (Jalan, Jln, etc)
        3. Removing multiple spaces and trailing letters
        4. Standardizing separators

        Args:
            street (str): Street name to normalize

        Returns:
            str: Normalized street name
        """
        if not street:
            return ""
            
        # Convert to lowercase and trim
        s = street.lower().strip()
        
        # Remove common prefixes
        prefixes = ['jalan ', 'jln ', 'lorong ', 'persiaran ', 'jln. ', 'jalan. ']
        for prefix in prefixes:
            if s.startswith(prefix):
                s = s[len(prefix):].strip()
                break
        
        # Normalize section/subsection format (u13/12, u13-12, u13 12, etc)
        s = re.sub(r'([a-z]+\d+)[\s/\\-]+(\d+[a-z]?)', r'\1/\2', s, flags=re.IGNORECASE)
        
        # Remove single letters surrounded by spaces (like "a" in "setia a utama")
        s = re.sub(r'\s+([a-z])\s+', ' ', s, flags=re.IGNORECASE)
        
        # Remove trailing single letters
        s = re.sub(r'\s+[a-z]$', '', s, flags=re.IGNORECASE)
        
        # Remove leading single letters
        s = re.sub(r'^[a-z]\s+', '', s, flags=re.IGNORECASE)
        
        # Normalize whitespace
        s = re.sub(r'\s+', ' ', s).strip()
        
        return s

    def _streets_have_similarity(self, street1, street2):
        """
        Check if two streets have some similarity beyond exact matching.
        This helps with clustering similar street patterns.
        
        Args:
            street1 (str): First street name
            street2 (str): Second street name
            
        Returns:
            bool: True if streets are similar
        """
        if not street1 or not street2:
            return False
        
        # Extract development patterns from both
        pattern1 = self._extract_development_pattern(street1, '')
        pattern2 = self._extract_development_pattern(street2, '')
        
        # If they share the same development pattern, they're similar
        if pattern1 and pattern1 == pattern2:
            return True
        
        # Extract section identifiers
        section1, subsection1 = self._extract_section_identifier(street1)
        section2, subsection2 = self._extract_section_identifier(street2)
        
        # If they're in the same section, they're similar
        if section1 and section1 == section2:
            return True
        
        # If normalized versions match, they're similar
        norm1 = self._normalize_street_for_clustering(street1)
        norm2 = self._normalize_street_for_clustering(street2)
        
        if norm1 and norm1 == norm2:
            return True
        
        return False

    def _compare_street_paths(self, street1, street2):
        """
        Compare full street paths for clustering
        """
        if not street1 or not street2:
            return False
        
        # Normalize strings
        s1 = self._normalize_street_name(street1)
        s2 = self._normalize_street_name(street2)
        
        print(f"DEBUG: Comparing '{s1}' with '{s2}'")
        
        # Level 1: Exact match
        if s1 == s2:
            print(f"DEBUG: Exact match found for '{s1}' and '{s2}'")
            return True
        
        # Level 2: Street stem match (without last character)
        # Create a function to get stem by removing last character if it's a letter after a number
        def get_street_stem(street):
            match = re.search(r'/\d+[a-zA-Z]$', street)
            if match:
                return street[:-1]
            return street
            
        stem1 = get_street_stem(s1)
        stem2 = get_street_stem(s2)
        
        if stem1 != s1 and stem2 != s2 and stem1 == stem2:
            print(f"DEBUG: Street stem match: '{stem1}'")
            return True
        
        # Extract components for further analysis
        components1 = self._extract_street_parts(s1)
        components2 = self._extract_street_parts(s2)
        
        print(f"DEBUG: Street 1 components: {components1}")
        print(f"DEBUG: Street 2 components: {components2}")
        
        # Level 3: Development + Section match
        # Must have matching development names (if both have them) and matching sections
        if (components1['development'] and components2['development']):
            # If both have development names, they must match
            if components1['development'] != components2['development']:
                print(f"DEBUG: Development names don't match: '{components1['development']}' vs '{components2['development']}'")
                return False
            
            # If they have matching development names and matching sections
            if components1['section'] and components2['section'] and components1['section'] == components2['section']:
                print(f"DEBUG: Matched by development '{components1['development']}' and section '{components1['section']}'")
                return True
        
        # Level 4: Section and numeric subsection match
        # This handles cases like U13/55T and U13/55Y (different letter suffixes)
        if (components1['section'] and components2['section'] and 
            components1['section'] == components2['section']):
            
            # Extract numeric part of subsections
            num1 = re.search(r'(\d+)', components1['subsection'])
            num2 = re.search(r'(\d+)', components2['subsection'])
            
            if num1 and num2 and num1.group(1) == num2.group(1):
                print(f"DEBUG: Matched by section/subsection base: {components1['section']}/{num1.group(1)}")
                return True
        
        print(f"DEBUG: Streets don't match after all checks")
        return False

    def _get_street_stem(self, street):
        """Get the street stem by removing the last character if it follows the Malaysian address pattern"""
        if not street:
            return ""
        
        # Regex: Matches if string ends with '/' + digits + exactly one letter
        match = re.search(r'/\d+[a-zA-Z]$', street)
        if match:
            return street[:-1]  # Return string excluding last char
        return street  # Return original if pattern doesn't match

    def _extract_section_identifier(self, street):
        """
        Extract section identifier from Malaysian address format
        
        Args:
            street (str): Street name
            
        Returns:
            tuple: (section, subsection) or (None, None) if not found
        """
        if not street:
            return None, None
            
        # Match patterns like U13/22B, SS15/3D, etc.
        section_pattern = r'([A-Z]+\d+)[/\\](\d+)[A-Z]?'
        match = re.search(section_pattern, street, re.IGNORECASE)
        if match:
            print(f"DEBUG: Extracted section={match.group(1).upper()}, subsection={match.group(2)} from '{street}'")
            return match.group(1).upper(), match.group(2)
        
        # Try alternative format - sometimes there's no subsection
        alt_pattern = r'([A-Z]+\d+)[^0-9]*$'
        match = re.search(alt_pattern, street, re.IGNORECASE)
        if match:
            print(f"DEBUG: Extracted section={match.group(1).upper()}, no subsection from '{street}'")
            return match.group(1).upper(), None
            
        print(f"DEBUG: No section identifier found in '{street}'")
        return None, None

    def _extract_development_pattern(self, street, neighborhood=None):
        """
        Extract housing development name from street patterns with improved heuristics
        
        Args:
            street (str): Street name like "Jalan Setia Nusantara U13/22T"
            neighborhood (str): Neighborhood name if available
        
        Returns:
            str: Development name like "Setia Nusantara"
        """
        if not street:
            return neighborhood.title() if neighborhood and isinstance(neighborhood, str) else None
        
        # Normalize and clean the street name first
        street_lower = self._normalize_street_name(street).lower()
        
        # List of common development name prefixes in Malaysia
        common_prefixes = ['taman', 'bandar', 'desa', 'setia', 'kota', 'bukit', 'puncak', 
                           'subang', 'tropicana', 'ara', 'damansara', 'sentosa', 'utama']
        
        # Strategy 1: Check for common prefixes as standalone words
        parts = street_lower.split()
        if parts:
            # If street starts with a common prefix followed by another word
            for prefix in common_prefixes:
                if prefix in parts:
                    prefix_idx = parts.index(prefix)
                    # Check if there's a word after the prefix that looks like a name
                    if prefix_idx + 1 < len(parts) and not parts[prefix_idx + 1].isdigit() and not re.match(r'^[a-z]\d+/?', parts[prefix_idx + 1]):
                        # Extract prefix and next word
                        dev_name = f"{parts[prefix_idx]} {parts[prefix_idx + 1]}"
                        # Look for more potential name parts
                        next_idx = prefix_idx + 2
                        while next_idx < len(parts):
                            next_part = parts[next_idx]
                            # Stop if we hit a section pattern or a number
                            if re.match(r'^[a-z]\d+/?', next_part) or next_part.isdigit():
                                break
                            # Add to development name
                            dev_name += f" {next_part}"
                            next_idx += 1
                        return dev_name.title()
        
        # Strategy 2: Extract everything before section/subsection pattern
        section_pattern = re.search(r'([a-z]\d+)/(\d+[a-z]?)', street_lower)
        if section_pattern:
            # Get everything before the section pattern
            section_start = street_lower.find(section_pattern.group(0))
            if section_start > 0:
                prefix = street_lower[:section_start].strip()
                # Remove common road prefixes
                if prefix.startswith('jalan '):
                    prefix = prefix[6:].strip()
                elif prefix.startswith('jln '):
                    prefix = prefix[4:].strip()
                
                if prefix and len(prefix) > 1:  # Ensure it's not empty or too short
                    return prefix.title()
        
        # Strategy 3: If neighborhood is available and looks like a development name
        if neighborhood:
            # Check if neighborhood has common development words
            neighborhood_lower = neighborhood.lower()
            for prefix in common_prefixes:
                if prefix in neighborhood_lower:
                    return neighborhood.title()
        
        # No clear development pattern found
        return None

    def _format_street_with_section(self, street, section, subsection):
        """
        Format a street name with section and subsection consistently
        
        Args:
            street (str): Original street name
            section (str): Section identifier (e.g., "U13")
            subsection (str): Subsection identifier (e.g., "21")
            
        Returns:
            str: Formatted street name
        """
        # Remove section/subsection if it appears in a different format
        pattern = fr"{section}[\\\/\s]*{subsection}"
        clean_street = re.sub(pattern, "", street, flags=re.IGNORECASE).strip()
        
        # Remove trailing spaces and punctuation
        clean_street = re.sub(r'[\s,.-]+$', '', clean_street)
        
        # Add properly formatted section/subsection
        if clean_street:
            return f"{clean_street} {section}/{subsection}"
        else:
            return f"Jalan {section}/{subsection}"

    def _cleanup_geocoded_address(self, address):
        """
        Clean up address components, especially removing stray letters in street names
        
        Args:
            address (dict): Address dictionary from geocoding
            
        Returns:
            dict: Cleaned address dictionary
        """
        if not address:
            return address
        
        # Clean up street name
        street = address.get('street', '')
        if street:
            # First, handle the specific patterns we're seeing
            # 1. Remove isolated single letters surrounded by spaces
            clean_street = re.sub(r'\s+[A-Z]\s+', ' ', street, flags=re.IGNORECASE)
            
            # 2. Remove trailing single letters
            clean_street = re.sub(r'\s+[A-Z]$', '', clean_street, flags=re.IGNORECASE)
            
            # 3. Remove leading single letters
            clean_street = re.sub(r'^\s*[A-Z]\s+', '', clean_street, flags=re.IGNORECASE)
            
            # 4. Special case: Handle development names with specific block patterns
            # But keep letters that are part of section/subsection format
            section_pattern = r'([A-Z]+\d+)/(\d+[A-Z]?)'
            section_match = re.search(section_pattern, clean_street, re.IGNORECASE)
            
            if section_match:
                # Split the string at the section pattern
                parts = re.split(section_pattern, clean_street, maxsplit=1, flags=re.IGNORECASE)
                if len(parts) >= 4:  # [prefix, section, subsection, suffix]
                    # Clean the prefix (development name)
                    prefix = parts[0].strip()
                    prefix = re.sub(r'\s+[A-Z](?=\s|$)', '', prefix, flags=re.IGNORECASE)
                    
                    # Preserve the section/subsection exactly as is
                    section = parts[1]
                    subsection = parts[2]
                    
                    # Clean any suffix
                    suffix = parts[3].strip() if len(parts) > 3 else ''
                    suffix = re.sub(r'^\s*[A-Z]\s+', '', suffix, flags=re.IGNORECASE)
                    
                    # Reassemble
                    clean_street = f"{prefix} {section}/{subsection}"
                    if suffix:
                        clean_street = f"{clean_street} {suffix}"
            
            # 5. Ensure proper spacing
            clean_street = re.sub(r'\s+', ' ', clean_street).strip()
            
            # Debug to trace the cleaning
            if clean_street != street:
                print(f"DEBUG: Cleaned street name from '{street}' to '{clean_street}'")
                address['street'] = clean_street
        
        return address

    def resolve_address(self, lat, lon, user_provided_address=None):
        """
        Get address for a location with priority:
        1. User provided address
        2. Geocoded address
        3. Suggested values
        
        Returns:
            dict: {
                'address': final address dict,
                'needs_user_input': bool,
                'suggested_values': dict if needed
            }
        """
        # First check if we have user-provided address
        if user_provided_address and user_provided_address.get('street'):
            return {
                'address': user_provided_address,
                'needs_user_input': False,
                'suggested_values': {}
            }
            
        # Then try geocoding
        address = self.geocode_location(lat, lon)
        
        # If geocoding succeeded with street, use it
        if address and address.get('street'):
            return {
                'address': address,
                'needs_user_input': False,
                'suggested_values': {}
            }
        
        # Otherwise, get suggestions
        return self.get_address_suggestions(lat, lon, address)

    def get_address_with_fallback(self, lat, lon):
        """
        Get address for a location with fallback to user input if needed
        
        Args:
            lat (float): Latitude
            lon (float): Longitude
            
        Returns:
            dict: {
                'address': address_dict or None,
                'needs_user_input': True/False,
                'suggested_values': dict of suggested values for form
            }
        """
        # First try standard geocoding
        address = self.geocode_location(lat, lon)
        
        # If we got a valid street, return success
        if address and address.get('street'):
            return {
                'address': address,
                'needs_user_input': False,
                'suggested_values': {}
            }
        
        # Initialize address components to empty if address is None
        address_neighborhood = ''
        address_city = ''
        address_postcode = ''
        address_country = 'Malaysia'
        
        # Extract address components safely if address exists
        if address:
            address_neighborhood = address.get('neighborhood', '')
            address_city = address.get('city', '')
            address_postcode = address.get('postcode', '')
            address_country = address.get('country', 'Malaysia')
        
        # We need user input, but let's provide some suggestions
        
        # 1. Get approximate section if possible
        section = None
        subsection = None
        neighborhood = None
        
        # Try to determine the area by searching nearby locations
        nearby = execute_read(
            """SELECT l.street, l.neighborhood
               FROM locations l 
               WHERE l.street != '' AND (
                   (l.lat BETWEEN ? AND ?) AND 
                   (l.lon BETWEEN ? AND ?)
               )
               LIMIT 5""",
                    (
                        lat - 0.003, lat + 0.003,  # About 300m radius
                lon - 0.003, lon + 0.003
            )
        )
        
        # Try to identify common sections or neighborhoods
        if nearby:
            print(f"DEBUG: Found {len(nearby)} nearby locations with street names")
            potential_sections = []
            potential_neighborhoods = []
            
            for location in nearby:
                # Get street safely - handles both dict and Row objects
                street = location['street'] if 'street' in location else ''
                if street:
                    # Try to extract section identifiers (e.g., U13/22)
                    s, sub = self._extract_section_identifier(street)
                    if s:
                        potential_sections.append((s, sub))
                
                # Get neighborhood safely
                n = location['neighborhood'] if 'neighborhood' in location else ''
                if n:
                    potential_neighborhoods.append(n)
            
            # See if we have a common section
            if potential_sections:
                # Find the most common section
                section_counts = {}
                for s, sub in potential_sections:
                    s_upper = s.upper()
                    if s_upper not in section_counts:
                        section_counts[s_upper] = {'count': 0, 'subsections': {}}
                    section_counts[s_upper]['count'] += 1
                    
                    if sub and sub not in section_counts[s_upper]['subsections']:
                        section_counts[s_upper]['subsections'][sub] = 0
                    if sub:
                        section_counts[s_upper]['subsections'][sub] += 1
                
                # Get the most common section
                if section_counts:
                    max_count = 0
                    most_common_section = None
                    most_common_subsection = None
                    
                    for s, data in section_counts.items():
                        if data['count'] > max_count:
                            max_count = data['count']
                            most_common_section = s
                            
                            # Also find the most common subsection for this section
                            sub_max = 0
                            for sub, sub_count in data['subsections'].items():
                                if sub_count > sub_max:
                                    sub_max = sub_count
                                    most_common_subsection = sub
                    
                    if most_common_section:
                        section = most_common_section
                        subsection = most_common_subsection
                        print(f"DEBUG: Identified likely section: {section}/{subsection}")
            
            # See if we have a common neighborhood
            if potential_neighborhoods:
                neighborhood_counts = {}
                for n in potential_neighborhoods:
                    if n not in neighborhood_counts:
                        neighborhood_counts[n] = 0
                    neighborhood_counts[n] += 1
                    
                if neighborhood_counts:
                    # Get the most common neighborhood
                    max_count = 0
                    for n, count in neighborhood_counts.items():
                        if count > max_count:
                            max_count = count
                            neighborhood = n
                    
                    print(f"DEBUG: Identified likely neighborhood: {neighborhood}")
        else:
            print(f"DEBUG: No nearby locations found with street names")
        
        # 2. Look for development patterns in nearby clusters
        if not neighborhood:
            nearby_clusters = execute_read(
                """SELECT c.name, c.centroid_lat, c.centroid_lon
                   FROM clusters c
                   WHERE (
                       (c.centroid_lat BETWEEN ? AND ?) AND 
                       (c.centroid_lon BETWEEN ? AND ?)
                   )
                   LIMIT 3""",
                (
                    lat - 0.005, lat + 0.005,  # About 500m radius
                    lon - 0.005, lon + 0.005
                )
            )
            
            if nearby_clusters:
                # Just use the name of the nearest cluster as a suggestion
                if len(nearby_clusters) > 0:
                    nearest_name = nearby_clusters[0]['name']
                    if '/' in nearest_name:
                        parts = nearest_name.split('/')
                        if len(parts) >= 2:
                            development = ' '.join(parts[0].split()[:-1])  # Everything before the section
                            neighborhood = development
                    else:
                        neighborhood = nearest_name
                    
                    print(f"DEBUG: Using nearest cluster name for suggestion: {neighborhood}")
        
        # Generate suggested values for form fields safely
        suggested_values = {
            'section': section,
            'subsection': subsection,
            'neighborhood': neighborhood or address_neighborhood,
            'city': address_city,
            'postcode': address_postcode,
            'country': address_country,
        }
        
        print(f"DEBUG: Suggested values for form: {suggested_values}")
        
        # If we have most parts of the address except street, indicate form needs
        return {
            'address': address or {},  # Ensure address is never None
            'needs_user_input': True,
            'suggested_values': suggested_values
        }

    def debug_extraction(self, street):
        """
        Debug helper for street pattern extraction
        
        Args:
            street (str): Street name to debug
        """
        print(f"\n=== DEBUGGING STREET: '{street}' ===")
        
        # Test development pattern extraction
        dev = self._extract_development_pattern(street, '')
        print(f"Development pattern: '{dev}'")
        
        # Test section extraction
        sec, subsec = self._extract_section_identifier(street)
        print(f"Section: '{sec}', Subsection: '{subsec}'")
        
        # Test cleanup
        address = {'street': street}
        cleaned = self._cleanup_geocoded_address(address)
        print(f"Cleaned street: '{cleaned['street']}'")
        
        # Test address formatting
        if sec and subsec:
            formatted = self._format_street_with_section(street, sec, subsec)
            print(f"Formatted street: '{formatted}'")
        
        print("===================================\n")

    def _extract_street_parts(self, street):
        """
        Extract components from street name with improved pattern recognition.
        
        Better handling of formats like:
        - "Jalan U13/52P" (just section/subsection)
        - "Jalan Setia U13/52P" (development + section/subsection)
        """
        if not street:
            return {
                'development': '',
                'section': '',
                'subsection': '',
                'block': ''
            }
        
        # Normalize and clean the street name
        street = self._normalize_street_name(street)
        
        # Patterns to extract components
        # Pattern for section/subsection: U13/52P or u13/52p
        section_pattern = r'([a-zA-Z]\d+)/(\d+[a-zA-Z]?)'
        
        # Pattern for block: BLOCK A, Block B, etc.
        block_pattern = r'block\s+([a-zA-Z0-9]+)'
        
        # Extract section/subsection if present
        section_match = re.search(section_pattern, street)
        section = ''
        subsection = ''
        
        if section_match:
            section = section_match.group(1).upper()  # e.g., U13
            subsection = section_match.group(2)       # e.g., 52P
        
        # Extract block if present
        block_match = re.search(block_pattern, street)
        block = block_match.group(1) if block_match else ''
        
        # Extract development pattern - everything before the section
        development = ''
        if section_match:
            # Get the part before the section/subsection
            section_start = street.find(section_match.group(0))
            if section_start > 0:
                # Take everything before the section, strip "jalan" prefix if present
                prefix = street[:section_start].strip()
                if prefix.lower().startswith('jalan '):
                    prefix = prefix[6:].strip()
                development = prefix
        else:
            # If no section found, use the entire street as development
            # Remove "jalan" prefix if present
            if street.lower().startswith('jalan '):
                development = street[6:].strip()
            else:
                development = street.strip()
        
        # If development ended up being just "jalan", set it to empty
        if development.lower() == 'jalan':
            development = ''
        
        print(f"DEBUG: Extracted from '{street}': dev='{development}', section='{section}', subsection='{subsection}', block='{block}'")
        
        return {
            'development': development,
            'section': section,
            'subsection': subsection,
            'block': block
        }

    def clean_existing_locations(self):
        """
        Clean up any existing locations in the database to fix stray letters
        """
        print("DEBUG: Starting cleanup of existing location street names")
        
        # Get all locations with street names
        locations = execute_read(
            "SELECT id, street FROM locations WHERE street IS NOT NULL AND street != ''"
        )
        
        updated = 0
        for loc in locations:
            location_id = loc['id']
            original_street = loc['street']
            
            # Apply the same cleanup
            cleaned = self._cleanup_geocoded_address({'street': original_street})
            clean_street = cleaned['street']
            
            if clean_street != original_street:
                # Update the database
                execute_write(
                    "UPDATE locations SET street = ? WHERE id = ?",
                    (clean_street, location_id)
                )
                updated += 1
                print(f"DEBUG: Updated location {location_id}: '{original_street}' → '{clean_street}'")
        
        print(f"DEBUG: Cleaned {updated} location street names in database")
        return updated
    
    def identify_cluster_access_points(self, cluster_id):
        """
        Identify access points for a cluster using network topology
        
        Args:
            cluster_id: ID of the cluster
            
        Returns:
            list: List of checkpoint dictionaries
        """
        print(f"DEBUG: Identifying access points for cluster {cluster_id}")
        
        # 1. Get all locations in this cluster
        locations = execute_read(
            """SELECT l.id, l.lat, l.lon 
            FROM locations l
            JOIN location_clusters lc ON l.id = lc.location_id
            WHERE lc.cluster_id = ?""",
            (cluster_id,)
        )
        
        if not locations:
            print(f"DEBUG: No locations found for cluster {cluster_id}")
            return []
        
        # 2. Get cluster center
        cluster_info = execute_read(
            "SELECT name, centroid_lat, centroid_lon FROM clusters WHERE id = ?",
            (cluster_id,),
            one=True
        )
        
        # Prepare inputs for network analysis
        location_coords = [(loc['lat'], loc['lon']) for loc in locations]
        cluster_center = (cluster_info['centroid_lat'], cluster_info['centroid_lon'])
        
        # 3. Use network analysis to find access points
        try:
            access_points = self.network_analyzer.find_cluster_access_points(
                location_coords, cluster_center
            )
            
            # 4. Save the access points to the database
            for ap in access_points:
                checkpoint_id = execute_write(
                    """INSERT INTO security_checkpoints 
                    (cluster_id, lat, lon, from_road_type, to_road_type, confidence)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        cluster_id, 
                        ap['lat'], 
                        ap['lon'], 
                        ap['from_type'], 
                        ap['to_type'],
                        ap.get('confidence', 1.0)
                    )
                )
                print(f"DEBUG: Created checkpoint {checkpoint_id} for cluster {cluster_id}")
            
            return access_points
        
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"DEBUG: Error in network analysis: {str(e)}")
            
            # Fall back to simple method if network analysis fails
            return self._calculate_fallback_checkpoint(cluster_id, locations)