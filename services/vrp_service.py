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
    def get_detailed_path(route_coords, api_key=None):
        """
        Get detailed path between a sequence of coordinates with improved rate limit handling
        """
        if not api_key:
            print("[DEBUG] No API key provided, using Haversine distances")
            return {
                'path': None,
                'distance': sum(VRPService._haversine_distance(
                    route_coords[i][0], route_coords[i][1],
                    route_coords[i+1][0], route_coords[i+1][1]
                ) for i in range(len(route_coords) - 1))
            }
            
        try:
            print(f"[DEBUG] OpenRouteService request with {len(route_coords)} coordinates")
            client = openrouteservice.Client(key=api_key)
            
            # OpenRouteService expects [lon, lat] format
            ors_coords = [[point[1], point[0]] for point in route_coords]
            
            # Check if we have too many coordinates
            if len(ors_coords) > 50:  # ORS has a limit on the number of waypoints
                print(f"[DEBUG] Splitting {len(ors_coords)} coordinates into segments (max 50 per request)")
                
                # Split into segments
                segments = []
                for i in range(0, len(ors_coords), 49):
                    segment = ors_coords[i:i+50]
                    if len(segment) >= 2:  # Need at least start and end
                        segments.append(segment)
                
                print(f"[DEBUG] Created {len(segments)} segments")
                
                # Process each segment
                combined_geometry = []
                total_distance = 0
                
                for idx, segment in enumerate(segments):
                    print(f"[DEBUG] Processing segment {idx+1}/{len(segments)} with {len(segment)} points")
                    
                    # Use exponential backoff for rate limit handling
                    max_retries = 5
                    retry_delay = 1.0
                    
                    for retry in range(max_retries):
                        try:
                            print(f"[DEBUG] API call attempt {retry+1}/{max_retries}")
                            route = client.directions(
                                coordinates=segment,
                                profile='driving-car',
                                format='geojson',
                                optimize_waypoints=False
                            )
                            break
                        except Exception as e:
                            if retry < max_retries - 1:
                                wait_time = retry_delay * (2 ** retry) + random.random()
                                print(f"[DEBUG] API error: {str(e)}. Retrying in {wait_time:.2f} seconds")
                                time.sleep(wait_time)
                            else:
                                print(f"[DEBUG] Max retries reached. Error: {str(e)}")
                                raise
                    
                    if 'features' in route and len(route['features']) > 0:
                        feature = route['features'][0]
                        combined_geometry.extend(feature['geometry']['coordinates'])
                        segment_distance = feature['properties']['segments'][0]['distance'] / 1000
                        total_distance += segment_distance
                        print(f"[DEBUG] Segment {idx+1} distance: {segment_distance:.2f} km")
                    
                    # Sleep to avoid rate limiting
                    time.sleep(1.0 + random.random())
                
                return {
                    'path': combined_geometry,
                    'distance': total_distance
                }
            else:
                print(f"[DEBUG] Single request for {len(ors_coords)} points")
                
                # Try up to 5 times with exponential backoff
                max_retries = 5
                for retry in range(max_retries):
                    try:
                        print(f"[DEBUG] API call attempt {retry+1}/{max_retries}")
                        route = client.directions(
                            coordinates=ors_coords,
                            profile='driving-car',
                            format='geojson',
                            optimize_waypoints=False
                        )
                        break
                    except Exception as e:
                        if retry < max_retries - 1:
                            wait_time = 1.0 * (2 ** retry) + random.random()
                            print(f"[DEBUG] API error: {str(e)}. Retrying in {wait_time:.2f} seconds")
                            time.sleep(wait_time)
                        else:
                            print(f"[DEBUG] Max retries reached. Error: {str(e)}")
                            raise
                
                if 'features' in route and len(route['features']) > 0:
                    feature = route['features'][0]
                    route_distance = feature['properties']['segments'][0]['distance'] / 1000
                    print(f"[DEBUG] Route distance: {route_distance:.2f} km")
                    
                    return {
                        'path': feature['geometry']['coordinates'],
                        'distance': route_distance
                    }
                
            return {'path': None, 'distance': 0}
        except Exception as e:
            print(f"[DEBUG] OpenRouteService API error: {str(e)}")
            print("[DEBUG] Falling back to Haversine distances")
            
            # Calculate distance using Haversine formula
            total_distance = 0
            for i in range(len(route_coords) - 1):
                segment_distance = VRPService._haversine_distance(
                    route_coords[i][0], route_coords[i][1],
                    route_coords[i+1][0], route_coords[i+1][1]
                )
                total_distance += segment_distance
                
            return {'path': None, 'distance': total_distance}
    
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
    def _get_ors_client(api_key=None):
        """Gets an ORS client instance."""
        if not api_key:
            api_key = current_app.config.get('ORS_API_KEY')
        if not api_key:
            print("[WARN _get_ors_client] ORS API key not available.")
            return None
        try:
            return openrouteservice.Client(key=api_key)
        except Exception as e:
            print(f"[ERROR _get_ors_client] Failed to create ORS client: {e}")
            return None

    @staticmethod
    def get_detailed_route_geometry(coords_sequence, api_key=None):
        """
        Gets detailed route geometry from ORS Directions API for a sequence of coordinates.

        Args:
            coords_sequence (list): List of coordinate dicts [{'lat': float, 'lon': float}, ...].
            api_key (str, optional): ORS API key. Defaults to config.

        Returns:
            list: List of [lat, lon] points for the detailed path, or None if failed.
        """
        # --- ADD DEBUG ---
        print(f"[DEBUG get_detailed_route_geometry] Function called with {len(coords_sequence)} coordinates.")
        # print(f"[DEBUG get_detailed_route_geometry] Coords: {coords_sequence}") # Optional: print full list if needed
        # --- END DEBUG ---

        if len(coords_sequence) < 2:
            print("[DEBUG get_detailed_route_geometry] Too few coordinates, returning None.") # Add debug
            return None # Cannot route with fewer than 2 points

        client = VRPService._get_ors_client(api_key)
        if not client:
            print("[ERROR get_detailed_route_geometry] ORS client not available.")
            return None

        # ORS expects [lon, lat]
        ors_coords = [[float(p['lon']), float(p['lat'])] for p in coords_sequence]

        try:
            print(f"[DEBUG get_detailed_route_geometry] Requesting ORS directions for {len(ors_coords)} points.")
            # Note: ORS Directions has waypoint limits (typically 50).
            # This simple version doesn't handle splitting large routes yet.
            # Consider adding segmentation logic similar to the old get_detailed_path if needed.
            if len(ors_coords) > 50:
                 print(f"[WARN get_detailed_route_geometry] Route has {len(ors_coords)} waypoints, exceeding typical ORS limit of 50. Request might fail or be slow. Segmentation not implemented here.")

            route_result = client.directions(
                coordinates=ors_coords,
                profile='driving-car',
                geometry='true', # Request geometry
                format='geojson' # GeoJSON includes coordinates directly
            )

            # Extract geometry coordinates
            if route_result and 'features' in route_result and route_result['features']:
                geometry = route_result['features'][0].get('geometry')
                if geometry and geometry.get('type') == 'LineString':
                    # Coordinates are [lon, lat], swap back to [lat, lon] for Leaflet
                    detailed_path = [[coord[1], coord[0]] for coord in geometry['coordinates']]
                    # --- ADD DEBUG ---
                    print(f"[DEBUG get_detailed_route_geometry] Returning detailed path with {len(detailed_path)} points.")
                    # --- END DEBUG ---
                    return detailed_path
                else:
                     print("[WARN get_detailed_route_geometry] ORS response missing LineString geometry.")
                     # --- ADD DEBUG ---
                     print("[DEBUG get_detailed_route_geometry] Returning None (missing geometry).")
                     # --- END DEBUG ---
                     return None
            else:
                print("[WARN get_detailed_route_geometry] ORS directions response format unexpected or empty.")
                # --- ADD DEBUG ---
                print("[DEBUG get_detailed_route_geometry] Returning None (bad response format).")
                # --- END DEBUG ---
                return None

        except openrouteservice.exceptions.ApiError as api_error:
            print(f"[ERROR get_detailed_route_geometry] ORS API Error: {api_error}. Status: {api_error.status_code}. Message: {api_error.message}")
            # --- ADD DEBUG ---
            print("[DEBUG get_detailed_route_geometry] Returning None (API Error).")
            # --- END DEBUG ---
            return None
        except Exception as e:
            print(f"[ERROR get_detailed_route_geometry] Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            # --- ADD DEBUG ---
            print("[DEBUG get_detailed_route_geometry] Returning None (Unexpected Error).")
            # --- END DEBUG ---
            return None