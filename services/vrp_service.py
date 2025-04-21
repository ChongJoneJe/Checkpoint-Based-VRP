import os
import numpy as np
import time
from algorithms.vrp import VehicleRoutingProblem
import openrouteservice
import traceback
import random
from services.cache_service import CacheService
from flask import current_app

class VRPService:
    """Service for Vehicle Routing Problem operations"""
    _ors_client = None

    @staticmethod
    def _get_ors_client(): # Removed api_key_override argument
        """Helper to get a cached ORS client instance using config."""
        if VRPService._ors_client is None:
            api_key = current_app.config.get('ORS_API_KEY')
            if api_key:
                try:
                    VRPService._ors_client = openrouteservice.Client(key=api_key)
                    print("[DEBUG _get_ors_client] OpenRouteService client initialized successfully.")
                except Exception as e:
                    print(f"[ERROR _get_ors_client] Failed to initialize OpenRouteService client: {e}")
                    VRPService._ors_client = None
            else:
                print("[WARN _get_ors_client] ORS_API_KEY not configured.")
        return VRPService._ors_client

    @staticmethod
    def solve_vrp(warehouse, destinations, num_vehicles=1, algorithm='nearest_neighbor', api_key=None, get_detailed_geometry=True):
        """Solve static VRP using specified algorithm."""
        print(f"[DEBUG VRPService] solve_vrp called for static test. Algorithm requested: {algorithm}")
        try:
            # --- Stage 1: Init Solver & Calculate Order ---
            print("[DEBUG VRPService] Initializing VehicleRoutingProblem...")
            vrp_solver = VehicleRoutingProblem(
                warehouse=warehouse,
                destinations=destinations,
                num_vehicles=num_vehicles,
                api_key=api_key
            )
            print(f"[DEBUG VRPService] Distance matrix calculated. Using road network: {vrp_solver.using_road_network}")

            # Call the solver's solve method with the chosen algorithm
            # Map UI names if necessary (e.g., 'or_tools' -> 'or_tools', 'two_opt' -> 'two_opt')
            solver_algorithm = algorithm # Assume direct mapping for static
            if algorithm not in ['nearest_neighbor', 'two_opt', 'or_tools']:
                 print(f"[WARNING VRPService] Unknown static algorithm '{algorithm}', defaulting to 'two_opt'.")
                 solver_algorithm = 'two_opt' # Default to a reasonable heuristic

            solution = vrp_solver.solve(algorithm=solver_algorithm)

            # Check for solver errors
            if 'error' in solution:
                 print(f"[ERROR VRPService] Solver returned an error: {solution['error']}")
                 # Return a basic error structure
                 return { 'warehouse': {...}, 'routes': [], 'error': solution['error'], 'execution_time_ms': 0 }


            # Extract data determined using the distance matrix
            routes_from_solver = solution.get('routes', [])
            total_distance_matrix_based = solution.get('distance', solution.get('total_distance', 0)) # Handle key variations
            computation_time = float(solution.get('computation_time', 0))
            distance_type = 'road_network (matrix)' if vrp_solver.using_road_network else 'haversine'
            print(f"[DEBUG VRPService] Solver finished. Distance (matrix-based): {total_distance_matrix_based:.2f} km")

            # --- Stage 2: Format Output & Optionally Get Detailed Geometry ---
            formatted_solution = {
                'warehouse': {
                    'lat': warehouse[0]['lat'] if isinstance(warehouse[0], dict) else warehouse[0],
                    'lon': warehouse[0]['lon'] if isinstance(warehouse[0], dict) else warehouse[1]
                },
                'routes': [],
                'total_distance': total_distance_matrix_based,
                'execution_time_ms': int(computation_time * 1000),
                'computation_time': computation_time, 
                'distance_type': distance_type
            }

            # Process each route determined by the solver
            for route_data in routes_from_solver:
                # Handle different possible return formats from solver
                if isinstance(route_data, tuple) and len(route_data) == 2:
                    route_distance_matrix_based, dest_indices = route_data
                else: # Assuming dict format like {'distance': d, 'stops': [...]}
                    route_distance_matrix_based = route_data.get('distance', 0)
                    dest_indices = route_data.get('stops', [])

                # --- Create the sequence of coordinates for this route ---
                route_coords_sequence = [ [formatted_solution['warehouse']['lat'], formatted_solution['warehouse']['lon']] ]
                # Store actual destination coordinates for this route
                route_destination_coords = []
                for dest_idx in dest_indices:
                    if dest_idx < len(destinations):
                        dest = destinations[dest_idx]
                        dest_lat = dest['lat'] if isinstance(dest, dict) else dest[0]
                        dest_lon = dest['lon'] if isinstance(dest, dict) else dest[1]
                        route_coords_sequence.append([dest_lat, dest_lon])
                        # Store coordinate object
                        route_destination_coords.append({'lat': dest_lat, 'lon': dest_lon, 'index': dest_idx})
                route_coords_sequence.append([formatted_solution['warehouse']['lat'], formatted_solution['warehouse']['lon']])

                # --- Prepare the route entry for the final solution ---
                route_entry = {
                    'stops': dest_indices, # Original 0-based indices of destinations
                    'destination_coords': route_destination_coords, # Actual destination coords
                    'distance': route_distance_matrix_based, # Distance from matrix calculation
                    # Basic path (sequence of points) as fallback
                    'path': [{'lat': coord[0], 'lon': coord[1]} for coord in route_coords_sequence]
                }

                # --- Optionally get detailed path geometry using ORS Directions ---
                if api_key and get_detailed_geometry and len(route_coords_sequence) >= 2:
                    print(f"[DEBUG] Getting detailed geometry for route with {len(dest_indices)} stops...")
                    detailed_path_data = VRPService.get_detailed_path(route_coords_sequence, api_key)

                    if detailed_path_data and detailed_path_data.get('path'):
                        # Update path with detailed geometry (list of [lon, lat])
                        # Convert ORS [lon, lat] to expected [lat, lon] for Leaflet
                        detailed_geometry_latlon = [[coord[1], coord[0]] for coord in detailed_path_data['path']]
                        route_entry['path'] = [{'lat': coord[0], 'lon': coord[1]} for coord in detailed_geometry_latlon]
                        # Update distance with more accurate sum from directions API
                        route_entry['distance'] = detailed_path_data.get('distance', route_distance_matrix_based)
                        formatted_solution['distance_type'] += ' + directions' # Indicate directions API was used
                        print(f"[DEBUG] Detailed geometry obtained. Updated distance: {route_entry['distance']:.2f} km")
                    else:
                        print("[DEBUG] Failed to get detailed geometry, using basic path.")
                elif not api_key and get_detailed_geometry:
                     print("[DEBUG] Cannot get detailed geometry: No API key provided.")


                formatted_solution['routes'].append(route_entry)

            # Recalculate total distance if detailed paths were fetched
            if api_key and get_detailed_geometry:
                 formatted_solution['total_distance'] = sum(r.get('distance', 0) for r in formatted_solution['routes'])
                 # Ensure execution time is still included even after recalculation
                 formatted_solution['execution_time_ms'] = int(computation_time * 1000)

            # Add algorithm used to the final output
            formatted_solution['algorithm_used'] = solver_algorithm

            print(f"[DEBUG VRPService] solve_vrp finished. Final distance: {formatted_solution['total_distance']:.2f} km")
            return formatted_solution

        except Exception as e:
            print(f"[ERROR VRPService] Exception in solve_vrp: {e}")
            traceback.print_exc()
            # Provide minimal valid structure in case of error
            return {
                'warehouse': {
                    'lat': warehouse[0]['lat'] if isinstance(warehouse[0], dict) else warehouse[0],
                    'lon': warehouse[0]['lon'] if isinstance(warehouse[0], dict) else warehouse[1]
                },
                'routes': [],
                'total_distance': 0,
                'execution_time_ms': 0, # Add default
                'computation_time': 0, # Add default
                'error': str(e)
            }
    
    @staticmethod
    def get_detailed_path(route_coords_list, api_key=None):
        """
        Get detailed path between a sequence of coordinates with improved rate limit handling,
        handling both list-of-lists [lat, lon] and list-of-dicts {'lat': ..., 'lon': ...}.
        """
        if not route_coords_list or len(route_coords_list) < 2:
            return {'path': [], 'distance': 0.0}

        # --- Input Type Handling ---
        # Convert input to a standardized list of [lat, lon] lists
        standardized_coords = []
        is_dict_input = False
        if isinstance(route_coords_list[0], dict):
            is_dict_input = True
            for point in route_coords_list:
                if isinstance(point, dict) and 'lat' in point and 'lon' in point:
                    standardized_coords.append([float(point['lat']), float(point['lon'])])
                else:
                    print(f"[WARN get_detailed_path] Skipping invalid dict format: {point}")
            if len(standardized_coords) < 2:
                 print("[WARN get_detailed_path] Not enough valid dict coordinates after extraction.")
                 return {'path': None, 'distance': 0}
        elif isinstance(route_coords_list[0], (list, tuple)) and len(route_coords_list[0]) == 2:
            # Assume input is already list of [lat, lon] or similar
            standardized_coords = [[float(p[0]), float(p[1])] for p in route_coords_list]
        else:
            print(f"[ERROR get_detailed_path] Unrecognized coordinate format: {route_coords_list[0]}")
            return {'path': None, 'distance': 0}
        # --- End Input Type Handling ---


        # --- Get the ORS client using the corrected helper ---
        client = VRPService._get_ors_client() # Call without argument
        if not client:
            print("[WARN get_detailed_path] ORS client not available. Calculating Haversine distance as fallback.")
            # Fallback: Calculate total Haversine distance, return None for path
            total_distance = 0.0
            for i in range(len(route_coords_list) - 1):
                p1 = route_coords_list[i]
                p2 = route_coords_list[i+1]
                if p1 and p2 and 'lat' in p1 and 'lon' in p1 and 'lat' in p2 and 'lon' in p2:
                     try:
                          total_distance += VRPService._haversine_distance(float(p1['lat']), float(p1['lon']), float(p2['lat']), float(p2['lon']))
                     except (ValueError, TypeError):
                          print(f"[WARN get_detailed_path] Haversine fallback: Coordinate conversion error in segment {i}. Skipping.")
            return {'path': None, 'distance': total_distance} # Return None path and Haversine distance
        # ---

        combined_geometry = []
        total_distance = 0.0
        first_segment = True

        try:
            for idx in range(len(route_coords_list) - 1):
                coords1 = route_coords_list[idx]
                coords2 = route_coords_list[idx+1]

                if not all(k in coords1 for k in ('lat', 'lon')) or not all(k in coords2 for k in ('lat', 'lon')):
                     print(f"[WARN get_detailed_path] Skipping segment {idx+1} due to missing coordinates.")
                     continue

                coords1_lonlat = [coords1['lon'], coords1['lat']]
                coords2_lonlat = [coords2['lon'], coords2['lat']]

                # Use the 'client' obtained above
                segment_result = client.directions(
                    coordinates=[coords1_lonlat, coords2_lonlat],
                    profile='driving-car',
                    format='geojson',
                    instructions=False,
                    geometry=True
                )

                if segment_result and 'features' in segment_result and segment_result['features']:
                    feature = segment_result['features'][0]
                    segment_geometry_lonlat = feature.get('geometry', {}).get('coordinates', [])
                    segment_distance_meters = feature.get('properties', {}).get('summary', {}).get('distance', 0)

                    if segment_geometry_lonlat:
                        # Convert [lon, lat] to [lat, lon] for Leaflet
                        segment_geometry_latlon = [[coord[1], coord[0]] for coord in segment_geometry_lonlat]

                        # Append geometry, avoiding duplication of the connecting point
                        start_index = 1 if not first_segment else 0
                        combined_geometry.extend(segment_geometry_latlon[start_index:])
                        first_segment = False

                        total_distance += (segment_distance_meters / 1000.0) # Accumulate distance in km
                        # print(f"[DEBUG get_detailed_path] Segment {idx+1} distance: {segment_distance_meters / 1000.0:.2f} km")
                    else:
                        print(f"[WARN get_detailed_path] Segment {idx+1} returned no geometry features.")
                        # If a segment fails, the combined path might become disjointed.
                        # Consider if a full fallback is better here. For now, just skip.
                else:
                    print(f"[WARN get_detailed_path] Segment {idx+1} ORS request failed or returned empty features.")
                        # Optionally: Fallback to Haversine for this segment? Or just skip? Skipping for now.

                    # Sleep briefly between requests to respect rate limits
                    time.sleep(0.5 + random.random() * 0.5) # Adjust sleep time as needed

                print(f"[DEBUG get_detailed_path] Finished processing segments. Total distance: {total_distance:.2f} km")
                return {'path': combined_geometry, 'distance': total_distance}

        except openrouteservice.exceptions.ApiError as api_err:
            print(f"[ERROR get_detailed_path] ORS API error: {api_err}. Status: {api_err.status_code}. Message: {api_err.message}")
            # Fallback for the whole path on API error
            total_distance = sum(VRPService._haversine_distance(float(route_coords_list[i]['lat']), float(route_coords_list[i]['lon']), float(route_coords_list[i+1]['lat']), float(route_coords_list[i+1]['lon']))
                                    for i in range(len(route_coords_list) - 1)
                                    if all(k in route_coords_list[i] for k in ('lat','lon')) and all(k in route_coords_list[i+1] for k in ('lat','lon')))
            return {'path': None, 'distance': total_distance}
        
        except Exception as e:
            print(f"[ERROR get_detailed_path] Unexpected error during ORS directions: {e}")
            import traceback
            traceback.print_exc()
            # Fallback for the whole path on unexpected error
            total_distance = sum(VRPService._haversine_distance(float(route_coords_list[i]['lat']), float(route_coords_list[i]['lon']), float(route_coords_list[i+1]['lat']), float(route_coords_list[i+1]['lon']))
                                    for i in range(len(route_coords_list) - 1)
                                    if all(k in route_coords_list[i] for k in ('lat','lon')) and all(k in route_coords_list[i+1] for k in ('lat','lon')))
            return {'path': None, 'distance': total_distance}

        # Return combined geometry and total distance
        return {'path': combined_geometry, 'distance': total_distance}

    @staticmethod
    def _fetch_ors_directions_with_retry(client, coordinates, max_retries=5, initial_delay=0.5):
        """Helper to fetch ORS directions with exponential backoff."""
        for attempt in range(max_retries):
            try:
                # print(f"[DEBUG _fetch_ors] Attempt {attempt+1}/{max_retries}") # Optional detailed logging
                route = client.directions(
                    coordinates=coordinates,
                    profile='driving-car',
                    format='geojson',
                    geometry='true' # Ensure geometry is requested
                    # optimize_waypoints=False # Usually false for pre-defined sequence
                )
                return route # Success
            except openrouteservice.exceptions.ApiError as api_error:
                # Check for rate limit or server errors (e.g., 429, 5xx)
                if api_error.status_code == 429 or api_error.status_code >= 500:
                    if attempt < max_retries - 1:
                        wait_time = initial_delay * (2 ** attempt) + random.uniform(0, 0.5)
                        print(f"[WARN _fetch_ors] ORS API error (Status {api_error.status_code}). Retrying in {wait_time:.2f}s...")
                        time.sleep(wait_time)
                    else:
                        print(f"[ERROR _fetch_ors] Max retries reached after ORS API error (Status {api_error.status_code}).")
                        raise api_error # Re-raise after max retries
                else:
                    # For other API errors (e.g., 400 Bad Request), don't retry
                    print(f"[ERROR _fetch_ors] ORS API Error (Status {api_error.status_code}): {api_error.message}")
                    raise api_error
            except Exception as e:
                # Handle other potential exceptions (network issues, etc.)
                if attempt < max_retries - 1:
                     wait_time = initial_delay * (2 ** attempt) + random.uniform(0, 0.5)
                     print(f"[WARN _fetch_ors] Non-API error during ORS request: {e}. Retrying in {wait_time:.2f}s...")
                     time.sleep(wait_time)
                else:
                     print(f"[ERROR _fetch_ors] Max retries reached after non-API error: {e}")
                     raise e # Re-raise after max retries
        return None # Should not be reached if exceptions are raised correctly

    @staticmethod
    def _haversine_distance(lat1, lon1, lat2, lon2):
        """Calculate the Haversine distance between two points in kilometers"""
        import math
        
        # Convert to radians
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        
        # Haversine formula
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        r = 6371  # Earth radius in km
        
        return c * r
    
    @staticmethod
    def _get_route_from_ors(start, end, api_key, max_retries=5):
        """
        Get route between two points with caching and retry logic
        
        Args:
            start: [lat, lon] coordinates of start point
            end: [lat, lon] coordinates of end point
            api_key: OpenRouteService API key
            max_retries: Maximum number of retry attempts
            
        Returns:
            dict: Route data or None if failed
        """
        # Check cache first
        cached_route = CacheService.get_route_cache(start, end)
        if cached_route:
            return cached_route
        
        # Cache miss, call API
        try:
            client = openrouteservice.Client(key=api_key)
            
            # OpenRouteService expects [lon, lat] format
            coords = [[start[1], start[0]], [end[1], end[0]]]
            
            # Try with exponential backoff for rate limits
            for retry in range(max_retries):
                try:
                    print(f"[DEBUG] ORS API call attempt {retry+1}/{max_retries}")
                    route = client.directions(
                        coordinates=coords,
                        profile='driving-car',
                        format='geojson',
                        optimize_waypoints=False
                    )
                    
                    if route and 'features' in route and len(route['features']) > 0:
                        feature = route['features'][0]
                        route_data = {
                            'geometry': feature['geometry']['coordinates'],
                            'distance': feature['properties']['segments'][0]['distance'] / 1000,  # km
                            'duration': feature['properties']['segments'][0]['duration'] / 60,  # minutes
                        }
                        
                        # Cache the result
                        CacheService.set_route_cache(start, end, route_data)
                        
                        return route_data
                    
                    # No valid route found
                    return None
                    
                except Exception as e:
                    if "rate limit" in str(e).lower() and retry < max_retries - 1:
                        wait_time = (2 ** retry) + random.random()  # Exponential backoff
                        print(f"[DEBUG] Rate limit hit. Waiting {wait_time:.2f} seconds...")
                        time.sleep(wait_time)
                    else:
                        raise  # Re-raise the exception if it's not a rate limit or last retry
        
        except Exception as e:
            print(f"[DEBUG] OpenRouteService API error: {str(e)}")
            return None

    @staticmethod
    def get_detailed_route_geometry(path_sequence, api_key=None): # Keep api_key param for potential future use
        """
        Fetches detailed route geometry segment by segment for a given path sequence.
        path_sequence: List of location dicts {'lat': ..., 'lon': ..., 'type': ...}
        Returns: List of [lat, lon] coordinates for the full path, or None on failure.
        """
        if not path_sequence or len(path_sequence) < 2:
            return None

        client = VRPService._get_ors_client() # Use cached/config client
        if not client:
            print("[WARN get_detailed_route_geometry] ORS client not available.")
            return None

        full_detailed_geometry = []
        total_distance_km = 0.0
        segments_failed = 0

        try:
            num_segments = len(path_sequence) - 1
            for j in range(num_segments):
                is_last_segment = (j == num_segments - 1)
                p1 = path_sequence[j]
                p2 = path_sequence[j+1]

                if not all(k in p1 for k in ('lat', 'lon')) or not all(k in p2 for k in ('lat', 'lon')):
                    print(f"[WARN get_detailed_route_geometry] Skipping segment {j+1} due to missing coordinates.")
                    segments_failed += 1
                    continue

                coords1_lonlat = [p1['lon'], p1['lat']]
                coords2_lonlat = [p2['lon'], p2['lat']]

                if is_last_segment:
                     print(f"[DEBUG get_detailed_route_geometry] Requesting ORS directions for LAST segment {j+1}/{num_segments} ({p1.get('type','?')}:{p1.get('matrix_idx','?')} -> {p2.get('type','?')}:{p2.get('matrix_idx','?')})...")

                segment_result = client.directions(
                    coordinates=[coords1_lonlat, coords2_lonlat],
                    profile='driving-car',
                    format='geojson',
                    instructions=False,
                    geometry=True
                )

                if segment_result and 'features' in segment_result and segment_result['features']:
                    feature = segment_result['features'][0]
                    segment_geometry_lonlat = feature.get('geometry', {}).get('coordinates', [])
                    segment_distance_meters = feature.get('properties', {}).get('summary', {}).get('distance', 0)

                    if segment_geometry_lonlat:
                        segment_geometry_latlon = [[coord[1], coord[0]] for coord in segment_geometry_lonlat]
                        start_index = 1 if j > 0 else 0
                        full_detailed_geometry.extend(segment_geometry_latlon[start_index:])
                        total_distance_km += (segment_distance_meters / 1000.0)
                        if is_last_segment:
                             print(f"[DEBUG get_detailed_route_geometry] LAST segment {j+1} successfully processed. Geometry points added: {len(segment_geometry_latlon[start_index:])}")
                    else:
                        print(f"[WARN get_detailed_route_geometry] Segment {j+1} returned no geometry. Path may be disjointed.")
                        segments_failed += 1
                else:
                    segments_failed += 1
                    if is_last_segment:
                         print(f"[WARN get_detailed_route_geometry] LAST segment {j+1} ORS request failed or returned empty features. Return-to-warehouse path may be missing.")
                    else:
                         print(f"[WARN get_detailed_route_geometry] Segment {j+1} ORS request failed or returned empty features. Path may be disjointed.")

        except openrouteservice.exceptions.ApiError as api_err:
            print(f"[ERROR get_detailed_route_geometry] ORS API error during directions: {api_err}.")
            return None # Indicate failure
        except Exception as e:
            print(f"[ERROR get_detailed_route_geometry] Unexpected error during ORS directions: {e}")
            import traceback
            traceback.print_exc()
            return None # Indicate failure

        if segments_failed > 0:
             print(f"[WARN get_detailed_route_geometry] Finished processing segments, but {segments_failed} segment(s) failed to return geometry.")

        print(f"[DEBUG get_detailed_route_geometry] Finished processing {num_segments} segments. Total points: {len(full_detailed_geometry)}. Failures: {segments_failed}.")
        return full_detailed_geometry if full_detailed_geometry else None