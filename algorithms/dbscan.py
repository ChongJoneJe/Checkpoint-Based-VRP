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
                        if result:
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
            
            # Get the street from address and clean it
            street = address.get('street', '').strip()
            neighborhood = address.get('neighborhood', '')

            # Skip if no street information
            if not street:
                print(f"DEBUG: No street information for location {location_id}, skipping clustering")
                return location_id, None, False

            # Clean up the street name
            cleaned_address = self._cleanup_geocoded_address({'street': street})
            street = cleaned_address['street']
            print(f"DEBUG: Using clean street name: {street}")

            # Extract street components for cluster naming
            street_parts = self._extract_street_parts(self._normalize_street_name(street))
            section = street_parts['section']
            subsection = street_parts['subsection']
            development_pattern = street_parts['development'].title()
            block = street_parts['block']

            # Initialize variables
            cluster_id = None
            is_new_cluster = False

            print(f"DEBUG: Trying to find matching street for '{street}'")
            # Find exact matches first
            query = """
                SELECT lc.cluster_id, l.street, c.name as cluster_name 
                FROM locations l
                JOIN location_clusters lc ON l.id = lc.location_id
                JOIN clusters c ON lc.cluster_id = c.id
                WHERE l.street IS NOT NULL AND l.street != ''
                LIMIT 100
            """
            matching_locations = execute_read(query)

            if matching_locations:
                for loc in matching_locations:
                    if self._compare_street_paths(street, loc['street']):
                        print(f"DEBUG: Found matching street: '{loc['street']}' in cluster: {loc['cluster_name']}")
                        cluster_id = loc['cluster_id']
                        
                        # Assign location to this cluster
                        execute_write(
                            "INSERT OR REPLACE INTO location_clusters (location_id, cluster_id) VALUES (?, ?)",
                            (location_id, cluster_id)
                        )
                        return location_id, cluster_id, False

            # If no match, try proximity clustering as fallback
            print(f"DEBUG: No exact street match found, trying proximity matching")
            nearby_locations = execute_read(
                """
                SELECT l.id, l.street, lc.cluster_id, c.name as cluster_name
                FROM locations l
                LEFT JOIN location_clusters lc ON l.id = lc.location_id
                LEFT JOIN clusters c ON lc.cluster_id = c.id
                WHERE (
                    (l.lat BETWEEN ? AND ?) AND 
                    (l.lon BETWEEN ? AND ?) AND
                    l.id != ? AND
                    lc.cluster_id IS NOT NULL
                )
                """,
                (
                    lat - 0.003, lat + 0.003,  # About 300m radius
                    lon - 0.003, lon + 0.003,
                    location_id
                )
            )

            if nearby_locations:
                # Group nearby locations by cluster
                cluster_counts = {}
                for loc in nearby_locations:
                    cluster_id = loc['cluster_id']
                    if cluster_id:
                        if cluster_id not in cluster_counts:
                            cluster_counts[cluster_id] = {
                                'count': 0,
                                'name': loc['cluster_name']
                            }
                        cluster_counts[cluster_id]['count'] += 1
                
                # Find the most common cluster in the area
                max_count = 0
                nearest_cluster_id = None
                nearest_cluster_name = None
                
                for c_id, info in cluster_counts.items():
                    if info['count'] > max_count:
                        max_count = info['count']
                        nearest_cluster_id = c_id
                        nearest_cluster_name = info['name']
                
                if nearest_cluster_id:
                    print(f"DEBUG: Found nearby cluster: {nearest_cluster_name}")
                    # Only assign to nearby cluster if we have section information matching
                    # or if the location is very close (within 100m)
                    nearby_matches = False
                    
                    if section:
                        # Check if the nearby cluster has the same section
                        if section.lower() in nearest_cluster_name.lower():
                            nearby_matches = True
                    else:
                        # Check if very close (within 100m)
                        very_close = execute_read(
                            """
                            SELECT COUNT(*) as count
                            FROM locations l
                            JOIN location_clusters lc ON l.id = lc.location_id
                            WHERE lc.cluster_id = ? AND
                            (l.lat BETWEEN ? AND ?) AND 
                            (l.lon BETWEEN ?)
                            """,
                            (
                                nearest_cluster_id,
                                lat - 0.001, lat + 0.001,  # About 100m radius
                                lon - 0.001, lon + 0.001
                            ),
                            one=True
                        )
                        
                        if very_close and very_close['count'] > 0:
                            nearby_matches = True
                    
                    if nearby_matches:
                        cluster_id = nearest_cluster_id
                        # Assign to this cluster
                        execute_write(
                            "INSERT OR REPLACE INTO location_clusters (location_id, cluster_id) VALUES (?, ?)",
                            (location_id, cluster_id)
                        )
                        return location_id, cluster_id, False

            print(f"DEBUG: No matching cluster found, creating new cluster")
            # If we get here, create a new cluster
            # Determine the best name for the new cluster
            if section and subsection:
                # Create name based on development pattern and section
                if development_pattern:
                    if block:
                        cluster_name = f"{development_pattern} {block} {section}/{subsection}"
                    else:
                        cluster_name = f"{development_pattern} {section}/{subsection}"
                else:
                    cluster_name = f"{section}/{subsection}"
            elif development_pattern:
                # Just use the development name
                if block:
                    cluster_name = f"{development_pattern} {block}"
                else:
                    cluster_name = development_pattern
            elif neighborhood:
                # Fall back to neighborhood
                cluster_name = neighborhood.title()
            else:
                # Last resort - use street name
                cluster_name = street.title()

            print(f"DEBUG: Creating new cluster: {cluster_name}")

            # Insert new cluster
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
                return location_id, None, False

            # Assign location to the new cluster
            execute_write(
                "INSERT INTO location_clusters (location_id, cluster_id) VALUES (?, ?)",
                (location_id, cluster_id)
            )

            is_new_cluster = True
            print(f"DEBUG: Created new cluster with ID {cluster_id}: {cluster_name}")

            return location_id, cluster_id, is_new_cluster
            
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
        Compare full street paths for clustering.
        
        Args:
            street1 (str): First street name
            street2 (str): Second street name
            
        Returns:
            bool: True if streets match closely enough for clustering
        """
        if not street1 or not street2:
            return False
        
        # Normalize strings - lowercase and remove extra whitespace
        s1 = self._normalize_street_name(street1)
        s2 = self._normalize_street_name(street2)
        
        # Handle exact matches (after normalization)
        if s1 == s2:
            print(f"DEBUG: Exact match for '{s1}' and '{s2}'")
            return True
        
        # Extract street name, section and subsection
        street1_info = self._extract_street_parts(s1)
        street2_info = self._extract_street_parts(s2)
        
        # No match if development names don't match
        if street1_info['development'] != street2_info['development']:
            print(f"DEBUG: Development names don't match: '{street1_info['development']}' vs '{street2_info['development']}'")
            return False
        
        # Must have exact section match (e.g., U13)
        if street1_info['section'] != street2_info['section']:
            print(f"DEBUG: Sections don't match: '{street1_info['section']}' vs '{street2_info['section']}'")
            return False
        
        # Must have exact subsection match (e.g., 21)
        # This fixes the U13/12 vs U13/13 issue
        if street1_info['subsection'] != street2_info['subsection']:
            print(f"DEBUG: Subsections don't match: '{street1_info['subsection']}' vs '{street2_info['subsection']}'")
            return False
            
        print(f"DEBUG: Streets match: '{street1}' and '{street2}'")
        return True

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
        
        # Check for the pattern with a block letter before section
        # Example: "Setia Perdana D U13/27"
        block_letter_pattern = r'(.+?)\s+([A-Z])\s+([A-Z]+\d+/\d+[A-Z]?)'
        block_match = re.search(block_letter_pattern, street, re.IGNORECASE)
        
        if block_match:
            base_name = block_match.group(1).strip()
            block_letter = block_match.group(2).upper()
            section_id = block_match.group(3)
            
            # Include the block letter in the development pattern
            return f"{base_name} {block_letter}".title()
        
        # Standard pattern without block letter
        section_match = re.search(r'(.+?)\s+(?:[A-Z]+\d+/\d+[A-Z]?)', street, re.IGNORECASE)
        if section_match:
            development_name = section_match.group(1).strip()
            # Clean development name but keep block letters that are meant to be there
            development_name = re.sub(r'\s+([A-Z])\s+([A-Z])', r' \1 \2', development_name, flags=re.IGNORECASE)
            development_name = re.sub(r'\s+[A-Z]$', '', development_name, flags=re.IGNORECASE)
            return development_name.title()
        
        # Alternative pattern for section only
        alt_match = re.search(r'(.+?)\s+(?:[A-Z]+\d+)', street, re.IGNORECASE)
        if alt_match:
            development_name = alt_match.group(1).strip()
            # Clean but preserve intentional block letters
            development_name = re.sub(r'\s+([A-Z])\s+([A-Z])', r' \1 \2', development_name, flags=re.IGNORECASE)
            development_name = re.sub(r'\s+[A-Z]$', '', development_name, flags=re.IGNORECASE)
            return development_name.title()
        
        # If no section identifiers, use the whole name
        return street.strip().title()

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
        Extract street components in a more reliable way.
        
        Args:
            street (str): Normalized street name
            
        Returns:
            dict: Dictionary with 'development', 'section', 'subsection', and 'block'
        """
        result = {
            'development': '',
            'section': '',
            'subsection': '',
            'block': ''
        }
        
        # First check for block letter pattern (e.g., "setia perdana d u13/27")
        block_pattern = r'(.+?)\s+([a-z])\s+([a-z]+\d+)/(\d+[a-z]?)$'
        match = re.search(block_pattern, street, re.IGNORECASE)
        
        if match:
            result['development'] = match.group(1).strip()
            result['block'] = match.group(2).upper()
            result['section'] = match.group(3).upper()
            result['subsection'] = match.group(4)
            return result
        
        # Then check for standard pattern (e.g., "setia indah u13/12")
        section_pattern = r'(.+?)\s+([a-z]+\d+)/(\d+[a-z]?)$'
        match = re.search(section_pattern, street, re.IGNORECASE)
        
        if match:
            result['development'] = match.group(1).strip()
            result['section'] = match.group(2).upper()
            result['subsection'] = match.group(3)
            return result
        
        # Try alternate format without subsection
        alt_pattern = r'(.+?)\s+([a-z]+\d+)$'
        match = re.search(alt_pattern, street, re.IGNORECASE)
        
        if match:
            result['development'] = match.group(1).strip()
            result['section'] = match.group(2).upper()
            return result
        
        # If no pattern matches, just use the whole string as development name
        result['development'] = street.strip()
        return result

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