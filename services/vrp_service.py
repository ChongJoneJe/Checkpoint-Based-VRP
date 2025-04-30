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
    def _get_ors_client(api_key_override=None):

        key_to_use = api_key_override or current_app.config.get('ORS_API_KEY')

        if key_to_use:
            try:
                # Create and return a new client instance
                client = openrouteservice.Client(key=key_to_use)

                source = "override" if api_key_override else "config"
                print(f"[DEBUG _get_ors_client] OpenRouteService client created using {source} key.")
                return client
            except Exception as e:
                print(f"[ERROR _get_ors_client] Failed to initialize OpenRouteService client: {e}")
                return None
        else:
            print("[WARN _get_ors_client] No ORS API key provided (checked override and config).")
            return None

    @staticmethod
    def solve_vrp(warehouse, destinations, num_vehicles=1, algorithm='nearest_neighbor', api_key=None, get_detailed_geometry=True):
        """Solve static VRP using specified algorithm."""
        print(f"[DEBUG VRPService] solve_vrp called for static test. Algorithm requested: {algorithm}")
        try:
            print("[DEBUG VRPService] Initializing VehicleRoutingProblem...")
            vrp_solver = VehicleRoutingProblem(
                warehouse=warehouse,
                destinations=destinations,
                num_vehicles=num_vehicles,
                api_key=api_key
            )
            print(f"[DEBUG VRPService] Distance matrix calculated. Using road network: {vrp_solver.using_road_network}")

            solver_algorithm = algorithm
            if algorithm not in ['nearest_neighbor', 'two_opt', 'or_tools']:
                print(f"[WARNING VRPService] Unknown static algorithm '{algorithm}', defaulting to 'two_opt'.")
                solver_algorithm = 'two_opt'

            solution = vrp_solver.solve(algorithm=solver_algorithm)

            # Check for solver errors
            if 'error' in solution:
                print(f"[ERROR VRPService] Solver returned an error: {solution['error']}")
                return { 'warehouse': {...}, 'routes': [], 'error': solution['error'], 'execution_time_ms': 0 }

            routes_from_solver = solution.get('routes', [])
            total_distance_matrix_based = solution.get('distance', solution.get('total_distance', 0))
            computation_time = float(solution.get('computation_time', 0))
            distance_type = 'road_network (matrix)' if vrp_solver.using_road_network else 'haversine'
            print(f"[DEBUG VRPService] Solver finished. Distance (matrix-based): {total_distance_matrix_based:.2f} km")

            processed_routes = []
            if solution and solution.get('routes'):
                for route in solution['routes']:
                    dest_indices = route.get('stops', [])
                    route_distance = route.get('distance', 0)

                    route_coords_sequence = []
                    # Add warehouse as dict
                    if warehouse:
                        if isinstance(warehouse, (list, tuple)) and len(warehouse) >= 2:
                            route_coords_sequence.append({'lat': warehouse[0], 'lon': warehouse[1], 'type': 'warehouse'})
                        elif isinstance(warehouse, dict) and 'lat' in warehouse and 'lon' in warehouse:
                            route_coords_sequence.append({'lat': warehouse['lat'], 'lon': warehouse['lon'], 'type': 'warehouse'})

                    # Add destinations as dicts
                    for dest_index in dest_indices:
                        if 0 <= dest_index < len(destinations):
                            dest = destinations[dest_index]
                            if isinstance(dest, (list, tuple)) and len(dest) >= 2:
                                route_coords_sequence.append({'lat': dest[0], 'lon': dest[1], 'type': 'destination'})
                            elif isinstance(dest, dict) and 'lat' in dest and ('lon' in dest or 'lng' in dest):
                                lon_val = dest.get('lon') if 'lon' in dest else dest.get('lng')
                                route_coords_sequence.append({'lat': dest['lat'], 'lon': lon_val, 'type': 'destination'})
                        else:
                            print(f"[WARN solve_vrp] Invalid destination index {dest_index} found in route.")

                    if warehouse:
                        if isinstance(warehouse, (list, tuple)) and len(warehouse) >= 2:
                            route_coords_sequence.append({'lat': warehouse[0], 'lon': warehouse[1], 'type': 'warehouse'})
                        elif isinstance(warehouse, dict) and 'lat' in warehouse and 'lon' in warehouse:
                            route_coords_sequence.append({'lat': warehouse['lat'], 'lon': warehouse['lon'], 'type': 'warehouse'})

                    detailed_path_data = None
                    if api_key and get_detailed_geometry and len(route_coords_sequence) >= 2:
                        print(f"[DEBUG] Getting detailed geometry for route with {len(dest_indices)} stops...")
                        valid_coords = True
                        for idx, item in enumerate(route_coords_sequence):
                            if not isinstance(item, dict) or item.get('lat') is None or item.get('lon') is None:
                                print(f"[ERROR solve_vrp] Invalid item in route_coords_sequence at index {idx}: {item}")
                                valid_coords = False
                        if not valid_coords:
                            print("[ERROR solve_vrp] Aborting detailed path fetch due to invalid coordinates.")
                            detailed_path_data = None 
                        else:
                            detailed_path_data = VRPService.get_detailed_path(route_coords_sequence, api_key=api_key)

                    processed_routes.append({
                        'stops': dest_indices,
                        'distance': route_distance,
                        'path': route_coords_sequence,
                        'detailed_path_geometry': detailed_path_data.get('path') if detailed_path_data else None,
                        'detailed_path_distance': detailed_path_data.get('distance') if detailed_path_data else None
                    })

            final_solution = {
                'warehouse': warehouse,
                'destinations': destinations,
                'routes': processed_routes,
                'total_distance': solution.get('total_distance', 0),
                'computation_time': solution.get('computation_time', 0),
                'algorithm_used': solution.get('algorithm_used', algorithm),
                'distance_type': 'road_network' if vrp_solver.using_road_network else 'haversine' # Add distance type
            }

            print(f"[DEBUG VRPService] solve_vrp finished. Final distance: {final_solution['total_distance']:.2f} km")
            return final_solution

        except Exception as e:
            print(f"[ERROR VRPService] Exception in solve_vrp: {e}")
            traceback.print_exc()
            return {
                'warehouse': {
                    'lat': warehouse[0]['lat'] if isinstance(warehouse[0], dict) else warehouse[0],
                    'lon': warehouse[0]['lon'] if isinstance(warehouse[0], dict) else warehouse[1]
                },
                'routes': [],
                'total_distance': 0,
                'execution_time_ms': 0,
                'computation_time': 0,
                'error': str(e)
            }
    
    @staticmethod
    def get_detailed_path(route_coords_list, api_key=None):
 
        if not route_coords_list or len(route_coords_list) < 2:
            return {'path': [], 'distance': 0.0}

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
            standardized_coords = [[float(p[0]), float(p[1])] for p in route_coords_list]
        else:
            print(f"[ERROR get_detailed_path] Unrecognized coordinate format: {route_coords_list[0]}")
            return {'path': None, 'distance': 0}

        client = VRPService._get_ors_client(api_key_override=api_key)
        if not client:
            print("[WARN get_detailed_path] ORS client not available. Calculating Haversine distance as fallback.")
            total_distance = 0.0
            for i in range(len(route_coords_list) - 1):
                p1 = route_coords_list[i]
                p2 = route_coords_list[i+1]
                if p1 and p2 and 'lat' in p1 and 'lon' in p1 and 'lat' in p2 and 'lon' in p2:
                    try:
                        total_distance += VRPService._haversine_distance(float(p1['lat']), float(p1['lon']), float(p2['lat']), float(p2['lon']))
                    except (ValueError, TypeError):
                        print(f"[WARN get_detailed_path] Haversine fallback: Coordinate conversion error in segment {i}. Skipping.")
            return {'path': None, 'distance': total_distance}

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
                        start_index = 1 if not first_segment else 0
                        combined_geometry.extend(segment_geometry_latlon[start_index:])
                        first_segment = False

                        total_distance += (segment_distance_meters / 1000.0)
                    else:
                        print(f"[WARN get_detailed_path] Segment {idx+1} returned no geometry features.")
                else:
                    print(f"[WARN get_detailed_path] Segment {idx+1} ORS request failed or returned empty features.")

                time.sleep(0.5 + random.random() * 0.5)

            print(f"[DEBUG get_detailed_path] Finished processing segments. Total distance: {total_distance:.2f} km")
            return {'path': combined_geometry, 'distance': total_distance}

        except openrouteservice.exceptions.ApiError as api_err:
            print(f"[ERROR get_detailed_path] ORS API error: {api_err}. Status: {api_err.status_code}. Message: {api_err.message}")
            total_distance = sum(VRPService._haversine_distance(float(route_coords_list[i]['lat']), float(route_coords_list[i]['lon']), float(route_coords_list[i+1]['lat']), float(route_coords_list[i+1]['lon']))
                                for i in range(len(route_coords_list) - 1)
                                if all(k in route_coords_list[i] for k in ('lat','lon')) and all(k in route_coords_list[i+1] for k in ('lat','lon')))
            return {'path': None, 'distance': total_distance}
        
        except Exception as e:
            print(f"[ERROR get_detailed_path] Unexpected error during ORS directions: {e}")
            traceback.print_exc()
            total_distance = sum(VRPService._haversine_distance(float(route_coords_list[i]['lat']), float(route_coords_list[i]['lon']), float(route_coords_list[i+1]['lat']), float(route_coords_list[i+1]['lon']))
                                for i in range(len(route_coords_list) - 1)
                                if all(k in route_coords_list[i] for k in ('lat','lon')) and all(k in route_coords_list[i+1] for k in ('lat','lon')))
            return {'path': None, 'distance': total_distance}

        return {'path': combined_geometry, 'distance': total_distance}

    @staticmethod
    def _fetch_ors_directions_with_retry(client, coordinates, max_retries=5, initial_delay=0.5):
        for attempt in range(max_retries):
            try:
                route = client.directions(
                    coordinates=coordinates,
                    profile='driving-car',
                    format='geojson',
                    geometry='true'
                )
                return route
            except openrouteservice.exceptions.ApiError as api_error:
                if api_error.status_code == 429 or api_error.status_code >= 500:
                    if attempt < max_retries - 1:
                        wait_time = initial_delay * (2 ** attempt) + random.uniform(0, 0.5)
                        print(f"[WARN _fetch_ors] ORS API error (Status {api_error.status_code}). Retrying in {wait_time:.2f}s...")
                        time.sleep(wait_time)
                    else:
                        print(f"[ERROR _fetch_ors] Max retries reached after ORS API error (Status {api_error.status_code}).")
                        raise api_error
                else:
                    print(f"[ERROR _fetch_ors] ORS API Error (Status {api_error.status_code}): {api_error.message}")
                    raise api_error
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = initial_delay * (2 ** attempt) + random.uniform(0, 0.5)
                    print(f"[WARN _fetch_ors] Non-API error during ORS request: {e}. Retrying in {wait_time:.2f}s...")
                    time.sleep(wait_time)
                else:
                    print(f"[ERROR _fetch_ors] Max retries reached after non-API error: {e}")
                    raise e
        return None

    @staticmethod
    def _haversine_distance(lat1, lon1, lat2, lon2):
        import math
        
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        r = 6371
        
        return c * r
    
    @staticmethod
    def _get_route_from_ors(start, end, api_key, max_retries=5):
  
        cached_route = CacheService.get_route_cache(start, end)
        if cached_route:
            return cached_route
        
        try:
            client = openrouteservice.Client(key=api_key)
            coords = [[start[1], start[0]], [end[1], end[0]]]
            
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
                            'distance': feature['properties']['segments'][0]['distance'] / 1000,
                            'duration': feature['properties']['segments'][0]['duration'] / 60,
                        }
                        
                        CacheService.set_route_cache(start, end, route_data)
                        
                        return route_data
                    
                    return None
                    
                except Exception as e:
                    if "rate limit" in str(e).lower() and retry < max_retries - 1:
                        wait_time = (2 ** retry) + random.random()
                        print(f"[DEBUG] Rate limit hit. Waiting {wait_time:.2f} seconds...")
                        time.sleep(wait_time)
                    else:
                        raise
        
        except Exception as e:
            print(f"[DEBUG] OpenRouteService API error: {str(e)}")
            return None

    @staticmethod
    def get_detailed_route_geometry(path_sequence, api_key=None):

        if not path_sequence or len(path_sequence) < 2:
            return None

        client = VRPService._get_ors_client(api_key_override=api_key)
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
            return None
        except Exception as e:
            print(f"[ERROR get_detailed_route_geometry] Unexpected error during ORS directions: {e}")
            traceback.print_exc()
            return None

        if segments_failed > 0:
            print(f"[WARN get_detailed_route_geometry] Finished processing segments, but {segments_failed} segment(s) failed to return geometry.")

        print(f"[DEBUG get_detailed_route_geometry] Finished processing {num_segments} segments. Total points: {len(full_detailed_geometry)}. Failures: {segments_failed}.")
        return full_detailed_geometry if full_detailed_geometry else None