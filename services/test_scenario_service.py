from flask import current_app
import os
import sqlite3
import json
import time
import traceback
import numpy as np
import math
from services.vrp_service import VRPService
from services.vrp_testing_service import VRPTestingService
from algorithms.enhanced_vrp import EnhancedVehicleRoutingProblem, HAS_ORTOOLS
from services.cache_service import CacheService
import random
from math import radians, sin, cos, sqrt, atan2
import openrouteservice
from datetime import datetime

class VRPTestScenarioService:

    @staticmethod
    def prepare_test_data(snapshot_id, preset_id, api_key=None):
        # --- Add Input Validation ---
        if not snapshot_id or not isinstance(snapshot_id, str):
            print(f"[ERROR prepare_test_data] Invalid snapshot_id: {snapshot_id}")
            return {'status': 'error', 'message': 'Invalid or missing snapshot ID'}
        if not preset_id or not isinstance(preset_id, str):
            print(f"[ERROR prepare_test_data] Invalid preset_id: {preset_id}")
            return {'status': 'error', 'message': 'Invalid or missing preset ID'}
        # --- End Input Validation ---

        cache_service = CacheService()
        cache_key = f"checkpoint_matrix_{snapshot_id}_{preset_id}"
        print(f"[DEBUG prepare_test_data] Using cache key: {cache_key}") # Add logging

        try:
            snapshot_path = os.path.join(current_app.root_path, "vrp_test_data", snapshot_id)
            preset_data = VRPTestingService.get_preset_from_snapshot(snapshot_path, preset_id)
            if not preset_data:
                return None

            conn = sqlite3.connect(snapshot_path)
            conn.row_factory = sqlite3.Row

            warehouse_query = """
                SELECT l.id, l.lat, l.lon, l.street, l.neighborhood, l.development
                FROM locations l
                JOIN preset_locations pl ON l.id = pl.location_id
                WHERE pl.preset_id = ? AND pl.is_warehouse = 1
                LIMIT 1
            """
            warehouse_row = conn.execute(warehouse_query, (preset_id,)).fetchone()
            warehouse = {
                'id': warehouse_row['id'],
                'lat': warehouse_row['lat'],
                'lon': warehouse_row['lon'],
                'street': warehouse_row['street'],
                'neighborhood': warehouse_row['neighborhood'],
                'development': warehouse_row['development']
            } if warehouse_row else None

            if not warehouse:
                conn.close()
                print("Error: Warehouse not found for preset.")
                return None

            destinations_query = """
                SELECT l.id, l.lat, l.lon, l.street, l.neighborhood, l.development, 
                       lc.cluster_id, c.name as cluster_name
                FROM locations l
                JOIN preset_locations pl ON l.id = pl.location_id
                LEFT JOIN location_clusters lc ON l.id = lc.location_id
                LEFT JOIN clusters c ON lc.cluster_id = c.id
                WHERE pl.preset_id = ? AND pl.is_warehouse = 0
            """
            destinations = [
                {
                    'id': row['id'],
                    'lat': row['lat'],
                    'lon': row['lon'],
                    'street': row['street'],
                    'neighborhood': row['neighborhood'],
                    'development': row['development'],
                    'cluster_id': row['cluster_id'],
                    'cluster_name': row['cluster_name']
                }
                for row in conn.execute(destinations_query, (preset_id,))
            ]

            required_clusters = {dest['cluster_id'] for dest in destinations if dest['cluster_id']}

            if not required_clusters:
                return {
                    'warehouse': warehouse,
                    'destinations': destinations,
                    'clusters': [],
                    'checkpoints': [],
                    'has_clusters': False
                }

            checkpoints_query = """
                SELECT cp.id, cp.lat, cp.lon, cp.cluster_id,
                       cp.confidence, c.name as cluster_name
                FROM security_checkpoints cp
                JOIN clusters c ON cp.cluster_id = c.id
                WHERE cp.cluster_id IN ({})
            """.format(','.join('?' * len(required_clusters)))

            # --- Checkpoint Query ---
            try:
                print(f"[DEBUG prepare_test_data] Executing checkpoints query for clusters: {list(required_clusters)}") # Log before query
                checkpoints_rows = conn.execute(checkpoints_query, list(required_clusters)).fetchall()
                print(f"[DEBUG prepare_test_data] Found {len(checkpoints_rows)} raw checkpoints from DB.")
            except sqlite3.OperationalError as db_error:
                print(f"Database error executing checkpoints query: {db_error}")
                conn.close()
                return {'status': 'error', 'message': f"DB error fetching checkpoints: {db_error}"}
            except Exception as query_error:
                print(f"[ERROR prepare_test_data] Unexpected error executing checkpoints query: {query_error}")
                traceback.print_exc() # Print full traceback for query error
                conn.close()
                return {'status': 'error', 'message': f"Error fetching checkpoints: {query_error}"}
            # --- End Checkpoint Query ---

            active_routing_checkpoints = []
            checkpoint_coord_to_clusters = {} # Map "lat,lon" -> [cluster_ids]

            for cp in checkpoints_rows:
                cp_id, cp_lat, cp_lon, cp_cluster_id, cp_confidence, cluster_name = cp
                clusters_served = [cp_cluster_id] if cp_cluster_id else []
                cp_dict = {
                    'id': cp_id,
                    'lat': cp_lat,
                    'lon': cp_lon,
                    'clusters': clusters_served, # Keep original cluster list if needed elsewhere
                    'clusters_served': clusters_served, # Explicitly add for solver post-processing clarity
                    'type': 'checkpoint' # Add type field
                }
                active_routing_checkpoints.append(cp_dict)
                coord_key = f"{cp_lat:.6f},{cp_lon:.6f}"
                checkpoint_coord_to_clusters[coord_key] = clusters_served

            cluster_to_checkpoints = {}
            checkpoint_to_clusters = {}

            for cp in checkpoints_rows:
                cluster_id = cp['cluster_id']
                cluster_to_checkpoints.setdefault(cluster_id, []).append(cp)
                cp_key = f"{cp['lat']:.6f},{cp['lon']:.6f}"
                checkpoint_to_clusters.setdefault(cp_key, []).append(cluster_id)

            unique_checkpoints = {}
            for cp in checkpoints_rows:
                # Access columns directly by name using dictionary-style access
                cp_lat = cp['lat']
                cp_lon = cp['lon']
                cp_cluster_id = cp['cluster_id']
                # --- CORRECTED ACCESS ---
                cp_confidence = cp['confidence'] # Direct access
                # Access optional columns by checking keys first
                from_type = cp['from_road_type'] if 'from_road_type' in cp.keys() else None
                to_type = cp['to_road_type'] if 'to_road_type' in cp.keys() else None
                # --- END CORRECTION ---

                cp_key = f"{cp_lat:.6f},{cp_lon:.6f}"
                if cp_key not in unique_checkpoints:
                    unique_checkpoints[cp_key] = {
                        'id': cp['id'],
                        'lat': cp_lat,
                        'lon': cp_lon,
                        'clusters': [cp_cluster_id],
                        'from_type': from_type,
                        'to_type': to_type,
                        'confidence': cp_confidence,
                        'type': 'checkpoint' # Ensure type is added
                    }
                elif cp_cluster_id not in unique_checkpoints[cp_key]['clusters']:
                    unique_checkpoints[cp_key]['clusters'].append(cp_cluster_id)

            active_routing_checkpoints = list(unique_checkpoints.values())

            if not active_routing_checkpoints or len(active_routing_checkpoints) == 0:
                return {
                    'status': 'error', 
                    'message': 'No valid checkpoints found for the required clusters. Please create checkpoints for these clusters first.'
                }
            
            covered_clusters = set()
            for cp in active_routing_checkpoints:
                covered_clusters.update(cp.get('clusters', []))
            
            missing_clusters = required_clusters - covered_clusters
            if missing_clusters:
                return {
                    'status': 'error',
                    'message': f'Missing checkpoints for clusters: {", ".join(map(str, missing_clusters))}. Please create checkpoints for these clusters.'
                }

            # --- Distance Matrix Calculation ---
            # Always try ORS if api_key is present, raise error on failure
            distance_type = 'unknown'
            checkpoint_distance_matrix = None
            ors_client = VRPService._get_ors_client() # Use helper to get client

            if ors_client:
                try:
                    print("[DEBUG prepare_test_data] Using OpenRouteService for checkpoint distance matrix.")
                    # --- CORRECTED CALL ---
                    # Combine warehouse and checkpoints into a single list for the matrix calculation
                    all_locations_for_matrix = [warehouse] + active_routing_checkpoints
                    print(f"[DEBUG prepare_test_data] Calculating matrix for {len(all_locations_for_matrix)} total locations (warehouse + checkpoints).")

                    # Pass the combined list and the client
                    # The helper function now returns a NumPy array directly or None
                    checkpoint_distance_matrix = VRPTestScenarioService._calculate_ors_distance_matrix(
                        all_locations_for_matrix, ors_client
                    )
                    # --- END CORRECTION ---

                    # --- ADJUSTED CHECK ---
                    # Check if the helper function returned None (indicating an error)
                    if checkpoint_distance_matrix is None:
                        print(f"[ERROR prepare_test_data] _calculate_ors_distance_matrix returned None.")
                        conn.close()
                        return {'status': 'error', 'message': "Failed to calculate ORS distance matrix."}
                    # --- END ADJUSTMENT ---

                    # If successful, the matrix is already a NumPy array
                    distance_type = 'road_network'
                    print("[DEBUG prepare_test_data] Successfully calculated ORS distance matrix.")

                except Exception as e:
                    # Catch potential errors from _calculate_ors_distance_matrix (like ValueError for invalid locations)
                    print(f"[ERROR prepare_test_data] Failed during ORS distance matrix calculation: {e}")
                    conn.close()
                    return {'status': 'error', 'message': f"Failed during ORS distance matrix calculation: {e}"}
            else:
                # No API key or client creation failed
                print("[ERROR prepare_test_data] ORS client not available. Cannot calculate road network distances.")
                conn.close()
                return {'status': 'error', 'message': "ORS client/API key not available for distance calculation."}
            # --- End Distance Matrix ---

            conn.close() # Close DB connection after use

            # --- Prepare idx_to_cluster_set mapping ---
            # This map uses the matrix index (0=warehouse, 1=cp1, 2=cp2, ...)
            idx_to_cluster_set = {}
            # Warehouse (index 0) serves no clusters
            idx_to_cluster_set[0] = set()
            # Checkpoints (index 1 onwards)
            for idx, cp_data in enumerate(active_routing_checkpoints, 1):
                 # Use the 'clusters' list from the unique_checkpoints dictionary
                 idx_to_cluster_set[idx] = set(cp_data.get('clusters', []))
            # --- End idx_to_cluster_set mapping ---


            prepared_dataset = {
                'warehouse': warehouse,
                'destinations': destinations,
                'required_clusters': list(required_clusters),
                'active_routing_checkpoints': active_routing_checkpoints,
                # Store checkpoints by their matrix index (1 to N) for easier lookup later
                'checkpoint_indices': {idx + 1: cp for idx, cp in enumerate(active_routing_checkpoints)},
                'checkpoint_to_clusters': checkpoint_to_clusters, # Original mapping by coord string
                'idx_to_cluster_set': idx_to_cluster_set, # New mapping by matrix index
                'checkpoint_distance_matrix': checkpoint_distance_matrix, # Store as NumPy array
                'has_clusters': True,
                'distance_type': distance_type,
                'api_key': api_key, # Pass API key for potential detailed path fetching
                'db_path': snapshot_path # Pass snapshot path for dynamic insertions
            }

            return prepared_dataset
        except Exception as e:
            traceback.print_exc()
            if 'conn' in locals() and conn:
                conn.close()
            # Return a structured error
            return {'status': 'error', 'message': f"Unexpected error preparing data: {e}"}

    @staticmethod
    def _calculate_ors_distance_matrix(locations, ors_client):
        """Calculates distance matrix using OpenRouteService."""
        print(f"[DEBUG _calculate_ors_distance_matrix] Received locations list with length: {len(locations)}")

        # --- Add check for None or invalid items ---
        valid_locations = []
        invalid_indices = []
        for i, loc in enumerate(locations):
            if loc and isinstance(loc, dict) and 'lat' in loc and 'lon' in loc:
                valid_locations.append(loc)
            else:
                print(f"[ERROR _calculate_ors_distance_matrix] Invalid location data at index {i}: {loc}")
                invalid_indices.append(i)

        # If invalid locations found, do not proceed
        if invalid_indices:
            raise ValueError(f"Invalid location data found at indices {invalid_indices} when calculating matrix.")
        # --- End check ---


        if len(valid_locations) < 2:
            print(f"[WARN _calculate_ors_distance_matrix] Insufficient valid locations ({len(valid_locations)}) provided.")
            return None # Return None if not enough valid locations

        coordinates = [[loc['lon'], loc['lat']] for loc in valid_locations] # ORS expects lon, lat
        num_coords = len(coordinates)
        print(f"[DEBUG _calculate_ors_distance_matrix] Requesting matrix for {num_coords} valid locations.")

        # --- DEBUG PRINTS (can be removed after fix) ---
        print(f"[DEBUG _calculate_ors_distance_matrix] Type of ors_client: {type(ors_client)}")
        # print(f"[DEBUG _calculate_ors_distance_matrix] Attributes of ors_client: {dir(ors_client)}")
        # --- END DEBUG PRINTS ---

        try:
            # --- CORRECTED METHOD NAME ---
            matrix_result = ors_client.distance_matrix( # Changed from .matrix
                locations=coordinates,
                metrics=['distance'],
                units='km'
            )
            # --- END CORRECTION ---

            if not matrix_result or 'distances' not in matrix_result:
                print("[ERROR _calculate_ors_distance_matrix] ORS response missing 'distances' or empty.")
                return None

            distances = matrix_result.get('distances')
            if not distances:
                 print("[ERROR _calculate_ors_distance_matrix] 'distances' field in ORS response is empty.")
                 return None

            # --- Validate shape BEFORE logging success ---
            matrix_array = np.array(distances)
            expected_shape = (num_coords, num_coords)
            if matrix_array.shape == expected_shape:
                print(f"[DEBUG _calculate_ors_distance_matrix] Received valid matrix response with shape {matrix_array.shape}.")
                return matrix_array # Return the valid numpy array
            else:
                print(f"[ERROR _calculate_ors_distance_matrix] ORS response matrix shape mismatch. Got {matrix_array.shape}, expected {expected_shape}.")
                return None # Return None if shape is wrong

        except Exception as e:
            print(f"[ERROR _calculate_ors_distance_matrix] ORS API call failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    @staticmethod
    def _calculate_cluster_centroid(cluster_id, destinations):
        """Helper to calculate the centroid of destinations for a given cluster."""
        cluster_locs = [
            (loc['lat'], loc['lon']) for loc in destinations
            if loc.get('cluster_id') == cluster_id and 'lat' in loc and 'lon' in loc
        ]
        if not cluster_locs:
            return None
        avg_lat = sum(lat for lat, lon in cluster_locs) / len(cluster_locs)
        avg_lon = sum(lon for lat, lon in cluster_locs) / len(cluster_locs)
        return {'lat': avg_lat, 'lon': avg_lon}

    @staticmethod
    def run_checkpoint_vrp_scenario(prepared_data, num_vehicles=1, algorithm='or_tools'):
        """Run a checkpoint-based VRP scenario using EnhancedVRP."""
        print(f"[DEBUG TestScenarioService] run_checkpoint_vrp_scenario called. Algorithm: {algorithm}, Vehicles: {num_vehicles}")
        if not prepared_data or prepared_data.get('status') == 'error':
            err_msg = prepared_data.get('message', 'Invalid prepared data') if isinstance(prepared_data, dict) else 'Invalid prepared data'
            print(f"[ERROR TestScenarioService] Invalid prepared data: {err_msg}")
            return {'status': 'error', 'message': err_msg}
        if not prepared_data.get('has_clusters'):
             print("[ERROR TestScenarioService] Prepared data missing cluster information.")
             return {'status': 'error', 'message': 'Prepared data does not contain cluster/checkpoint info'}

        start_time = time.time()

        try:
            print("[DEBUG TestScenarioService] Initializing EnhancedVehicleRoutingProblem...")
            # PASS num_vehicles to constructor
            enhanced_vrp_solver = EnhancedVehicleRoutingProblem(
                warehouse=prepared_data['warehouse'],
                destinations=prepared_data['destinations'],
                num_vehicles=num_vehicles # Pass it here
            )

            # Ensure distance matrix is NumPy array before passing to solver
            if isinstance(prepared_data.get('checkpoint_distance_matrix'), list):
                 prepared_data['checkpoint_distance_matrix'] = np.array(prepared_data['checkpoint_distance_matrix'])
            elif prepared_data.get('checkpoint_distance_matrix') is None:
                 print("[ERROR TestScenarioService] Checkpoint distance matrix is missing in prepared_data.")
                 return {'status': 'error', 'message': 'Checkpoint distance matrix is missing.'}


            # Call the enhanced solver's solve method
            solution = enhanced_vrp_solver.solve(prepared_data, algorithm=algorithm)

            # Check for solver errors
            solver_error_message = solution.get('error')
            if solver_error_message is not None or not solution.get('routes'):
                 error_msg_to_report = solver_error_message if solver_error_message is not None else 'Solver failed to find any routes.'
                 print(f"[ERROR TestScenarioService] Enhanced solver failed: {error_msg_to_report}")
                 # Add timing info even to error response
                 solution['execution_time_ms'] = int((time.time() - start_time) * 1000)
                 # Ensure status is set correctly
                 solution['status'] = 'error'
                 solution['message'] = str(error_msg_to_report)
                 return solution # Return the error dict from the solver

            # --- Fetch Detailed Path Geometry ---
            api_key = prepared_data.get('api_key')
            if api_key and solution.get('routes'):
                print("[DEBUG run_checkpoint_vrp_scenario] Fetching detailed route geometry...")
                for i, route in enumerate(solution['routes']):
                    path_sequence = route.get('path') # Get the sequence of stops including warehouse
                    if path_sequence and len(path_sequence) >= 2:
                        print(f"[DEBUG run_checkpoint_vrp_scenario] Processing route {i+1} (length {len(path_sequence)}) for detailed path.")
                        try:
                            # --- USE VRPService HELPER ---
                            route_detailed_geometry = VRPService.get_detailed_route_geometry(path_sequence, api_key)
                            # ---

                            if route_detailed_geometry:
                                print(f"[DEBUG run_checkpoint_vrp_scenario]   Route {i+1} final detailed geometry points: {len(route_detailed_geometry)}")
                                solution['routes'][i]['detailed_path_geometry'] = route_detailed_geometry
                            else:
                                print(f"[WARN run_checkpoint_vrp_scenario]   Route {i+1} failed to generate detailed geometry (returned None).")
                                solution['routes'][i]['detailed_path_geometry'] = None # Ensure it's None if failed
                        except Exception as geo_err:
                             print(f"[ERROR run_checkpoint_vrp_scenario]   Error fetching detailed geometry for route {i+1}: {geo_err}")
                             solution['routes'][i]['detailed_path_geometry'] = None
                    else:
                         print(f"[WARN run_checkpoint_vrp_scenario]   Route {i+1} has insufficient path points ({len(path_sequence or [])}) for detailed geometry.")
                         solution['routes'][i]['detailed_path_geometry'] = None
            elif not api_key:
                 print("[WARN run_checkpoint_vrp_scenario] No API key provided, skipping detailed geometry fetch.")
                 # Ensure geometry is None if skipped
                 if 'routes' in solution and solution['routes']:
                     for i in range(len(solution['routes'])):
                         solution['routes'][i]['detailed_path_geometry'] = None
            # --- End Detailed Path ---

            end_time = time.time()
            computation_time = end_time - start_time

            # Add timing and distance type info to the solution
            # Solver already adds 'execution_time_ms' based on its internal timing
            # We add overall scenario time here if needed, or rely on solver's time
            # solution['scenario_execution_time_ms'] = int(computation_time * 1000)
            solution['distance_type'] = prepared_data.get('distance_type', 'unknown')
            # algorithm_used is already added by solve()

            print(f"[DEBUG TestScenarioService] Checkpoint scenario finished. Algorithm used: {solution.get('algorithm_used', 'N/A')}, Total distance: {solution.get('total_distance', 0):.2f} km")
            solution['status'] = 'success' # Ensure status is success
            return solution

        except (ValueError, ConnectionError, RuntimeError) as e:
             # Catch errors from distance matrix calculation or ORS API in prepare_data or solver
             print(f"[ERROR TestScenarioService] Handled error during VRP solving or ORS communication: {e}")
             traceback.print_exc()
             return {'status': 'error', 'message': str(e), 'execution_time_ms': int((time.time() - start_time) * 1000)}
        except Exception as e:
             print(f"[ERROR TestScenarioService] Unexpected exception in run_checkpoint_vrp_scenario: {e}")
             traceback.print_exc()
             return {
                 'status': 'error',
                 'message': f"Unexpected error running checkpoint scenario: {e}",
                 'execution_time_ms': int((time.time() - start_time) * 1000)
             }


    @staticmethod
    def insert_dynamic_locations(current_solution, prepared_data, new_location_pairs, target_vehicle_index, insertion_point_index, algorithm='or_tools'):
        """
        Insert new location pairs into an existing solution by re-solving the
        remainder of the target vehicle's route from a specified insertion point.

        Args:
            current_solution: The original solution dictionary.
            prepared_data: The original prepared data dictionary (used for context).
            new_location_pairs: List of {pickup: {...}, dropoff: {...}} dictionaries.
            target_vehicle_index: Index of the vehicle route to modify.
            insertion_point_index: Index of the stop in the original route *after* which
                                   to insert (0 means after warehouse). The driver is assumed
                                   to be *at* the stop corresponding to this index.
            algorithm: Routing algorithm to use ('or_tools', 'heuristic', etc.).

        Returns:
            Dictionary containing the updated solution or an error.
        """
        start_time = time.time()
        print(f"[DEBUG insert_dynamic_locations] Start Re-Solve. Target Vehicle: {target_vehicle_index}, At Stop Index: {insertion_point_index}")

        # --- Basic Validation ---
        if not current_solution or not prepared_data or not new_location_pairs:
            return {'status': 'error', 'message': 'Missing required data for dynamic insertion'}
        if target_vehicle_index < 0 or target_vehicle_index >= len(current_solution.get('routes', [])):
            return {'status': 'error', 'message': f'Invalid target vehicle index: {target_vehicle_index}'}
        db_path = prepared_data.get('db_path')
        if not db_path or not os.path.exists(db_path):
            return {'status': 'error', 'message': 'Invalid or missing snapshot database path'}
        # --- End Validation ---

        conn = None
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row

            original_route = current_solution['routes'][target_vehicle_index]
            original_warehouse = prepared_data['warehouse']
            api_key = prepared_data.get('api_key')
            ors_client = VRPService._get_ors_client()

            # --- Identify Current Location and Remaining Stops ---
            # Check if the original route used checkpoints based on the presence of 'stops'
            is_checkpoint_route = bool(original_route.get('stops'))
            # Get the sequence of stops visited (checkpoints or destinations)
            original_stops_sequence = original_route.get('stops', []) if is_checkpoint_route else original_route.get('path', [])[1:-1] # Exclude warehouse for static

            if insertion_point_index < 0 or insertion_point_index > len(original_stops_sequence):
                 return {'status': 'error', 'message': f'Invalid insertion point index: {insertion_point_index} for {len(original_stops_sequence)} stops.'}

            # Determine the starting point (current location) for the re-solve
            if insertion_point_index == 0:
                current_location = original_warehouse.copy() # Start from warehouse
                current_location['type'] = 'warehouse' # Ensure type
                original_segment_completed_path = [current_location] # Path segment already done
            else:
                # Driver is AT the stop corresponding to insertion_point_index - 1 in the sequence
                current_stop_index_in_list = insertion_point_index - 1
                if current_stop_index_in_list >= len(original_stops_sequence):
                     return {'status': 'error', 'message': f'Insertion point index {insertion_point_index} is out of bounds for the route stops.'}
                current_location = original_stops_sequence[current_stop_index_in_list].copy()
                # Ensure lat/lon are present
                if 'lat' not in current_location or 'lon' not in current_location:
                     return {'status': 'error', 'message': f'Current stop at index {current_stop_index_in_list} lacks coordinates.'}
                # Determine the path segment already completed (warehouse up to and including current stop)
                # The original path includes warehouse at start and end
                original_segment_completed_path = original_route.get('path', [])[:insertion_point_index + 1]

            # Identify remaining original stops for this vehicle (those after the current location)
            remaining_original_stops = original_stops_sequence[insertion_point_index:]

            print(f"[DEBUG insert_dynamic_locations] Re-solve starts from: {current_location.get('type')} ({current_location['lat']:.4f}, {current_location['lon']:.4f})")
            print(f"[DEBUG insert_dynamic_locations] Remaining original stops: {len(remaining_original_stops)}")

            # --- Prepare New Dynamic Destinations ---
            new_dynamic_stops_for_subproblem = []
            # Indices relative to the subproblem matrix will be calculated later

            for pair_idx, pair in enumerate(new_location_pairs):
                pickup = pair['pickup']
                dropoff = pair['dropoff']
                # Ensure in DB (optional here if already done, but safe)
                VRPTestScenarioService._ensure_location_in_snapshot(conn, pickup['lat'], pickup['lon'], pickup.get('address'), pickup.get('cluster_id'))
                VRPTestScenarioService._ensure_location_in_snapshot(conn, dropoff['lat'], dropoff['lon'], dropoff.get('address'), dropoff.get('cluster_id'))

                # Create entries for the subproblem list, include necessary details
                pickup_stop = {**pickup, 'id': f"DYN_P_{pair_idx}", 'type': 'pickup', 'is_dynamic': True}
                dropoff_stop = {**dropoff, 'id': f"DYN_D_{pair_idx}", 'type': 'dropoff', 'is_dynamic': True}
                new_dynamic_stops_for_subproblem.extend([pickup_stop, dropoff_stop])

            # --- Determine end_cp_data (End point for the subproblem) ---
            # This logic determines where the re-solved route should end.
            # Usually, it's the next stop in the original route, or the warehouse if it was the last stop.
            warehouse_coords = original_warehouse # Use the full warehouse dict
            if not warehouse_coords or 'lat' not in warehouse_coords or 'lon' not in warehouse_coords:
                 raise ValueError("Warehouse coordinates missing or invalid in prepared data.")

            end_cp_data = None
            # Check if there was a next stop in the original sequence
            if insertion_point_index < len(original_stops_sequence):
                next_original_stop_in_sequence = original_stops_sequence[insertion_point_index]
                print(f"[DEBUG insert_dynamic_locations] Subproblem should end at next original stop (Index {insertion_point_index} in sequence): {next_original_stop_in_sequence}")
                # Find the full data for this stop in the original path (which includes matrix_idx if available)
                target_lat = next_original_stop_in_sequence['lat']
                target_lon = next_original_stop_in_sequence['lon']
                # Search the original full path for this stop
                end_cp_data = next((p for p in original_route.get('path', []) if
                                    abs(p['lat'] - target_lat) < 1e-6 and
                                    abs(p['lon'] - target_lon) < 1e-6), None)

                if end_cp_data:
                    end_cp_data = end_cp_data.copy()
                    # Mark its type clearly for the subproblem context
                    end_cp_data['type'] = 'subproblem_end_checkpoint' if end_cp_data.get('type') == 'checkpoint' else 'subproblem_end_destination'
                else:
                    print(f"[WARN insert_dynamic_locations] Could not find full data for next stop {insertion_point_index}. Using warehouse as end.")
                    # Fallback to warehouse if the next stop couldn't be found in the path data
                    end_cp_data = {'lat': warehouse_coords['lat'], 'lon': warehouse_coords['lon'], 'type': 'warehouse', 'matrix_idx': 0} # Assuming warehouse is index 0
            else:
                # If the insertion point was after the last stop, the subproblem ends at the warehouse
                print("[DEBUG insert_dynamic_locations] Subproblem ends at warehouse (insertion after last stop).")
                end_cp_data = {'lat': warehouse_coords['lat'], 'lon': warehouse_coords['lon'], 'type': 'warehouse', 'matrix_idx': 0} # Assuming warehouse is index 0

            if end_cp_data is None or 'lat' not in end_cp_data or 'lon' not in end_cp_data:
                 print(f"[ERROR insert_dynamic_locations] Failed to determine valid end_cp_data. Value: {end_cp_data}")
                 raise ValueError("Could not determine valid end location for subproblem.")
            # --- End end_cp_data determination ---

            # --- Combine Locations for Sub-Problem Matrix ---
            # Order: Current Location (Start/Depot for subproblem), Remaining Originals, New Dynamics, End Location (end_cp_data)
            subproblem_locations = [current_location] + remaining_original_stops + new_dynamic_stops_for_subproblem + [end_cp_data]
            num_sub_locations = len(subproblem_locations)
            print(f"[DEBUG insert_dynamic_locations] Constructed subproblem_locations list with {num_sub_locations} items.")

            if not ors_client:
                raise ConnectionError("ORS client not available for subproblem distance calculation.")
            try:
                print(f"[DEBUG insert_dynamic_locations] Calling _calculate_ors_distance_matrix with list of length {len(subproblem_locations)}")
                subproblem_matrix = VRPTestScenarioService._calculate_ors_distance_matrix(subproblem_locations, ors_client)
                if subproblem_matrix is None:
                    raise ValueError("Failed to calculate ORS matrix for subproblem.")
                if not isinstance(subproblem_matrix, np.ndarray):
                     raise ValueError("Calculated subproblem matrix is not a numpy array.")
                expected_shape = (num_sub_locations, num_sub_locations)
                if subproblem_matrix.shape != expected_shape:
                     raise ValueError(f"Calculated subproblem matrix has incorrect shape. Expected {expected_shape}, got {subproblem_matrix.shape}.")
                print("[DEBUG insert_dynamic_locations] Subproblem ORS matrix calculated successfully and validated.")
            except Exception as e:
                raise ConnectionError(f"Failed to get ORS subproblem matrix: {e}") from e

            # --- Map Indices for Solver Constraints ---
            subproblem_start_node = 0
            subproblem_end_node = num_sub_locations - 1
            pickup_delivery_pairs_subproblem_indices = []
            dynamic_pickup_indices = {}
            dynamic_dropoff_indices = {}
            for idx, loc in enumerate(subproblem_locations):
                 loc_id = loc.get('id')
                 if loc.get('is_dynamic'):
                     if loc.get('type') == 'pickup': dynamic_pickup_indices[loc_id] = idx
                     elif loc.get('type') == 'dropoff': dynamic_dropoff_indices[loc_id] = idx
            for pair_idx, pair in enumerate(new_location_pairs):
                 pickup_id = f"DYN_P_{pair_idx}"
                 dropoff_id = f"DYN_D_{pair_idx}"
                 pickup_idx_sub = dynamic_pickup_indices.get(pickup_id)
                 dropoff_idx_sub = dynamic_dropoff_indices.get(dropoff_id)
                 if pickup_idx_sub is not None and dropoff_idx_sub is not None:
                     pickup_delivery_pairs_subproblem_indices.append((pickup_idx_sub, dropoff_idx_sub))
                 else:
                      print(f"[WARN insert_dynamic_locations] Could not find subproblem index for dynamic pair {pair_idx} (IDs: {pickup_id}, {dropoff_id})")

            # Prepare data for the subproblem solver
            subproblem_prepared_data = {
                'warehouse': current_location,
                'active_routing_checkpoints': subproblem_locations[1:-1],
                'checkpoint_distance_matrix': subproblem_matrix,
                'required_clusters': [],
                'checkpoint_to_clusters': {},
                'idx_to_cluster_set': {},
                'subproblem_locations': subproblem_locations
            }

            print("[DEBUG insert_dynamic_locations] Initializing EnhancedVRP for subproblem solve.")
            subproblem_solver = EnhancedVehicleRoutingProblem(
                warehouse=current_location, # Use start node as 'warehouse' for subproblem context
                destinations=[], # Not relevant for checkpoint subproblem
                num_vehicles=1
            )

            # --- Determine Subproblem Algorithm ---
            subproblem_algorithm = algorithm # Start with user's choice
            if new_location_pairs: # If there are dynamic pairs
                if algorithm != 'or_tools' and HAS_ORTOOLS:
                    print(f"[INFO insert_dynamic_locations] Dynamic pairs present. Forcing OR-Tools for subproblem solve to enforce constraints (User selected: {algorithm}).")
                    subproblem_algorithm = 'or_tools'
                elif not HAS_ORTOOLS:
                     # Error handled within EnhancedVRP.solve, but log here too
                     print("[WARN insert_dynamic_locations] Dynamic pairs present, but OR-Tools is unavailable. Heuristic/2-Opt cannot enforce P/D order.")
                     # Proceed with user's choice, EnhancedVRP will error if needed or warn critically

            print(f"[DEBUG insert_dynamic_locations] Calling subproblem solver. Algorithm: {subproblem_algorithm}")

            subproblem_options = {
                'is_subproblem': True,
                'start_node': subproblem_start_node, # Index within the subproblem matrix/list
                'end_node': subproblem_end_node, # Index within the subproblem matrix/list
                'pickup_delivery_pairs': pickup_delivery_pairs_subproblem_indices # Indices within the subproblem matrix/list
            }

            # Solve the subproblem
            subproblem_solution = subproblem_solver.solve(subproblem_prepared_data, algorithm=subproblem_algorithm, options=subproblem_options)

            # --- Process Sub-Problem Result ---
            solver_error_message = subproblem_solution.get('error')
            if solver_error_message is not None or not subproblem_solution.get('routes'):
                error_msg_to_report = solver_error_message if solver_error_message is not None else 'Solver failed to find a route for the subproblem.'
                print(f"[ERROR insert_dynamic_locations] Subproblem solver failed: {error_msg_to_report}")
                return {'status': 'error', 'message': str(error_msg_to_report)}

            print("[DEBUG insert_dynamic_locations] Subproblem solver succeeded.")
            subproblem_route = subproblem_solution['routes'][0]
            subproblem_path = subproblem_route.get('path', [])
            subproblem_stops = subproblem_route.get('stops', [])

            # --- Stitch Original and New Route Segments ---
            if not subproblem_path:
                 raise ValueError("Subproblem solver returned an empty path despite reporting success.")

            new_full_path = original_segment_completed_path + subproblem_path[1:]
            new_full_stops = original_stops_sequence[:insertion_point_index] + subproblem_stops if is_checkpoint_route else []

            # --- Recalculate Full Stitched Path Distance ---
            print(f"[DEBUG insert_dynamic_locations] Calculating distance for full stitched path (length {len(new_full_path)}).")
            new_total_distance_recalc = VRPTestScenarioService._calculate_path_distance(new_full_path, None, ors_client)
            print(f"[DEBUG insert_dynamic_locations] Full stitched path distance: {new_total_distance_recalc:.2f} km")

            # --- Update the Solution Object ---
            updated_solution = json.loads(json.dumps(current_solution))
            updated_solution['routes'][target_vehicle_index]['path'] = new_full_path
            updated_solution['routes'][target_vehicle_index]['stops'] = new_full_stops
            updated_solution['routes'][target_vehicle_index]['distance'] = new_total_distance_recalc
            updated_solution['total_distance'] = sum(r.get('distance', 0) for r in updated_solution['routes'])

            # --- Fetch Detailed Geometry for the Updated Route ---
            if api_key:
                print(f"[DEBUG insert_dynamic_locations] Fetching detailed geometry for updated route {target_vehicle_index}...")
                try:
                    # --- USE VRPService HELPER ---
                    updated_detailed_geometry = VRPService.get_detailed_route_geometry(new_full_path, api_key)
                    # ---

                    if updated_detailed_geometry:
                        print(f"[DEBUG insert_dynamic_locations]   Updated route {target_vehicle_index} final detailed geometry points: {len(updated_detailed_geometry)}")
                        updated_solution['routes'][target_vehicle_index]['detailed_path_geometry'] = updated_detailed_geometry
                    else:
                        print(f"[WARN insert_dynamic_locations]   Failed to generate detailed geometry for updated route {target_vehicle_index}.")
                        updated_solution['routes'][target_vehicle_index]['detailed_path_geometry'] = None

                except Exception as detail_err:
                     print(f"[ERROR insert_dynamic_locations] Error fetching detailed geometry for updated route: {detail_err}")
                     updated_solution['routes'][target_vehicle_index]['detailed_path_geometry'] = None
            else:
                 print("[WARN insert_dynamic_locations] No API key, skipping detailed geometry fetch for updated route.")
                 updated_solution['routes'][target_vehicle_index]['detailed_path_geometry'] = None
            # --- End Detailed Geometry Fetch ---

            # Add metadata
            computation_time = time.time() - start_time
            updated_solution['execution_time_ms'] = int(computation_time * 1000) # Overall time for insertion
            updated_solution['is_dynamic_update'] = True
            updated_solution['dynamic_pairs_count'] = len(new_location_pairs)
            if 'test_info' not in updated_solution: updated_solution['test_info'] = {}
            updated_solution['test_info']['timestamp'] = datetime.now().isoformat()
            updated_solution['status'] = 'success' # Ensure status is success

            print(f"[DEBUG insert_dynamic_locations] Route stitching complete. New total distance: {updated_solution['total_distance']:.2f} km")
            return updated_solution

        except (ValueError, ConnectionError, RuntimeError, sqlite3.Error) as e:
            print(f"[ERROR insert_dynamic_locations] Handled error during subproblem solve/stitch: {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': f"Error during dynamic insertion: {str(e)}"}
        except Exception as e:
            print(f"[ERROR insert_dynamic_locations] Unexpected error: {e}")
            traceback.print_exc()
            return {'status': 'error', 'message': f"Unexpected error during dynamic insertion: {str(e)}"}
        finally:
            if conn:
                conn.close()

    @staticmethod
    def _calculate_path_distance(path, matrix=None, ors_client=None):
        """
        Calculates the distance of a path (list of location dicts) using ORS directions or Haversine fallback.
        """
        if not path or len(path) < 2:
            return 0.0

        total_distance = 0.0

        if ors_client:
            print(f"[DEBUG _calculate_path_distance] Calculating distance for {len(path)} points using ORS directions API.")
            try:
                # Iterate through segments of the path
                for i in range(len(path) - 1):
                    p1 = path[i]
                    p2 = path[i+1]

                    # Basic validation of points
                    if not (p1 and p2 and 'lat' in p1 and 'lon' in p1 and 'lat' in p2 and 'lon' in p2):
                        print(f"[WARN _calculate_path_distance] Invalid or incomplete coordinates in path segment {i}: {p1}, {p2}. Skipping segment.")
                        continue # Skip this segment

                    # Ensure coordinates are floats
                    try:
                        coords = [
                            [float(p1['lon']), float(p1['lat'])],
                            [float(p2['lon']), float(p2['lat'])]
                        ]
                    except (ValueError, TypeError) as coord_err:
                         print(f"[WARN _calculate_path_distance] Coordinate conversion error in segment {i}: {coord_err}. Skipping segment.")
                         continue # Skip this segment

                    # Call ORS Directions API for the segment
                    try:
                        # Request only distance, no geometry or instructions for efficiency
                        route_info = ors_client.directions(
                            coordinates=coords,
                            profile='driving-car',
                            format='json',
                            instructions='false',
                            geometry='false'
                        )
                        # --- CORRECT RESPONSE PARSING ---
                        if (route_info and 'routes' in route_info and
                                len(route_info['routes']) > 0 and
                                'summary' in route_info['routes'][0] and
                                'distance' in route_info['routes'][0]['summary']):

                            segment_distance = route_info['routes'][0]['summary']['distance'] / 1000.0 # Convert meters to km
                            total_distance += segment_distance
                            # print(f"[DEBUG _calculate_path_distance] Segment {i} distance: {segment_distance:.3f} km") # Optional detailed log
                        else:
                            # Log unexpected response and fallback for this segment
                            print(f"[WARN _calculate_path_distance] Unexpected ORS directions response structure for segment {i}. Response: {route_info}. Falling back to Haversine for segment.")
                            total_distance += VRPTestScenarioService._haversine_distance(p1['lat'], p1['lon'], p2['lat'], p2['lon'])
                        # --- END CORRECT RESPONSE PARSING ---

                    except Exception as ors_api_err:
                         print(f"[WARN _calculate_path_distance] ORS directions API error for segment {i}: {ors_api_err}. Falling back to Haversine for segment.")
                         total_distance += VRPTestScenarioService._haversine_distance(p1['lat'], p1['lon'], p2['lat'], p2['lon'])

                print(f"[DEBUG _calculate_path_distance] Total ORS calculated distance: {total_distance:.3f} km")
                return total_distance

            except Exception as e:
                # Catch-all for unexpected errors during ORS calculation loop
                print(f"[ERROR _calculate_path_distance] Unexpected error during ORS distance calculation loop: {e}. Falling back to Haversine for entire path.")
                # Fallback to calculating Haversine for the whole path if ORS fails catastrophically

        # --- Fallback to Haversine if ORS client not provided or failed ---
        print("[DEBUG _calculate_path_distance] Using Haversine distance calculation (fallback).")
        total_distance = 0.0 # Recalculate from scratch
        for i in range(len(path) - 1):
            p1 = path[i]
            p2 = path[i+1]
            if p1 and p2 and 'lat' in p1 and 'lon' in p1 and 'lat' in p2 and 'lon' in p2:
                try:
                    total_distance += VRPTestScenarioService._haversine_distance(
                        float(p1['lat']), float(p1['lon']),
                        float(p2['lat']), float(p2['lon'])
                    )
                except (ValueError, TypeError):
                     print(f"[WARN _calculate_path_distance] Haversine fallback: Coordinate conversion error in segment {i}. Skipping.")
                     continue
            else:
                 print(f"[WARN _calculate_path_distance] Haversine fallback: Invalid coordinates in segment {i}. Skipping.")

        print(f"[DEBUG _calculate_path_distance] Total Haversine calculated distance: {total_distance:.3f} km")
        return total_distance

    @staticmethod
    def _ensure_location_in_snapshot(conn, lat, lon, address, cluster_id):
        """
        Ensure a location exists in the snapshot database and is properly clustered.
        Returns the location ID.
        """
        cursor = conn.cursor()
        address = address or {} # Ensure address is a dict

        # Check if location already exists
        cursor.execute(
            "SELECT id FROM locations WHERE lat = ? AND lon = ?",
            (lat, lon)
        )
        existing = cursor.fetchone()

        if existing:
            location_id = existing['id']
        else:
            # Insert the location
            cursor.execute(
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
            location_id = cursor.lastrowid

        # Ensure cluster assignment
        if cluster_id:
            cursor.execute(
                "SELECT location_id FROM location_clusters WHERE location_id = ?",
                (location_id,)
            )
            existing_cluster = cursor.fetchone()

            if not existing_cluster:
                cursor.execute(
                    "INSERT OR REPLACE INTO location_clusters (location_id, cluster_id) VALUES (?, ?)",
                    (location_id, cluster_id)
                )

        conn.commit()
        return location_id

    @staticmethod
    def _haversine_distance(lat1, lon1, lat2, lon2):
        """Calculate the great-circle distance between two points on the Earth."""
        # Ensure inputs are floats
        try:
            lat1, lon1, lat2, lon2 = map(float, [lat1, lon1, lat2, lon2])
        except (ValueError, TypeError):
            print(f"[WARN _haversine_distance] Invalid input types for Haversine: {(lat1, lon1, lat2, lon2)}")
            return 0.0 # Return 0 if coordinates are invalid

        R = 6371  # Earth radius in kilometers
        dLat = math.radians(lat2 - lat1)
        dLon = math.radians(lon2 - lon1)
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        a = (math.sin(dLat / 2) * math.sin(dLat / 2) +
             math.sin(dLon / 2) * math.sin(dLon / 2) * math.cos(lat1_rad) * math.cos(lat2_rad))
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distance = R * c
        return distance