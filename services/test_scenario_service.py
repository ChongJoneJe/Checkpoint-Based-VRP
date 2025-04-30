from flask import current_app
import os
import sqlite3
import json
import time
import traceback
import numpy as np
import math
import re
from services.vrp_service import VRPService
from services.vrp_testing_service import VRPTestingService
from algorithms.enhanced_vrp import EnhancedVehicleRoutingProblem, HAS_ORTOOLS
from services.cache_service import CacheService
from utils.json_helpers import NumpyEncoder
import random
from math import radians, sin, cos, sqrt, atan2
import openrouteservice
from datetime import datetime

class VRPTestScenarioService:

    @staticmethod
    def prepare_test_data(snapshot_id, preset_id, api_key=None):
        """Prepares data for checkpoint-based VRP, including distance matrix."""
        # Use snapshot_id (without extension) and preset_id for cache key
        cache_key = f"checkpoint_matrix_{snapshot_id}_{preset_id}"
        cached_data = CacheService().get(cache_key) # Correct: Get instance first
        if cached_data:
            print(f"[DEBUG prepare_test_data] Using cached data for key: {cache_key}")
            # --- ENSURE API KEY IS PRESENT IN CACHED DATA ---
            if 'api_key' not in cached_data or cached_data['api_key'] is None:
                 cached_data['api_key'] = api_key # Add/update the key from the current call
                 print("[DEBUG prepare_test_data] Added/Updated api_key in cached data.")
            # --- END ENSURE API KEY ---
            # Ensure snapshot_id and preset_id are present in cached data
            if 'snapshot_id' not in cached_data:
                 cached_data['snapshot_id'] = snapshot_id
            if 'preset_id' not in cached_data:
                 cached_data['preset_id'] = preset_id
            return cached_data

        print(f"[DEBUG prepare_test_data] Cache miss for key: {cache_key}. Preparing fresh data.")

        try:
            # Construct DB path using snapshot_id
            if snapshot_id.endswith('.sqlite'):
                 db_snapshot_filename = snapshot_id # Already has extension
            else:
                 db_snapshot_filename = f"{snapshot_id}.sqlite" # Add extension

            # Use a robust way to get the base path
            try:
                from flask import current_app
                base_path = os.path.join(current_app.root_path, "vrp_test_data")
            except ImportError:
                base_path = os.path.join(os.path.dirname(__file__), '..', 'vrp_test_data')
                print(f"[WARN prepare_test_data] Not in Flask context, using relative path: {base_path}")

            db_path = os.path.join(base_path, db_snapshot_filename)
            print(f"[DEBUG prepare_test_data] Constructed DB path: {db_path}")

            if not os.path.exists(db_path):
                print(f"[ERROR prepare_test_data] Snapshot ID received: {snapshot_id}")
                return {'status': 'error', 'message': f'Snapshot database not found: {db_path}'}

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # --- CORRECTED: Fetch warehouse and destinations using schema ---
            warehouse = None
            destinations = []

            # Query for Warehouse (is_warehouse = 1)
            cursor.execute("""
                SELECT l.id, l.lat, l.lon, l.street, l.city, l.postcode
                FROM locations l
                JOIN preset_locations pl ON l.id = pl.location_id
                WHERE pl.preset_id = ? AND pl.is_warehouse = 1
                LIMIT 1
            """, (preset_id,))
            warehouse_row = cursor.fetchone()

            if warehouse_row:
                warehouse = {
                    'id': warehouse_row['id'],
                    'lat': warehouse_row['lat'],
                    'lon': warehouse_row['lon'],
                    'address': f"{warehouse_row['street'] or ''}, {warehouse_row['postcode'] or ''} {warehouse_row['city'] or ''}".strip(', '),
                    'type': 'warehouse' # Add type for consistency
                }
                print(f"[DEBUG prepare_test_data] Found warehouse: {warehouse}")
            else:
                conn.close()
                return {'status': 'error', 'message': f'Warehouse not found for Preset ID {preset_id} in snapshot {snapshot_id}'}

            # Query for Destinations (is_warehouse = 0 or NULL)
            cursor.execute("""
                SELECT l.id, l.lat, l.lon, l.street, l.city, l.postcode
                FROM locations l
                JOIN preset_locations pl ON l.id = pl.location_id
                WHERE pl.preset_id = ? AND (pl.is_warehouse = 0 OR pl.is_warehouse IS NULL)
            """, (preset_id,))
            destination_rows = cursor.fetchall()

            for row in destination_rows:
                destinations.append({
                    'id': row['id'],
                    'lat': row['lat'],
                    'lon': row['lon'],
                    'address': f"{row['street'] or ''}, {row['postcode'] or ''} {row['city'] or ''}".strip(', '),
                    'type': 'destination' # Add type for consistency
                })
            print(f"[DEBUG prepare_test_data] Found {len(destinations)} destinations.")
            # --- END CORRECTION ---

            # Determine required clusters from destination locations
            required_clusters = set()
            destination_coords = [(float(d['lat']), float(d['lon'])) for d in destinations if 'lat' in d and 'lon' in d]

            if not destination_coords:
                 print("[WARN prepare_test_data] No valid destination coordinates found in preset.")
            else:
                # Find clusters for destinations more efficiently
                # Get location IDs directly from the destinations list we just built
                dest_loc_ids = [d['id'] for d in destinations]

                if dest_loc_ids:
                    placeholders = ','.join('?' * len(dest_loc_ids))
                    cluster_query = f"SELECT DISTINCT cluster_id FROM location_clusters WHERE location_id IN ({placeholders})"
                    try:
                        cursor.execute(cluster_query, dest_loc_ids)
                        required_clusters = {row['cluster_id'] for row in cursor.fetchall() if row['cluster_id'] is not None}
                        print(f"[DEBUG prepare_test_data] Required clusters from destinations: {required_clusters}")
                    except sqlite3.OperationalError as op_err:
                         print(f"[ERROR prepare_test_data] SQLite error finding destination clusters: {op_err}. Might be too many coordinates for IN clause.")
                         conn.close()
                         return {'status': 'error', 'message': f'Database error finding destination clusters: {op_err}'}
                else:
                    print("[WARN prepare_test_data] Could not find location IDs for destination coordinates.")


            if not required_clusters:
                 print("[WARN prepare_test_data] No clusters identified for the given destinations.")


            # Fetch active routing checkpoints covering these clusters
            active_routing_checkpoints = []
            checkpoint_to_clusters = {} # Map "lat,lon" -> [cluster_ids]
            if required_clusters:
                placeholders_clusters = ','.join('?' * len(required_clusters))
                print(f"[DEBUG prepare_test_data] Executing checkpoints query for clusters: {list(required_clusters)}")
                # Use the correct table name 'security_checkpoints'
                cursor.execute(
                    f"SELECT id, lat, lon, cluster_id FROM security_checkpoints WHERE cluster_id IN ({placeholders_clusters})",
                    list(required_clusters)
                )
                unique_cps = {}
                for row in cursor.fetchall():
                    cp_key = f"{row['lat']:.6f},{row['lon']:.6f}"
                    if cp_key not in unique_cps:
                        unique_cps[cp_key] = {
                            'id': row['id'], 'lat': row['lat'], 'lon': row['lon'],
                            'type': 'checkpoint', 'clusters_served': set()
                        }
                    unique_cps[cp_key]['clusters_served'].add(row['cluster_id'])
                    if cp_key not in checkpoint_to_clusters:
                        checkpoint_to_clusters[cp_key] = []
                    if row['cluster_id'] not in checkpoint_to_clusters[cp_key]:
                         checkpoint_to_clusters[cp_key].append(row['cluster_id'])

                active_routing_checkpoints = list(unique_cps.values())
                for cp in active_routing_checkpoints:
                    cp['clusters_served'] = list(cp['clusters_served'])
                print(f"[DEBUG prepare_test_data] Found {len(active_routing_checkpoints)} raw checkpoints from DB.")

            conn.close() # Close DB connection after fetching data

            if not active_routing_checkpoints and required_clusters:
                 print(f"[WARN prepare_test_data] No security checkpoints found for required clusters: {required_clusters}")


            # Prepare locations for distance matrix calculation
            all_locations_for_matrix = [warehouse] + active_routing_checkpoints
            num_locations = len(all_locations_for_matrix)

            # Calculate distance matrix (using ORS or Haversine)
            ors_client = None
            distance_type = 'haversine' # Default
            checkpoint_distance_matrix = None

            if api_key:
                try:
                    ors_client = VRPService._get_ors_client(api_key)
                    if ors_client:
                        print("[DEBUG prepare_test_data] Using OpenRouteService for checkpoint distance matrix.")
                        distance_type = 'ors'
                        print(f"[DEBUG prepare_test_data] Calculating matrix for {num_locations} total locations (warehouse + checkpoints).")
                        checkpoint_distance_matrix = VRPTestScenarioService._calculate_ors_distance_matrix(
                            all_locations_for_matrix, ors_client
                        )
                        if checkpoint_distance_matrix is None:
                             print("[WARN prepare_test_data] ORS matrix calculation failed, falling back to Haversine.")
                             distance_type = 'haversine' # Fallback
                        else:
                             print("[DEBUG prepare_test_data] Successfully calculated ORS distance matrix.")
                    else:
                         print("[WARN prepare_test_data] Failed to initialize ORS client, using Haversine.")
                except Exception as ors_err:
                    print(f"[WARN prepare_test_data] Error initializing or using ORS client: {ors_err}. Using Haversine.")
                    ors_client = None # Ensure client is None if error occurred

            if checkpoint_distance_matrix is None:
                distance_type = 'haversine'
                print("[DEBUG prepare_test_data] Using Haversine for checkpoint distance matrix.")
                checkpoint_distance_matrix = np.zeros((num_locations, num_locations))
                for i in range(num_locations):
                    for j in range(i, num_locations):
                        loc1 = all_locations_for_matrix[i]
                        loc2 = all_locations_for_matrix[j]
                        dist = VRPTestScenarioService._haversine_distance(loc1['lat'], loc1['lon'], loc2['lat'], loc2['lon'])
                        checkpoint_distance_matrix[i, j] = dist
                        checkpoint_distance_matrix[j, i] = dist

             # --- Create node_indices_map (index -> location_data) ---
            node_indices_map = {}
            for idx, loc_data in enumerate(all_locations_for_matrix):
                 loc_data_copy = loc_data.copy()
                 loc_data_copy['matrix_idx'] = idx
                 node_indices_map[idx] = loc_data_copy
            # --- End node_indices_map creation ---

            # --- Prepare idx_to_cluster_set mapping ---
            idx_to_cluster_set = {}
            idx_to_cluster_set[0] = set() # Warehouse is index 0
            cp_coord_to_idx = { f"{cp['lat']:.6f},{cp['lon']:.6f}": idx for idx, cp in enumerate(all_locations_for_matrix[1:], 1)}
            for cp_data in active_routing_checkpoints:
                 cp_key = f"{cp_data['lat']:.6f},{cp_data['lon']:.6f}"
                 matrix_idx = cp_coord_to_idx.get(cp_key)
                 if matrix_idx is not None:
                      idx_to_cluster_set[matrix_idx] = set(cp_data.get('clusters_served', []))
                 else:
                      print(f"[WARN prepare_test_data] Checkpoint {cp_key} not found in matrix mapping.")
            # --- End idx_to_cluster_set mapping ---


            prepared_dataset = {
                'warehouse': warehouse,
                'destinations': destinations,
                'required_clusters': list(required_clusters),
                'active_routing_checkpoints': active_routing_checkpoints,
                'node_indices_map': node_indices_map,
                'checkpoint_to_clusters': checkpoint_to_clusters,
                'idx_to_cluster_set': idx_to_cluster_set,
                'checkpoint_distance_matrix': checkpoint_distance_matrix,
                'has_clusters': bool(required_clusters),
                'distance_type': distance_type,
                'ors_client': ors_client,
                'snapshot_id': snapshot_id, # ID without extension
                'preset_id': preset_id,
                'api_key': api_key
            }

            # Cache the prepared data (excluding non-serializable ORS client)
            cacheable_data = prepared_dataset.copy()
            if 'ors_client' in cacheable_data:
                del cacheable_data['ors_client'] # Don't cache the client object
            CacheService().set(cache_key, cacheable_data)

            return prepared_dataset

        except Exception as e:
            print(f"[ERROR prepare_test_data] Unexpected error preparing data: {e}")
            traceback.print_exc()
            if 'conn' in locals() and conn:
                try: conn.close()
                except: pass
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
            api_key = prepared_data.get('api_key') # Retrieve the key (should be present now)
            if api_key and solution.get('routes'):
                print("[DEBUG run_checkpoint_vrp_scenario] Fetching detailed route geometry...")
                for i, route in enumerate(solution['routes']):
                    path_sequence = route.get('path') # Get the sequence of stops including warehouse
                    if path_sequence and len(path_sequence) >= 2:
                        print(f"[DEBUG run_checkpoint_vrp_scenario] Processing route {i+1} (length {len(path_sequence)}) for detailed path.")
                        try:
                            # --- USE VRPService HELPER ---
                            route_detailed_geometry = VRPService.get_detailed_route_geometry(path_sequence, api_key=api_key)
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
                 print("[WARN run_checkpoint_vrp_scenario] No API key found in prepared_data, skipping detailed geometry fetch.")
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
        Compares two strategies for inserting dynamic P/D pairs and chooses the shorter one:
        A) Constrained Insertion (Requires OR-Tools): Inserts P/D respecting order, visiting ALL original remaining stops, and covering any new clusters.
        B) Append P/D: Finishes original segment, then visits P, then D, then Warehouse.
        """
        print(f"[INFO insert_dynamic_locations] Comparing Insertion vs. Append strategies. Target Vehicle: {target_vehicle_index}, At Stop Index: {insertion_point_index}")
        start_time_comparison = time.time()

        # --- Basic Setup & Validation ---
        if not new_location_pairs:
            return {'status': 'error', 'message': 'No dynamic location pairs provided for insertion.'}
        if not current_solution or 'routes' not in current_solution or target_vehicle_index >= len(current_solution['routes']):
            return {'status': 'error', 'message': 'Invalid current solution or target vehicle index.'}
        if not prepared_data or 'snapshot_id' not in prepared_data:
             return {'status': 'error', 'message': 'Prepared data or snapshot ID missing.'}

        # --- Ensure OR-Tools is available for Strategy A ---
        if not HAS_ORTOOLS:
            print("[ERROR insert_dynamic_locations] Comparison requires OR-Tools for Strategy A (Constrained Insertion), but OR-Tools is not available.")
            return {
                'status': 'error',
                'message': 'Cannot compare insertion strategies: OR-Tools is required but not available.',
                'recalculation_skipped': True
            }

        conn = None
        try:
            # --- Database Connection & Data Extraction ---
            snapshot_db_path = VRPTestScenarioService._get_snapshot_db_path(prepared_data['snapshot_id'])
            conn = sqlite3.connect(snapshot_db_path)
            conn.row_factory = sqlite3.Row

            original_route = current_solution['routes'][target_vehicle_index]
            original_stops_sequence = original_route.get('stops', []) # List of stop dicts
            original_warehouse = current_solution.get('warehouse')
            if not original_warehouse: raise ValueError("Warehouse data missing from current_solution")

            # --- Determine Start Location for Subproblems ---
            if insertion_point_index == 0:
                current_location = original_warehouse.copy()
                current_location['type'] = 'warehouse'
                original_segment_completed_path_nodes = [current_location] # Nodes visited before insertion point
            else:
                current_stop_index_in_list = insertion_point_index - 1
                if current_stop_index_in_list >= len(original_stops_sequence):
                    return {'status': 'error', 'message': f'Insertion point index {insertion_point_index} is out of bounds.'}
                # Make a copy to avoid modifying the original solution data
                current_location = original_stops_sequence[current_stop_index_in_list].copy()
                # Get the full path nodes up to and including the current location
                # The 'path' includes warehouse at start/end, 'stops' usually doesn't
                original_segment_completed_path_nodes = original_route.get('path', [])[:insertion_point_index + 1]
                if not original_segment_completed_path_nodes:
                     # Fallback if path is missing - reconstruct from stops + warehouse
                     original_segment_completed_path_nodes = [original_warehouse] + original_stops_sequence[:insertion_point_index]


            # --- Identify Remaining Original Stops/Clusters ---
            remaining_original_stops_data = original_stops_sequence[insertion_point_index:] # List of stop dicts
            remaining_original_clusters = set()
            for stop in remaining_original_stops_data:
                # Use helper to query DB based on stop coordinates
                cluster_id = VRPTestScenarioService._get_cluster_for_location(conn, stop['lat'], stop['lon'])
                if cluster_id is not None:
                    remaining_original_clusters.add(cluster_id)
            print(f"[DEBUG insert_dynamic_locations] Remaining original stops: {len(remaining_original_stops_data)}, Clusters: {remaining_original_clusters}")


            # --- Get New P/D Clusters and Checkpoint Info ---
            new_dynamic_clusters = set()
            pickup_checkpoint_indices = [] # Indices in the *full* matrix
            dropoff_checkpoint_indices = [] # Indices in the *full* matrix
            full_distance_matrix = prepared_data.get('checkpoint_distance_matrix')
            full_node_indices_map = prepared_data.get('node_indices_map') # Map index -> location data
            full_loc_to_idx_map = {f"{loc['lat']:.6f},{loc['lon']:.6f}": idx for idx, loc in full_node_indices_map.items()} if full_node_indices_map else {}

            if full_distance_matrix is None or not full_loc_to_idx_map:
                 matrix_status = "missing" if full_distance_matrix is None else "present"
                 map_status = "missing" if not full_loc_to_idx_map else "present"
                 error_msg = f"Full distance matrix ({matrix_status}) or node mapping ({map_status}) missing from prepared_data."
                 print(f"[ERROR insert_dynamic_locations] {error_msg}")
                 raise ValueError(error_msg)

            # Process each new pair to get cluster IDs and selected checkpoint indices
            for pair_idx, pair in enumerate(new_location_pairs):
                p_cluster = pair['pickup'].get('cluster_id')
                d_cluster = pair['dropoff'].get('cluster_id')
                if p_cluster is not None: new_dynamic_clusters.add(p_cluster)
                if d_cluster is not None: new_dynamic_clusters.add(d_cluster)

                p_cp_data = pair['pickup'].get('selected_checkpoint')
                d_cp_data = pair['dropoff'].get('selected_checkpoint')

                # --- ADD VALIDATION ---
                if not p_cp_data or 'lat' not in p_cp_data or 'lon' not in p_cp_data:
                    raise ValueError(f"Missing or invalid 'selected_checkpoint' data for pickup in pair {pair_idx}.")
                if not d_cp_data or 'lat' not in d_cp_data or 'lon' not in d_cp_data:
                    raise ValueError(f"Missing or invalid 'selected_checkpoint' data for dropoff in pair {pair_idx}.")
                # --- END VALIDATION ---

                p_cp_key = f"{p_cp_data['lat']:.6f},{p_cp_data['lon']:.6f}"
                d_cp_key = f"{d_cp_data['lat']:.6f},{d_cp_data['lon']:.6f}"
                print(f"[DEBUG insert_dynamic_locations] Processing Pair {pair_idx}: PKey={p_cp_key}, DKey={d_cp_key}")

                p_idx = full_loc_to_idx_map.get(p_cp_key)
                d_idx = full_loc_to_idx_map.get(d_cp_key)

                if p_idx is None or d_idx is None:
                    print(f"[ERROR insert_dynamic_locations] Lookup failed. PKey='{p_cp_key}', DKey='{d_cp_key}'. Found P Index: {p_idx}, Found D Index: {d_idx}")
                    map_keys_sample = list(full_loc_to_idx_map.keys())[:5]
                    print(f"  Sample keys in full_loc_to_idx_map: {map_keys_sample} ... (Total: {len(full_loc_to_idx_map)})")
                    raise ValueError(f"Could not find matrix index for P/D checkpoints: PKey={p_cp_key}, DKey={d_cp_key}")

                pickup_checkpoint_indices.append(p_idx)
                dropoff_checkpoint_indices.append(d_idx)
                print(f"  Found Indices -> P: {p_idx}, D: {d_idx}")

            # --- STRATEGY A: Constrained Insertion (using OR-Tools) ---
            print("[DEBUG insert_dynamic_locations] Calculating Strategy A (Constrained Insertion)...")
            distance_A = float('inf')
            solution_A = None
            intermediate_stops_A = [] # Store the sequence of stops between start and end
            try:
                # 1. Determine relevant locations for the subproblem
                #    Includes: current_location (start), warehouse (end),
                #    ALL checkpoints from remaining_original_stops_data,
                #    Selected P/D checkpoints (pickup_checkpoint_indices, dropoff_checkpoint_indices)

                # --- Build subproblem_A_locations list ---
                subproblem_A_locations = []
                subproblem_loc_keys = set() # To track unique locations by key

                # Add start node (current location)
                start_loc_copy = current_location.copy()
                start_loc_key = f"{start_loc_copy['lat']:.6f},{start_loc_copy['lon']:.6f}"
                start_loc_original_idx = full_loc_to_idx_map.get(start_loc_key)
                if start_loc_original_idx is not None:
                    start_loc_copy['original_matrix_idx'] = start_loc_original_idx
                elif start_loc_copy.get('type') == 'warehouse':
                     start_loc_copy['original_matrix_idx'] = 0 # Assume warehouse is always 0
                else:
                     raise ValueError(f"Cannot determine original matrix index for start location: {start_loc_key}")
                subproblem_A_locations.append(start_loc_copy)
                subproblem_loc_keys.add(start_loc_key)

                # Add original remaining checkpoints (ensure they exist in the full map)
                original_remaining_cp_matrix_indices = set()
                for stop_data in remaining_original_stops_data:
                    stop_key = f"{stop_data['lat']:.6f},{stop_data['lon']:.6f}"
                    matrix_idx = full_loc_to_idx_map.get(stop_key)
                    if matrix_idx is not None:
                        if stop_key not in subproblem_loc_keys:
                            loc_data = full_node_indices_map.get(matrix_idx)
                            if loc_data:
                                loc_copy = loc_data.copy()
                                loc_copy['original_matrix_idx'] = matrix_idx # Ensure it's set
                                subproblem_A_locations.append(loc_copy)
                                subproblem_loc_keys.add(stop_key)
                                original_remaining_cp_matrix_indices.add(matrix_idx)
                            else:
                                print(f"[WARN Strategy A Setup] Could not find location data for original stop index {matrix_idx}")
                        else:
                             # If already added (e.g., start node was the last original stop), still track its index
                             original_remaining_cp_matrix_indices.add(matrix_idx)
                    else:
                        print(f"[WARN Strategy A Setup] Could not find matrix index for original remaining stop: {stop_key}")

                # Add selected P/D checkpoints (ensure they exist in the full map)
                pd_matrix_indices = set(pickup_checkpoint_indices + dropoff_checkpoint_indices)
                for matrix_idx in pd_matrix_indices:
                    loc_data = full_node_indices_map.get(matrix_idx)
                    if loc_data:
                        loc_key = f"{loc_data['lat']:.6f},{loc_data['lon']:.6f}"
                        if loc_key not in subproblem_loc_keys:
                            loc_copy = loc_data.copy()
                            loc_copy['original_matrix_idx'] = matrix_idx # Ensure it's set
                            loc_copy['is_dynamic'] = True # Mark as part of the dynamic insertion
                            subproblem_A_locations.append(loc_copy)
                            subproblem_loc_keys.add(loc_key)
                    else:
                        print(f"[WARN Strategy A Setup] Could not find location data for P/D index {matrix_idx}")

                # Add end node (warehouse)
                end_loc_copy = original_warehouse.copy()
                end_loc_copy['original_matrix_idx'] = 0 # Assume warehouse is always index 0
                end_loc_key = f"{end_loc_copy['lat']:.6f},{end_loc_copy['lon']:.6f}"
                if end_loc_key not in subproblem_loc_keys:
                    subproblem_A_locations.append(end_loc_copy)
                    subproblem_loc_keys.add(end_loc_key)

                print(f"[DEBUG Strategy A Setup] Built subproblem_A_locations list with {len(subproblem_A_locations)} unique locations.")

                # --- Verification for original_matrix_idx ---
                missing_indices = False
                for idx, loc_data in enumerate(subproblem_A_locations):
                     if 'original_matrix_idx' not in loc_data:
                          key = f"{loc_data.get('lat', 0.0):.6f},{loc_data.get('lon', 0.0):.6f}"
                          print(f"[ERROR Strategy A Setup] Critical: Missing original_matrix_idx for subproblem loc {idx} ({loc_data.get('type')}) with key {key} AFTER construction.")
                          missing_indices = True
                if missing_indices:
                     raise ValueError("Failed to assign original_matrix_idx to all subproblem locations.")

                # 2. Create Subproblem Matrix and Mappings
                num_sub_A_locations = len(subproblem_A_locations)
                subproblem_A_matrix = np.zeros((num_sub_A_locations, num_sub_A_locations))
                subproblem_idx_map = {} # Maps subproblem index -> location data
                original_matrix_idx_to_subproblem_idx = {} # Maps original matrix index -> subproblem index

                for sub_idx, loc_data in enumerate(subproblem_A_locations):
                    subproblem_idx_map[sub_idx] = loc_data
                    original_idx = loc_data.get('original_matrix_idx')
                    if original_idx is not None:
                        original_matrix_idx_to_subproblem_idx[original_idx] = sub_idx
                        for sub_jdx, loc_data_j in enumerate(subproblem_A_locations):
                            original_jdx = loc_data_j.get('original_matrix_idx')
                            if original_jdx is not None:
                                # Use distances from the full matrix
                                subproblem_A_matrix[sub_idx, sub_jdx] = full_distance_matrix[original_idx, original_jdx]
                            else:
                                # Should not happen due to verification, but handle defensively
                                print(f"[ERROR Strategy A Setup] Missing original index for subproblem location {sub_jdx} during matrix creation.")
                                subproblem_A_matrix[sub_idx, sub_jdx] = float('inf')
                    else:
                         # Should not happen due to verification
                         print(f"[ERROR Strategy A Setup] Missing original index for subproblem location {sub_idx} during matrix creation.")

                # 3. Determine start/end nodes and constraints in the subproblem context
                subproblem_start_node_idx = 0 # By construction, start is always index 0
                subproblem_end_node_idx = num_sub_A_locations - 1 # By construction, end is always last index

                # Map P/D indices to subproblem indices
                subproblem_pd_pairs = []
                for i in range(len(pickup_checkpoint_indices)):
                    p_orig_idx = pickup_checkpoint_indices[i]
                    d_orig_idx = dropoff_checkpoint_indices[i]
                    sub_p_idx = original_matrix_idx_to_subproblem_idx.get(p_orig_idx)
                    sub_d_idx = original_matrix_idx_to_subproblem_idx.get(d_orig_idx)
                    if sub_p_idx is not None and sub_d_idx is not None:
                        subproblem_pd_pairs.append((sub_p_idx, sub_d_idx))
                    else:
                        raise ValueError(f"Could not map P/D original indices ({p_orig_idx}, {d_orig_idx}) to subproblem indices.")

                # Map original remaining checkpoint indices to subproblem indices (for mandatory visits)
                mandatory_nodes_subproblem_indices = set()
                for orig_cp_idx in original_remaining_cp_matrix_indices:
                    sub_idx = original_matrix_idx_to_subproblem_idx.get(orig_cp_idx)
                    # Exclude start/end nodes if they happen to be original CPs
                    if sub_idx is not None and sub_idx != subproblem_start_node_idx and sub_idx != subproblem_end_node_idx:
                        mandatory_nodes_subproblem_indices.add(sub_idx)
                    elif sub_idx is None:
                         print(f"[WARN Strategy A Setup] Original remaining CP index {orig_cp_idx} not found in subproblem map.")

                print(f"[DEBUG Strategy A Setup] Subproblem Start: {subproblem_start_node_idx}, End: {subproblem_end_node_idx}")
                print(f"[DEBUG Strategy A Setup] Subproblem P/D Pairs: {subproblem_pd_pairs}")
                print(f"[DEBUG Strategy A Setup] Subproblem Mandatory Nodes (Original Remaining CPs): {list(mandatory_nodes_subproblem_indices)}")

                # 4. Prepare data and options for the solver
                subproblem_prepared_data = {
                    'warehouse': subproblem_idx_map[subproblem_start_node_idx], # Use start node as 'warehouse' context for solver
                    'destinations': list(subproblem_idx_map.values()), # All nodes for context
                    'active_routing_checkpoints': [loc for idx, loc in subproblem_idx_map.items() if idx != subproblem_start_node_idx and idx != subproblem_end_node_idx],
                    'checkpoint_distance_matrix': subproblem_A_matrix,
                    'node_indices_map': subproblem_idx_map, # Use the subproblem map
                    'idx_to_cluster_set': {}, # Not strictly needed for mandatory visits, but can be built if useful
                    'required_clusters': [], # Not using cluster coverage for original stops here
                    'has_clusters': True # Indicate checkpoint logic applies
                }
                solver_options = {
                    'is_subproblem': True,
                    'start_node': subproblem_start_node_idx,
                    'end_node': subproblem_end_node_idx,
                    'pickup_delivery_pairs': subproblem_pd_pairs,
                    'mandatory_nodes': list(mandatory_nodes_subproblem_indices) # Pass mandatory nodes
                }

                # 5. Initialize and run the solver
                # Use num_vehicles=1 for the subproblem
                subproblem_solver = EnhancedVehicleRoutingProblem(
                    warehouse=subproblem_prepared_data['warehouse'],
                    destinations=subproblem_prepared_data['destinations'],
                    num_vehicles=1
                )
                solution_A = subproblem_solver.solve(subproblem_prepared_data, algorithm='or_tools', options=solver_options)

                # 6. Process the result
                if solution_A and solution_A.get('status') != 'error' and solution_A.get('routes'):
                    distance_A = solution_A.get('total_distance', float('inf'))
                    # Extract the sequence of intermediate stops (dictionaries) from the solution's path
                    # The 'path' in the solution includes start and end, we want stops between them.
                    subproblem_path = solution_A['routes'][0].get('path', [])
                    if len(subproblem_path) > 2:
                         intermediate_stops_A = subproblem_path[1:-1] # Get stop dicts between start and end
                    else:
                         intermediate_stops_A = [] # Direct route from start to end
                    print(f"[DEBUG insert_dynamic_locations] Strategy A Solution Found. Distance: {distance_A:.2f} km, Stops: {len(intermediate_stops_A)}")
                else:
                    error_msg = solution_A.get('error', 'Strategy A solver failed') if solution_A else 'Strategy A solver failed'
                    print(f"[ERROR insert_dynamic_locations] Strategy A failed: {error_msg}")
                    distance_A = float('inf') # Ensure it doesn't win comparison

            except Exception as e_strat_A:
                print(f"[ERROR insert_dynamic_locations] Exception during Strategy A calculation: {e_strat_A}")
                traceback.print_exc()
                distance_A = float('inf') # Ensure it doesn't win comparison

            # --- STRATEGY B: Append P/D ---
            print("[DEBUG insert_dynamic_locations] Calculating Strategy B (Append P/D)...")
            distance_B = float('inf')
            intermediate_stops_B = []
            try:
                # Path: original completed segment + original remaining stops + P checkpoint + D checkpoint + warehouse
                path_B_nodes = []
                path_B_nodes.extend(original_segment_completed_path_nodes) # Nodes up to insertion point

                # Add original remaining stops
                path_B_nodes.extend(remaining_original_stops_data)

                # Add P checkpoint(s) - assuming one pair for simplicity here, adjust if multiple
                p_cp_node = full_node_indices_map.get(pickup_checkpoint_indices[0])
                if p_cp_node: path_B_nodes.append(p_cp_node)

                # Add D checkpoint(s)
                d_cp_node = full_node_indices_map.get(dropoff_checkpoint_indices[0])
                if d_cp_node: path_B_nodes.append(d_cp_node)

                # Add warehouse at the end
                path_B_nodes.append(original_warehouse)

                # Calculate distance using the full matrix
                distance_B = VRPTestScenarioService._calculate_path_distance(
                    path_B_nodes,
                    matrix=full_distance_matrix,
                    node_map=full_node_indices_map
                )
                # Extract intermediate stops for Strategy B (all stops between first and last warehouse visit)
                intermediate_stops_B = path_B_nodes[1:-1]
                print(f"[DEBUG insert_dynamic_locations] Strategy B Calculated Distance: {distance_B:.2f} km, Stops: {len(intermediate_stops_B)}")

            except Exception as e_strat_B:
                print(f"[ERROR insert_dynamic_locations] Exception during Strategy B calculation: {e_strat_B}")
                traceback.print_exc()
                distance_B = float('inf')

            # --- Comparison and Final Selection ---
            print(f"[INFO insert_dynamic_locations] Comparison: Strategy A Distance = {distance_A:.2f}, Strategy B Distance = {distance_B:.2f}")

            chosen_strategy = None
            final_intermediate_stops = []
            final_distance = float('inf')

            if distance_A <= distance_B:
                print("[INFO insert_dynamic_locations] Choosing Strategy A (Constrained Insertion).")
                chosen_strategy = 'A'
                final_intermediate_stops = intermediate_stops_A
                final_distance = distance_A # Use distance calculated by subproblem solver
            else:
                print("[INFO insert_dynamic_locations] Choosing Strategy B (Append P/D).")
                chosen_strategy = 'B'
                final_intermediate_stops = intermediate_stops_B
                final_distance = distance_B # Use distance calculated for the full B path

            # --- Construct Updated Solution ---
            updated_solution = json.loads(json.dumps(current_solution, cls=NumpyEncoder)) 
            new_full_stops = original_segment_completed_path_nodes[1:] + final_intermediate_stops # Combine history + chosen segment (exclude first warehouse)
            new_full_path = [original_warehouse] + new_full_stops + [original_warehouse] # Add warehouse at start/end

            # Recalculate final distance using the chosen full path for consistency
            final_recalculated_distance = VRPTestScenarioService._calculate_path_distance(
                 new_full_path,
                 matrix=full_distance_matrix,
                 node_map=full_node_indices_map,
                 api_key=prepared_data.get('api_key') # Pass API key for potential ORS fallback
            )
            print(f"[DEBUG insert_dynamic_locations] Final stitched path distance (Recalculated): {final_recalculated_distance:.2f} km")


            # Update the specific vehicle's route
            updated_solution['routes'][target_vehicle_index]['stops'] = new_full_stops
            updated_solution['routes'][target_vehicle_index]['path'] = new_full_path
            updated_solution['routes'][target_vehicle_index]['distance'] = final_recalculated_distance
            # Update total distance if only one vehicle, otherwise recalculate sum
            if len(updated_solution['routes']) == 1:
                 updated_solution['total_distance'] = final_recalculated_distance
            else:
                 updated_solution['total_distance'] = sum(r.get('distance', 0) for r in updated_solution['routes'])


            # Fetch Detailed Geometry for the final chosen path
            api_key_geom = prepared_data.get('api_key')
            if api_key_geom and new_full_path:
                 try:
                     detailed_geometry = VRPService.get_detailed_route_geometry(new_full_path, api_key=api_key_geom)
                     updated_solution['routes'][target_vehicle_index]['detailed_path_geometry'] = detailed_geometry # Use correct key
                     print("[DEBUG insert_dynamic_locations] Successfully fetched detailed geometry for updated route.")
                 except Exception as geom_e:
                     print(f"[WARN insert_dynamic_locations] Failed to fetch detailed geometry for updated route: {geom_e}")
                     updated_solution['routes'][target_vehicle_index]['detailed_path_geometry'] = None
            elif not api_key_geom:
                 print("[WARN insert_dynamic_locations] No API key found in prepared_data, skipping detailed geometry fetch for updated route.")
                 updated_solution['routes'][target_vehicle_index]['detailed_path_geometry'] = None

            # Add information about the chosen strategy to the result
            updated_solution['test_info'] = updated_solution.get('test_info', {})
            updated_solution['test_info']['dynamic_insertion_strategy'] = chosen_strategy
            updated_solution['test_info']['strategy_A_distance'] = distance_A if distance_A != float('inf') else None
            updated_solution['test_info']['strategy_B_distance'] = distance_B if distance_B != float('inf') else None
            updated_solution['test_info']['original_warehouse'] = original_warehouse # Store original warehouse context

            updated_solution['status'] = 'success'
            return updated_solution

        except Exception as e:
            print(f"[ERROR insert_dynamic_locations] General exception during comparison: {e}")
            traceback.print_exc()
            # Ensure connection is closed if opened
            return {'status': 'error', 'message': f'Error during dynamic insertion comparison: {e}'}
        finally:
            if conn:
                try: conn.close()
                except: pass
            end_time_comparison = time.time()
            print(f"[INFO insert_dynamic_locations] Comparison and update finished in {end_time_comparison - start_time_comparison:.4f} seconds.")

    @staticmethod
    def _calculate_path_distance(path_nodes, matrix=None, node_map=None, ors_client=None, api_key=None): # Add api_key
        """Calculates distance for a path given as list of node dicts."""
        total_distance = 0.0
        if not path_nodes or len(path_nodes) < 2:
            return 0.0

        if matrix is not None and node_map is not None:
            loc_to_idx = {f"{loc['lat']:.6f},{loc['lon']:.6f}": idx for idx, loc in node_map.items()}
            indices = []
            for node in path_nodes:
                key = f"{node['lat']:.6f},{node['lon']:.6f}"
                idx = loc_to_idx.get(key)
                if idx is None:
                    print(f"[WARN _calculate_path_distance] Could not find matrix index for node: {node}")
                    return float('inf')
                indices.append(idx)

            for i in range(len(indices) - 1):
                idx1, idx2 = indices[i], indices[i+1]
                if 0 <= idx1 < matrix.shape[0] and 0 <= idx2 < matrix.shape[0]:
                    total_distance += matrix[idx1][idx2]
                else:
                    print(f"[ERROR _calculate_path_distance] Matrix index out of bounds: {idx1}, {idx2}")
                    return float('inf')
            return total_distance

        elif ors_client or api_key:
             print("[WARN _calculate_path_distance] Matrix/NodeMap missing or failed, falling back to ORS segment calls.")
             local_ors_client = ors_client
             if not local_ors_client and api_key:
                  local_ors_client = VRPService._get_ors_client(api_key)

             if not local_ors_client:
                  print("[ERROR _calculate_path_distance] ORS client unavailable for fallback calculation.")
                  return float('inf')

             total_distance = 0.0
             for i in range(len(path_nodes) - 1):
                  start_node = path_nodes[i]
                  end_node = path_nodes[i+1]
                  try:
                       coords = [[start_node['lon'], start_node['lat']], [end_node['lon'], end_node['lat']]]
                       route = local_ors_client.directions(coordinates=coords, profile='driving-car', format='json')
                       segment_distance = route['routes'][0]['summary']['distance'] / 1000.0 # Convert meters to km
                       total_distance += segment_distance
                  except Exception as e:
                       print(f"[ERROR _calculate_path_distance] ORS fallback failed for segment {i+1}: {e}")
                       dist_hav = VRPTestScenarioService._haversine_distance(start_node['lat'], start_node['lon'], end_node['lat'], end_node['lon'])
                       print(f"[WARN _calculate_path_distance] Using Haversine fallback for segment {i+1}: {dist_hav:.2f} km")
                       total_distance += dist_hav
             return total_distance

        else:
             print("[WARN _calculate_path_distance] Matrix/NodeMap and ORS client missing, falling back to Haversine.")
             total_distance = 0.0
             for i in range(len(path_nodes) - 1):
                  start_node = path_nodes[i]
                  end_node = path_nodes[i+1]
                  total_distance += VRPTestScenarioService._haversine_distance(start_node['lat'], start_node['lon'], end_node['lat'], end_node['lon'])
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

    @staticmethod
    def _get_cluster_for_location(conn, lat, lon):
        """
        Query the snapshot DB to find the cluster_id for given coordinates
        by joining locations and location_clusters tables.
        """
        # Ensure lat/lon are floats for reliable matching
        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except (ValueError, TypeError):
            print(f"[WARN _get_cluster_for_location] Invalid lat/lon format: ({lat}, {lon}). Cannot find cluster.")
            return None

        # Query using JOIN
        query = """
            SELECT lc.cluster_id
            FROM locations l
            JOIN location_clusters lc ON l.id = lc.location_id
            WHERE l.lat = ? AND l.lon = ?
            LIMIT 1
        """
        try:
            cursor = conn.execute(query, (lat_f, lon_f))
            row = cursor.fetchone()
            if row:
                return row['cluster_id']
            else:
                return None
        except sqlite3.Error as e:
            print(f"[ERROR _get_cluster_for_location] Database error querying cluster for ({lat_f}, {lon_f}): {e}")
            return None
        
    @staticmethod
    def _get_snapshot_db_path(snapshot_id):
        """Helper to construct the full path to the snapshot DB."""
        # Ensure snapshot_id has the correct extension for file path
        if not snapshot_id.endswith('.sqlite'):
            db_snapshot_filename = f"{snapshot_id}.sqlite"
        else:
            db_snapshot_filename = snapshot_id

        try:
             from flask import current_app
             base_path = os.path.join(current_app.root_path, "vrp_test_data")
        except ImportError:
             base_path = os.path.join(os.path.dirname(__file__), '..', 'vrp_test_data')
             print(f"[WARN _get_snapshot_db_path] Not in Flask context, using relative path: {base_path}")

        if not os.path.isdir(base_path):
             raise FileNotFoundError(f"Snapshot directory not found: {base_path}")

        # Basic validation to prevent path traversal
        if '..' in db_snapshot_filename or '/' in db_snapshot_filename or '\\' in db_snapshot_filename:
             raise ValueError(f"Invalid snapshot filename format: {db_snapshot_filename}")

        snapshot_path = os.path.join(base_path, db_snapshot_filename)
        if not os.path.isfile(snapshot_path):
             raise FileNotFoundError(f"Snapshot database file not found: {snapshot_path}")
        return snapshot_path
    
    @staticmethod
    def _get_street_stem(street_name):
        """
        Extracts the base part of a street name, removing specific suffixes/numbers.
        Example: 'Jalan Setia Indah U13/9W' -> 'Jalan Setia Indah'
                'Persiaran Setia Wawasan' -> 'Persiaran Setia Wawasan'
        Adjust the regex pattern based on observed street name formats.
        """
        if not street_name:
            return None
        # Pattern attempts to match common endings like U13/..., /..., numbers, letters after slashes/spaces
        # This might need refinement based on your specific data patterns
        match = re.match(r"^(.*?)(?:\s+(?:U\d+|\d+)\/\S*|\s+\d+[A-Z]?\s*|\s+\/\s*\S+)?$", street_name.strip())
        if match and match.group(1):
            return match.group(1).strip()
        return street_name.strip()