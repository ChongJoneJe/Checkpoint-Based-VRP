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
        """
        Prepare dataset for testing by loading clusters and checkpoints
        Includes caching for the checkpoint distance matrix.
        """
        cache_service = CacheService()
        # Define a cache key based on snapshot and preset
        cache_key = f"checkpoint_matrix_{snapshot_id}_{preset_id}"

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
                       cp.confidence, cp.source, c.name as cluster_name
                FROM security_checkpoints cp
                JOIN clusters c ON cp.cluster_id = c.id
                WHERE cp.cluster_id IN ({})
            """.format(','.join('?' * len(required_clusters)))

            try:
                checkpoints = [
                    {
                        'id': row['id'],
                        'lat': row['lat'],
                        'lon': row['lon'],
                        'cluster_id': row['cluster_id'],
                        'cluster_name': row['cluster_name'],
                        'confidence': row['confidence'],
                        'source': row['source']
                    }
                    for row in conn.execute(checkpoints_query, list(required_clusters))
                ]
            except sqlite3.OperationalError as db_error:
                print(f"Database error executing checkpoints query: {db_error}")
                conn.close()
                # Return a more specific error message
                return {'status': 'error', 'message': f"DB error fetching checkpoints: {db_error}"}
            except Exception as query_error:
                print(f"Unexpected error executing checkpoints query: {query_error}")
                conn.close()
                return {'status': 'error', 'message': f"Error fetching checkpoints: {query_error}"}

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

            # --- Distance Matrix Calculation with Caching and Road Networks ---
            checkpoint_distance_matrix = cache_service.get(cache_key)
            distance_type = 'cached'  # Default if using cached matrix
            
            if checkpoint_distance_matrix:
                print(f"Cache hit for distance matrix: {cache_key}")
            else:
                print(f"Cache miss for distance matrix: {cache_key}. Calculating...")
                
                # Try using road network first if API key provided
                if api_key:
                    try:
                        client = openrouteservice.Client(key=api_key)
                        checkpoint_distance_matrix = VRPTestScenarioService._calculate_ors_distance_matrix(
                            client, warehouse, active_routing_checkpoints)
                        distance_type = 'road_network'
                        print("Using OpenRouteService for distance matrix")
                    except Exception as e:
                        print(f"Error using OpenRouteService: {str(e)}")
                        # Fall back to Haversine
                        checkpoint_distance_matrix = VRPTestScenarioService._calculate_haversine_distance_matrix(
                            warehouse, active_routing_checkpoints)
                        distance_type = 'haversine'
                        print("Fallback to Haversine distance calculation")
                else:
                    # No API key, use Haversine
                    checkpoint_distance_matrix = VRPTestScenarioService._calculate_haversine_distance_matrix(
                        warehouse, active_routing_checkpoints)
                    distance_type = 'haversine'
                    print("Using Haversine distance calculation (no API key)")
                    
                # Store in cache
                cache_service.set(cache_key, checkpoint_distance_matrix, timeout=3600)

            conn.close()

            # Return the prepared dataset with distance_type
            prepared_dataset = {
                'warehouse': warehouse,
                'destinations': destinations,
                'required_clusters': list(required_clusters),
                'active_routing_checkpoints': active_routing_checkpoints,
                'cluster_to_checkpoints': cluster_to_checkpoints,
                'checkpoint_to_clusters': checkpoint_to_clusters,
                'checkpoint_distance_matrix': checkpoint_distance_matrix,
                'has_clusters': True,
                'distance_type': distance_type
            }
            
            return prepared_dataset
        except Exception as e:
            traceback.print_exc()
            if 'conn' in locals() and conn:
                conn.close()
            return None

    @staticmethod
    def _calculate_haversine_distance_matrix(warehouse, checkpoints):
        """Calculate distance matrix using Haversine distance"""
        if not warehouse or not checkpoints:
            return []

        n = 1 + len(checkpoints)
        distance_matrix = np.zeros((n, n))
        nodes = [{'lat': warehouse['lat'], 'lon': warehouse['lon']}]
        nodes.extend(checkpoints)

        for i in range(n):
            for j in range(i+1, n):
                if isinstance(nodes[i], dict) and isinstance(nodes[j], dict) and \
                   'lat' in nodes[i] and 'lon' in nodes[i] and \
                   'lat' in nodes[j] and 'lon' in nodes[j]:
                    dist = VRPTestScenarioService._haversine_distance(
                        nodes[i]['lat'], nodes[i]['lon'],
                        nodes[j]['lat'], nodes[j]['lon']
                    )
                    distance_matrix[i][j] = dist
                    distance_matrix[j][i] = dist
                else:
                    print(f"Warning: Invalid node structure at indices {i}, {j}")
                    distance_matrix[i][j] = float('inf')
                    distance_matrix[j][i] = float('inf')

        return distance_matrix.tolist()

    @staticmethod
    def _calculate_ors_distance_matrix(client, warehouse, checkpoints):
        """Calculate distance matrix using OpenRouteService"""
        if not warehouse or not checkpoints:
            return []

        locations = [[warehouse['lon'], warehouse['lat']]]
        locations.extend([[cp['lon'], cp['lat']] for cp in checkpoints])

        try:
            matrix_result = client.distance_matrix(
                locations=locations,
                metrics=['distance'],
                units='km'
            )
            n = len(locations)
            if 'distances' in matrix_result and len(matrix_result['distances']) == n and \
               all(len(row) == n for row in matrix_result['distances']):
                return matrix_result['distances']
            else:
                raise ValueError("ORS response format unexpected or matrix size incorrect.")

        except openrouteservice.exceptions.ApiError as api_error:
            print(f"ORS API Error: {api_error}. Status: {api_error.status_code}. Message: {api_error.message}")
            raise
        except Exception as e:
            print(f"Error during ORS matrix calculation: {e}")
            raise

    @staticmethod
    def _haversine_distance(lat1, lon1, lat2, lon2):
        """Calculate the Haversine distance between two points in km"""
        lat1, lon1, lat2, lon2 = map(float, [lat1, lon1, lat2, lon2])
        lat1_rad, lon1_rad = radians(lat1), radians(lon1)
        lat2_rad, lon2_rad = radians(lat2), radians(lon2)

        dlon = lon2_rad - lon1_rad
        dlat = lat2_rad - lat1_rad
        a = sin(dlat/2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        r = 6371
        return r * c

    @staticmethod
    def run_checkpoint_vrp_scenario(prepared_data, num_vehicles=1, algorithm='or_tools'):
        """Run a checkpoint-based VRP scenario using EnhancedVRP."""
        print(f"[DEBUG TestScenarioService] run_checkpoint_vrp_scenario called. Algorithm requested: {algorithm}")
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
            # Note: EnhancedVRP __init__ might need adjustment if it expects different args now
            enhanced_vrp_solver = EnhancedVehicleRoutingProblem(
                warehouse=prepared_data['warehouse'],
                destinations=prepared_data['destinations'], # Pass original destinations for context
                num_vehicles=num_vehicles
                # Removed args like checkpoints, clusters, distance_matrix, api_key from init
                # as solve() now takes prepared_data
            )

            # Call the enhanced solver's solve method
            solution = enhanced_vrp_solver.solve(prepared_data, algorithm=algorithm)

            # Check for solver errors
            if 'error' in solution:
                 print(f"[ERROR TestScenarioService] Enhanced solver returned an error: {solution['error']}")
                 # Add timing info even to error response
                 solution['execution_time_ms'] = int((time.time() - start_time) * 1000)
                 solution['computation_time'] = time.time() - start_time
                 return solution # Return the error dict from the solver

            end_time = time.time()
            computation_time = end_time - start_time

            # Add timing and distance type info to the solution
            solution['execution_time_ms'] = int(computation_time * 1000)
            # computation_time is already added by solve()
            solution['distance_type'] = prepared_data.get('distance_type', 'unknown')
            # algorithm_used is already added by solve()

            print(f"[DEBUG TestScenarioService] Checkpoint scenario finished. Total distance: {solution.get('total_distance', 0):.2f} km")
            return solution

        except Exception as e:
             print(f"[ERROR TestScenarioService] Exception in run_checkpoint_vrp_scenario: {e}")
             import traceback
             traceback.print_exc()
             return {
                 'status': 'error',
                 'message': f"Error running checkpoint scenario: {e}",
                 'execution_time_ms': int((time.time() - start_time) * 1000)
             }