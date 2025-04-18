from flask import current_app
import os
import sqlite3
import json
import time
import traceback
import numpy as np
from services.vrp_service import VRPService
from services.vrp_testing_service import VRPTestingService
from algorithms.enhanced_vrp import EnhancedVehicleRoutingProblem
from services.cache_service import CacheService
import random
from math import radians, sin, cos, sqrt, atan2
import openrouteservice

class VRPTestScenarioService:

    @staticmethod
    def _get_ors_client():
        api_key = current_app.config.get('ORS_API_KEY')
        if not api_key:
            print("Warning: ORS_API_KEY not found in config. Using Haversine distance.")
            return None
        try:
            return openrouteservice.Client(key=api_key)
        except Exception as e:
            print(f"Error creating ORS client: {e}")
            return None

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
                checkpoints = [dict(row) for row in checkpoints_rows] # Convert rows to dicts
                print(f"[DEBUG prepare_test_data] Found {len(checkpoints)} raw checkpoints from DB.")
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

            cluster_to_checkpoints = {}
            checkpoint_to_clusters = {}

            for cp in checkpoints:
                cluster_id = cp['cluster_id']
                cluster_to_checkpoints.setdefault(cluster_id, []).append(cp)
                cp_key = f"{cp['lat']:.6f},{cp['lon']:.6f}"
                checkpoint_to_clusters.setdefault(cp_key, []).append(cluster_id)

            unique_checkpoints = {}
            for cp in checkpoints:
                cp_key = f"{cp['lat']:.6f},{cp['lon']:.6f}"
                if cp_key not in unique_checkpoints:
                    unique_checkpoints[cp_key] = {
                        'id': cp['id'],
                        'lat': cp['lat'],
                        'lon': cp['lon'],
                        'clusters': [cp['cluster_id']],
                        'from_type': cp.get('from_type'),
                        'to_type': cp.get('to_type'),
                        'confidence': cp['confidence']
                    }
                elif cp['cluster_id'] not in unique_checkpoints[cp_key]['clusters']:
                    unique_checkpoints[cp_key]['clusters'].append(cp['cluster_id'])

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
            ors_client = VRPTestScenarioService._get_ors_client() # Use helper to get client

            if ors_client:
                try:
                    print("[DEBUG prepare_test_data] Using OpenRouteService for checkpoint distance matrix.")
                    # Pass the client instance
                    matrix_list = VRPTestScenarioService._calculate_ors_distance_matrix(
                        ors_client, warehouse, active_routing_checkpoints
                    )
                    # Ensure it's a NumPy array for consistency and OR-Tools compatibility
                    checkpoint_distance_matrix = np.array(matrix_list)
                    distance_type = 'road_network'
                    print("[DEBUG prepare_test_data] Successfully calculated ORS distance matrix.")

                except Exception as e:
                    print(f"[ERROR prepare_test_data] Failed to calculate ORS distance matrix: {e}")
                    # Return an error dictionary immediately if ORS fails
                    conn.close()
                    return {'status': 'error', 'message': f"Failed to get ORS distance matrix: {e}"}
            else:
                # No API key or client creation failed
                print("[ERROR prepare_test_data] ORS client not available. Cannot calculate road network distances.")
                conn.close()
                return {'status': 'error', 'message': "ORS client/API key not available for distance calculation."}
            # --- End Distance Matrix ---

            conn.close() # Close DB connection after use

            prepared_dataset = {
                'warehouse': warehouse,
                'destinations': destinations,
                'required_clusters': list(required_clusters),
                'active_routing_checkpoints': active_routing_checkpoints, # Pass the actual list of unique checkpoints
                # Store checkpoints by their matrix index (1 to N) for easier lookup later
                'checkpoint_indices': {idx + 1: cp for idx, cp in enumerate(active_routing_checkpoints)},
                'checkpoint_to_clusters': checkpoint_to_clusters,
                'checkpoint_distance_matrix': checkpoint_distance_matrix, # Store as NumPy array
                'has_clusters': True,
                'distance_type': distance_type,
                'api_key': api_key # Pass API key for potential detailed path fetching
            }
            
            return prepared_dataset
        except Exception as e:
            traceback.print_exc()
            if 'conn' in locals() and conn:
                conn.close()
            return None

    @staticmethod
    def _calculate_ors_distance_matrix(client, warehouse, checkpoints):
        """Calculate distance matrix using OpenRouteService. Returns list of lists."""
        if not warehouse or not checkpoints:
            print("[WARN _calculate_ors_distance_matrix] Warehouse or checkpoints list is empty.")
            return [] # Return empty list, let caller handle

        # ORS expects [lon, lat]
        locations = [[float(warehouse['lon']), float(warehouse['lat'])]]
        locations.extend([[float(cp['lon']), float(cp['lat'])] for cp in checkpoints])
        n = len(locations)
        print(f"[DEBUG _calculate_ors_distance_matrix] Requesting matrix for {n} locations.")

        try:
            matrix_result = client.distance_matrix(
                locations=locations,
                metrics=['distance'],
                units='km'
            )
            # Basic validation
            if 'distances' not in matrix_result or len(matrix_result['distances']) != n or \
               not all(len(row) == n for row in matrix_result['distances']):
                raise ValueError(f"ORS response format unexpected or matrix size incorrect. Expected ({n},{n})")

            print("[DEBUG _calculate_ors_distance_matrix] Received valid matrix response.")
            return matrix_result['distances'] # Return list of lists

        except openrouteservice.exceptions.ApiError as api_error:
            print(f"[ERROR _calculate_ors_distance_matrix] ORS API Error: {api_error}. Status: {api_error.status_code}. Message: {api_error.message}")
            # Re-raise to be caught by the caller
            raise ConnectionError(f"ORS API Error: {api_error.message}") from api_error
        except Exception as e:
            print(f"[ERROR _calculate_ors_distance_matrix] Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            # Re-raise to be caught by the caller
            raise RuntimeError(f"Unexpected error during ORS matrix calculation: {e}") from e

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
            if isinstance(prepared_data['checkpoint_distance_matrix'], list):
                 prepared_data['checkpoint_distance_matrix'] = np.array(prepared_data['checkpoint_distance_matrix'])

            # Call the enhanced solver's solve method
            solution = enhanced_vrp_solver.solve(prepared_data, algorithm=algorithm)

            # Check for solver errors
            if 'error' in solution:
                 print(f"[ERROR TestScenarioService] Enhanced solver returned an error: {solution['error']}")
                 # Add timing info even to error response
                 solution['execution_time_ms'] = int((time.time() - start_time) * 1000)
                 solution['computation_time'] = time.time() - start_time
                 return solution # Return the error dict from the solver

            # --- Add Detailed Path Geometry (Modified Logic) ---
            if 'routes' in solution and solution['routes']:
                print("[DEBUG run_checkpoint_vrp_scenario] Fetching detailed route geometry (segment-aware)...")
                api_key = prepared_data.get('api_key')
                destinations = prepared_data.get('destinations', [])
                # Get mapping from checkpoint index (1+) to cluster set {id1, id2,...}
                idx_to_cluster_set = prepared_data.get('idx_to_cluster_set', {})
                # Get mapping from checkpoint index (1+) to checkpoint data {'lat':..., 'lon':...}
                checkpoint_indices_map = prepared_data.get('checkpoint_indices', {})

                for i, route in enumerate(solution['routes']):
                    print(f"[DEBUG run_checkpoint_vrp_scenario] Processing route {i+1} for detailed path.")
                    route_detailed_geometry = []
                    # route['path'] contains dicts: [{'lat':..., 'lon':..., 'type':'warehouse/checkpoint', 'matrix_idx': optional_int}, ...]
                    path_sequence = route.get('path', [])

                    if len(path_sequence) < 2:
                        solution['routes'][i]['detailed_path_geometry'] = None
                        continue # Skip if path is too short

                    # Iterate through segments (P1 -> P2)
                    for j in range(len(path_sequence) - 1):
                        p1 = path_sequence[j]
                        p2 = path_sequence[j+1]

                        segment_geometry = None
                        try_cluster_routing = False
                        shared_cluster_id = None

                        # Check if both are checkpoints and share a cluster
                        if p1.get('type') == 'checkpoint' and p2.get('type') == 'checkpoint':
                            idx1 = p1.get('matrix_idx')
                            idx2 = p2.get('matrix_idx')
                            if idx1 is not None and idx2 is not None and idx1 != idx2: # Ensure different checkpoints
                                clusters1 = idx_to_cluster_set.get(idx1, set())
                                clusters2 = idx_to_cluster_set.get(idx2, set())
                                common_clusters = clusters1.intersection(clusters2)
                                if common_clusters:
                                    try_cluster_routing = True
                                    # Use the first common cluster found for simplicity
                                    shared_cluster_id = list(common_clusters)[0]
                                    print(f"[DEBUG run_checkpoint_vrp_scenario]   Segment {j+1}: CP {idx1} -> CP {idx2} share Cluster {shared_cluster_id}. Attempting routing through cluster.")

                        if try_cluster_routing and shared_cluster_id is not None:
                            # Calculate centroid for the shared cluster
                            cluster_centroid = VRPTestScenarioService._calculate_cluster_centroid(shared_cluster_id, destinations)

                            if cluster_centroid:
                                print(f"[DEBUG run_checkpoint_vrp_scenario]     -> Calculated centroid for Cluster {shared_cluster_id}: {cluster_centroid}")
                                # Request P1 -> Centroid
                                geom1 = VRPService.get_detailed_route_geometry([p1, cluster_centroid], api_key)
                                # Request Centroid -> P2
                                geom2 = VRPService.get_detailed_route_geometry([cluster_centroid, p2], api_key)

                                if geom1 and geom2:
                                    # Stitch geometries, avoiding duplicate centroid point
                                    segment_geometry = geom1[:-1] + geom2
                                    print(f"[DEBUG run_checkpoint_vrp_scenario]     -> Successfully stitched path through centroid.")
                                else:
                                    print(f"[WARN run_checkpoint_vrp_scenario]     -> Failed to get path via centroid. Falling back to direct P1->P2.")
                                    # Fallback to direct routing if via-centroid fails
                                    segment_geometry = VRPService.get_detailed_route_geometry([p1, p2], api_key)
                            else:
                                print(f"[WARN run_checkpoint_vrp_scenario]     -> Could not calculate centroid for Cluster {shared_cluster_id}. Falling back to direct P1->P2.")
                                segment_geometry = VRPService.get_detailed_route_geometry([p1, p2], api_key)
                        else:
                            # Default: Direct routing P1 -> P2
                            print(f"[DEBUG run_checkpoint_vrp_scenario]   Segment {j+1}: Direct routing {p1.get('type','?')}(idx {p1.get('matrix_idx','N/A')}) -> {p2.get('type','?')}(idx {p2.get('matrix_idx','N/A')}).")
                            segment_geometry = VRPService.get_detailed_route_geometry([p1, p2], api_key)

                        # Append segment geometry (if valid)
                        if segment_geometry:
                            # Add all points except the first one if it's not the very first segment
                            # This avoids duplicating the connection points
                            start_index = 1 if j > 0 else 0
                            route_detailed_geometry.extend(segment_geometry[start_index:])

                    if route_detailed_geometry:
                         print(f"[DEBUG run_checkpoint_vrp_scenario]   Route {i+1} final detailed geometry points: {len(route_detailed_geometry)}")
                         solution['routes'][i]['detailed_path_geometry'] = route_detailed_geometry
                    else:
                         print(f"[WARN run_checkpoint_vrp_scenario]   Route {i+1} failed to generate any detailed geometry.")
                         solution['routes'][i]['detailed_path_geometry'] = None

            # --- End Detailed Path ---

            end_time = time.time()
            computation_time = end_time - start_time

            # Add timing and distance type info to the solution
            solution['execution_time_ms'] = int(computation_time * 1000)
            # computation_time is already added by solve()
            solution['distance_type'] = prepared_data.get('distance_type', 'unknown')
            # algorithm_used is already added by solve()

            print(f"[DEBUG TestScenarioService] Checkpoint scenario finished. Algorithm used: {solution.get('algorithm_used', 'N/A')}, Total distance: {solution.get('total_distance', 0):.2f} km")
            return solution

        except (ValueError, ConnectionError, RuntimeError) as e:
             # Catch errors from distance matrix calculation or ORS API in prepare_data or solver
             print(f"[ERROR TestScenarioService] Failed during VRP solving or ORS communication: {e}")
             return {'status': 'error', 'message': str(e), 'execution_time_ms': int((time.time() - start_time) * 1000)}
        except Exception as e:
             print(f"[ERROR TestScenarioService] Exception in run_checkpoint_vrp_scenario: {e}")
             import traceback
             traceback.print_exc()
             return {
                 'status': 'error',
                 'message': f"Error running checkpoint scenario: {e}",
                 'execution_time_ms': int((time.time() - start_time) * 1000)
             }