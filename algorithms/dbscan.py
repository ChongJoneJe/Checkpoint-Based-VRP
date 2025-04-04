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
                        
                        # Check for section/subsection
                        section_match = re.search(r'([A-Z]+\d+)[/\\](\d+)[A-Z]?', street, re.IGNORECASE)
                        if section_match:
                            section = section_match.group(1).upper()
                            subsection = section_match.group(2)
                            
                            # Format street consistently with section/subsection
                            formatted_street = self._format_street_with_section(street, section, subsection)
                            
                            result = {
                                'street': formatted_street,
                                'neighborhood': address.get('neighbourhood', ''),
                                'town': address.get('town', ''),
                                'city': address.get('city', ''),
                                'postcode': address.get('postcode', ''),
                                'country': address.get('country', '')
                            }
                            return result
                        
                        result = {
                            'street': street,
                            'neighborhood': address.get('neighbourhood', ''),
                            'town': address.get('town', ''),
                            'city': address.get('city', ''),
                            'postcode': address.get('postcode', ''),
                            'country': address.get('country', '')
                        }
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

    def add_location_with_smart_clustering(self, lat, lon, warehouse_lat, warehouse_lon):
        """
        Add a location to the database with revised smart clustering based on precise street matching.
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
                    'town': existing_loc.get('town', ''),
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
                    "SELECT street, neighborhood, town, city, postcode, country FROM locations WHERE lat = ? AND lon = ?",
                    (lat, lon),
                    one=True
                )

                if existing_address and existing_address.get('street'):
                    # Use existing geocoded address from database
                    address = {
                        'street': existing_address.get('street', ''),
                        'neighborhood': existing_address.get('neighborhood', ''),
                        'town': existing_address.get('town', ''),
                        'city': existing_address.get('city', ''),
                        'postcode': existing_address.get('postcode', ''),
                        'country': existing_address.get('country', '')
                    }
                    print(f"DEBUG: Using existing geocoded address from database")
                else:
                    address = self.geocode_location(lat, lon)
                
                if not address:
                    print(f"WARNING: Could not geocode location ({lat}, {lon}) - creating without address data")
                    address = {'street': '', 'neighborhood': '', 'town': '', 'city': '', 'postcode': '', 'country': ''}
                else:
                    print(f"DEBUG: Address components from geocoding: {address}")
                
                # Continue with existing location check and insertion
                if existing_loc:
                    location_id = existing_loc['id']
                    LocationRepository.update_address(location_id, address)
                else:
                    location_id = LocationRepository.insert(lat, lon, address)
                    print(f"DEBUG: Inserted new location with ID: {location_id}")
            
            # Check if this is the warehouse location (with small tolerance for float comparison)
            if abs(lat - warehouse_lat) < 0.0001 and abs(lon - warehouse_lon) < 0.0001:
                print(f"DEBUG: Location ({lat}, {lon}) is the warehouse - excluding from clustering")
                return location_id, None, False
            
            # Format street with section/subsection properly if needed
            if address and address.get('street'):
                # Check if we need to extract section/subsection
                street = address.get('street', '')
                section, subsection = self._extract_section_identifier(street)
                
                # If we found a section but it's not properly formatted, reformat it
                if section and subsection and f"{section}/{subsection}" not in street:
                    formatted_street = self._format_street_with_section(street, section, subsection)
                    if formatted_street != street:
                        print(f"DEBUG: Reformatted street from '{street}' to '{formatted_street}'")
                        address['street'] = formatted_street
                        # Update the location with reformatted street
                        if existing_loc:
                            LocationRepository.update_address(location_id, address)
            
            # Get the street from address
            street = address.get('street', '').lower()
            neighborhood = address.get('neighborhood', '')
            
            cluster_id = None
            is_new_cluster = False
            
            # Skip clustering if we don't have street information
            if not street:
                print(f"DEBUG: No street information for location {location_id}, skipping clustering")
                return location_id, None, False
            
            print(f"DEBUG: Attempting to cluster location with street: {street}")
            
            print(f"DEBUG: Trying strategy 1: Exact section matching")
            # 1. FIRST CLUSTERING STRATEGY: Exact section matching
            # Extract section identifiers from this location (e.g., U13/21)
            section, subsection = self._extract_section_identifier(street)
            
            if section and subsection:
                print(f"DEBUG: Extracted section/subsection: {section}/{subsection}")
                
                # Search for existing clusters with matching section/subsection
                query = """
                    SELECT c.id, c.name 
                    FROM clusters c 
                    WHERE c.name LIKE ? 
                    ORDER BY c.id DESC
                    LIMIT 1
                """
                
                # Look for pattern where section/subsection is at the end of cluster name
                # (handles both "Setia Duta U13/21" and just "U13/21")
                pattern = f"%{section}/{subsection}"
                existing_cluster = execute_read(query, (pattern,), one=True)
                
                if existing_cluster:
                    print(f"DEBUG: Found matching section cluster: {existing_cluster['name']}")
                    cluster_id = existing_cluster['id']
                    
                    # Verify the cluster exists
                    verification = execute_read("SELECT id, name FROM clusters WHERE id = ?", 
                                               (cluster_id,), one=True)
                    if verification:
                        print(f"DEBUG: Verified cluster exists: {verification['name']}")
                    else:
                        print(f"ERROR: Cluster {cluster_id} not found in database!")
                    
                    # Assign location to this cluster
                    execute_write(
                        "INSERT OR REPLACE INTO location_clusters (location_id, cluster_id) VALUES (?, ?)",
                        (location_id, cluster_id)
                    )
                    
                    return location_id, cluster_id, False
            
            print(f"DEBUG: Strategy 1 failed, trying strategy 2")
            # 2. SECOND CLUSTERING STRATEGY: Development pattern matching
            development_pattern = self._extract_development_pattern(street, neighborhood)
            
            if development_pattern:
                print(f"DEBUG: Extracted development pattern: {development_pattern}")
                
                # Look for clusters with the same development pattern
                query = """
                    SELECT c.id, c.name
                    FROM clusters c
                    WHERE c.name LIKE ?
                    ORDER BY c.id DESC
                    LIMIT 5
                """
                
                existing_clusters = execute_read(query, (f"{development_pattern}%",))
                
                if existing_clusters:
                    print(f"DEBUG: Found {len(existing_clusters)} clusters with matching development pattern")
                    
                    # Check each cluster to see if streets match without last character
                    for cluster in existing_clusters:
                        # Get streets in this cluster
                        cluster_streets = execute_read(
                            """
                            SELECT l.street 
                            FROM locations l
                            JOIN location_clusters lc ON l.id = lc.location_id
                            WHERE lc.cluster_id = ? AND l.street != ''
                            """,
                            (cluster['id'],)
                        )
                        
                        for cluster_street in cluster_streets:
                            cluster_street_val = cluster_street['street'].lower()
                            
                            # Check if streets match without last character
                            normalized_street = self._normalize_street_for_clustering(street)
                            normalized_cluster_street = self._normalize_street_for_clustering(cluster_street_val)
                            
                            if normalized_street and normalized_street == normalized_cluster_street:
                                print(f"DEBUG: Normalized street match: '{normalized_street}' with '{normalized_cluster_street}'")
                                
                                # Assign to this cluster
                                cluster_id = cluster['id']
                                execute_write(
                                    "INSERT OR REPLACE INTO location_clusters (location_id, cluster_id) VALUES (?, ?)",
                                    (location_id, cluster_id)
                                )
                                
                                return location_id, cluster_id, False
            
            print(f"DEBUG: Strategy 2 failed, trying strategy 3")
            # 3. THIRD CLUSTERING STRATEGY: Neighborhood matching
            if neighborhood:
                print(f"DEBUG: Checking neighborhood matching for: {neighborhood}")
                
                # Look for clusters with the same neighborhood
                query = """
                    SELECT DISTINCT c.id, c.name
                    FROM clusters c
                    JOIN location_clusters lc ON c.id = lc.cluster_id
                    JOIN locations l ON lc.location_id = l.id
                    WHERE l.neighborhood = ?
                    ORDER BY c.id DESC
                    LIMIT 1
                """
                
                existing_cluster = execute_read(query, (neighborhood,), one=True)
                
                if existing_cluster:
                    print(f"DEBUG: Found cluster with matching neighborhood: {existing_cluster['name']}")
                    cluster_id = existing_cluster['id']
                    
                    # Assign location to this cluster
                    execute_write(
                        "INSERT OR REPLACE INTO location_clusters (location_id, cluster_id) VALUES (?, ?)",
                        (location_id, cluster_id)
                    )
                    
                    return location_id, cluster_id, False
            
            print(f"DEBUG: Strategy 3 failed, trying strategy 4")
            # 4. FINAL STRATEGY: Proximity-based clustering
            # Only try this if we have at least a development pattern or section
            if development_pattern or section:
                print(f"DEBUG: Attempting proximity-based clustering")
                
                # Get all locations within a small radius (400m)
                nearby_locations = execute_read(
                    """
                    SELECT l.id, l.street, lc.cluster_id
                    FROM locations l
                    LEFT JOIN location_clusters lc ON l.id = lc.location_id
                    WHERE (
                        (l.lat BETWEEN ? AND ?) AND 
                        (l.lon BETWEEN ? AND ?) AND
                        l.id != ?
                    )
                    """,
                    (
                        lat - 0.004, lat + 0.004,  # Approx 400m
                        lon - 0.004, lon + 0.004,
                        location_id
                    )
                )
                
                if nearby_locations:
                    # Group nearby locations by their cluster
                    proximity_clusters = {}
                    for loc in nearby_locations:
                        if loc['cluster_id']:
                            if loc['cluster_id'] not in proximity_clusters:
                                proximity_clusters[loc['cluster_id']] = 0
                            proximity_clusters[loc['cluster_id']] += 1
                    
                    if proximity_clusters:
                        # Find the most common cluster in the proximity
                        max_count = 0
                        nearest_cluster_id = None
                        
                        for c_id, count in proximity_clusters.items():
                            if count > max_count:
                                max_count = count
                                nearest_cluster_id = c_id
                        
                        if nearest_cluster_id:
                            # Get cluster name for logging
                            cluster_name = execute_read(
                                "SELECT name FROM clusters WHERE id = ?",
                                (nearest_cluster_id,),
                                one=True
                            )
                            
                            print(f"DEBUG: Assigning to proximity cluster: {cluster_name['name']}")
                            
                            # Assign to this proximity cluster
                            cluster_id = nearest_cluster_id
                            execute_write(
                                "INSERT OR REPLACE INTO location_clusters (location_id, cluster_id) VALUES (?, ?)",
                                (location_id, cluster_id)
                            )
                            
                            return location_id, cluster_id, False
            
            print(f"DEBUG: Strategy 4 failed, creating new cluster")
            # 5. CREATE NEW CLUSTER
            # If we got here, we need to create a new cluster
            print(f"DEBUG: Creating new cluster for location {location_id}")
            
            # Determine the best name for the new cluster
            cluster_name = ""
            
            if section and subsection:
                # Create name based on development and section
                if development_pattern:
                    cluster_name = f"{development_pattern} {section}/{subsection}"
                else:
                    cluster_name = f"{section}/{subsection}"
            elif development_pattern:
                # Just use development pattern
                cluster_name = development_pattern
            elif neighborhood:
                # Fall back to neighborhood
                cluster_name = neighborhood
            else:
                # Last resort - use street name
                cluster_name = street.title()
            
            print(f"DEBUG: New cluster name: {cluster_name}")
            
            # Insert new cluster with only required columns
            try:
                cluster_id = execute_write(
                    """
                    INSERT INTO clusters (name, centroid_lat, centroid_lon)
                    VALUES (?, ?, ?)
                    """,
                    (cluster_name, lat, lon)
                )
            except Exception as e:
                print(f"Error creating cluster: {str(e)}")
                return location_id, None, False  # Fail cleanly if we can't create cluster
            
            # Assign location to the new cluster
            execute_write(
                "INSERT INTO location_clusters (location_id, cluster_id) VALUES (?, ?)",
                (location_id, cluster_id)
            )
            
            is_new_cluster = True
            
            print(f"DEBUG: ===== CLUSTERING RESULT: {cluster_id} (new: {is_new_cluster}) =====")
            
            if cluster_id is not None:
                return location_id, cluster_id, is_new_cluster
            else:
                print("DEBUG: No clustering strategy succeeded, returning without cluster")
                return location_id, None, False
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"ERROR: Error in smart clustering: {str(e)}")
            return None, None, False

    def _normalize_street_for_clustering(self, street):
        """
        Normalize a street name for clustering by removing the last character identifier after '/'
        Example: 'jalan setia nusantara u13/22t' -> 'jalan setia nusantara u13/22'
        
        Args:
            street (str): Original street name
            
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
        Extract housing development name from street patterns
        
        Args:
            street (str): Street name like "Jalan Setia Nusantara U13/22T"
            neighborhood (str): Neighborhood name if available
        
        Returns:
            str: Development name like "Setia Nusantara"
        """
        if not street:
            return neighborhood.title() if neighborhood and isinstance(neighborhood, str) else None
            
        # Remove common prefixes
        prefixes = ['jalan ', 'jln ', 'lorong ', 'persiaran ']
        street_lower = street.lower()
        for prefix in prefixes:
            if street_lower.startswith(prefix):
                street = street[len(prefix):]
                break
        
        # First try to match development name followed by section
        # Modified pattern to exclude single letters before section
        section_match = re.search(r'(.+?)(?:\s+[A-Z])?\s+([A-Z]+\d+/\d+[A-Z]?)', street, re.IGNORECASE)
        if section_match:
            development_name = section_match.group(1).strip()
            # Remove any trailing single letters
            development_name = re.sub(r'\s+[A-Z]$', '', development_name, flags=re.IGNORECASE)
            return development_name.title()
        
        # Try alternative patterns for cases where the format varies
        alt_match = re.search(r'(.+?)(?:\s+[A-Z])?\s+([A-Z]+\d+)', street, re.IGNORECASE)
        if alt_match:
            development_name = alt_match.group(1).strip()
            # Remove any trailing single letters
            development_name = re.sub(r'\s+[A-Z]$', '', development_name, flags=re.IGNORECASE)
            return development_name.title()
        
        # If no section identifiers, just use the whole name
        # Remove any trailing single letters
        street = re.sub(r'\s+[A-Z]$', '', street.strip(), flags=re.IGNORECASE)
        return street.title()

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