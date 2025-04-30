from flask import Blueprint, render_template, request, jsonify, current_app
from services.vrp_service import VRPService
from services.preset_service import PresetService
from services.vrp_testing_service import VRPTestingService, NumpyEncoder
from services.cache_service import CacheService
from services.test_scenario_service import VRPTestScenarioService
from algorithms.dbscan import GeoDBSCAN
from utils.database import execute_read
from save_db import create_database_snapshot
import os
import json
import numpy as np
import traceback
from datetime import datetime
import sqlite3

vrp_testing_bp = Blueprint('vrp_testing', __name__, url_prefix='/vrp_testing')

@vrp_testing_bp.route('/', methods=['GET'])
def vrp_testing_dashboard():
    """Dashboard for VRP testing and comparison"""
    snapshots = VRPTestingService.get_snapshots()
    return render_template('vrp_testing.html', snapshots=snapshots)

@vrp_testing_bp.route('/snapshots', methods=['GET'])
def get_snapshots():
    """Get all available database snapshots"""
    snapshots = VRPTestingService.get_snapshots()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'status': 'success',
            'snapshots': snapshots
        })

    return snapshots

@vrp_testing_bp.route('/create_snapshot', methods=['POST'])
def create_snapshot():
    """Create a new database snapshot"""
    try:
        snapshot_info = create_database_snapshot()

        if not snapshot_info:
            return jsonify({
                'status': 'error',
                'message': 'Failed to create snapshot'
            })

        return jsonify({
            'status': 'success',
            'snapshot': snapshot_info
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': f"Error creating snapshot: {str(e)}"
        })

@vrp_testing_bp.route('/delete_snapshot/<snapshot_id>', methods=['POST'])
def delete_snapshot(snapshot_id):
    """Delete a database snapshot"""
    success, message = VRPTestingService.delete_snapshot(snapshot_id)

    if success:
        return jsonify({
            'status': 'success',
            'message': message
        })
    else:
        return jsonify({
            'status': 'error',
            'message': message
        })

@vrp_testing_bp.route('/presets/<snapshot_id>', methods=['GET'])
def get_snapshot_presets(snapshot_id):
    """Get presets from a specific snapshot"""
    try:
        # Ensure snapshot_id has the correct extension if needed by VRPTestingService
        if not snapshot_id.endswith('.sqlite'):
            snapshot_id_db = f"{snapshot_id}.sqlite"
        else:
            snapshot_id_db = snapshot_id

        snapshot_path = os.path.join(current_app.root_path, "vrp_test_data", snapshot_id_db)

        if not os.path.exists(snapshot_path):
            return jsonify({
                'status': 'error',
                'message': 'Snapshot not found'
            })

        presets = VRPTestingService.get_presets_from_snapshot(snapshot_path)

        return jsonify({
            'status': 'success',
            'presets': presets
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': f"Error: {str(e)}"
        })

@vrp_testing_bp.route('/run_test', methods=['POST'])
def run_test():
    """Run VRP test based on selected type (static, checkpoints, dynamic)"""
    data = request.json

    required_fields = ['snapshot_id', 'preset_id', 'num_vehicles', 'test_type']
    if not data or not all(field in data for field in required_fields):
        return jsonify({'status': 'error', 'message': 'Missing required parameters'})

    snapshot_id = data['snapshot_id'] # Should not include .sqlite here, handled by services
    preset_id = data['preset_id']
    algorithm = data.get('algorithm', 'two_opt')  # Default to NN+2Opt
    num_vehicles = int(data.get('num_vehicles', 1))  # Ensure num_vehicles is extracted correctly
    test_type = data.get('test_type', 'static')
    api_key = data.get('api_key') or current_app.config.get('ORS_API_KEY')

    try:
        # Ensure snapshot_id has the correct extension for path checking
        if not snapshot_id.endswith('.sqlite'):
            snapshot_id_db = f"{snapshot_id}.sqlite"
        else:
            snapshot_id_db = snapshot_id
        snapshot_path = os.path.join(current_app.root_path, "vrp_test_data", snapshot_id_db)
        if not os.path.exists(snapshot_path):
            return jsonify({'status': 'error', 'message': 'Snapshot not found'})

        solution = None
        prepared_data = None

        if test_type == 'static':
            preset_data_basic = VRPTestingService.get_preset_from_snapshot(snapshot_path, preset_id)
            if not preset_data_basic:
                return jsonify({'status': 'error', 'message': 'Preset not found or invalid'})

            print(f"[DEBUG Route] Calling VRPService.solve_vrp for static test with algorithm: {algorithm}")
            solution = VRPService.solve_vrp(
                warehouse=preset_data_basic['warehouse'],
                destinations=preset_data_basic['destinations'],
                num_vehicles=num_vehicles,  # Pass num_vehicles
                algorithm=algorithm,  # Pass the selected algorithm
                api_key=api_key  # Pass API key here
            )
            solution['distance_type'] = solution.get('distance_type', 'haversine')

        elif test_type == 'checkpoints' or test_type == 'dynamic':
            # Prepare data (includes distance matrix calculation for checkpoints)
            # Pass snapshot_id WITHOUT extension to prepare_test_data
            prepared_data = VRPTestScenarioService.prepare_test_data(
                snapshot_id, preset_id, api_key=api_key
            )

            if not prepared_data:
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to prepare test data - no data returned.'
                })

            if prepared_data.get('status') == 'error':
                return jsonify({
                    'status': 'error',
                    'message': prepared_data.get('message', 'Failed to prepare test data.')
                })

            if not prepared_data.get('has_clusters', False):
                return jsonify({
                    'status': 'error',
                    'message': 'Test data missing required cluster information. Try with a different preset or snapshot.'
                })

            # Add api_key to prepared_data if not already present (prepare_test_data should handle this)
            # prepared_data['api_key'] = api_key

            print(f"[DEBUG Route] Calling VRPTestScenarioService.run_checkpoint_vrp_scenario. Algorithm: {algorithm}, Vehicles: {num_vehicles}")
            solution = VRPTestScenarioService.run_checkpoint_vrp_scenario(
                prepared_data,
                num_vehicles=num_vehicles,  # Pass num_vehicles
                algorithm=algorithm  # Pass 'two_opt' or 'or_tools'
            )

        else:
            return jsonify({'status': 'error', 'message': f'Invalid test type: {test_type}'})

        # --- Prepare test_info ---
        solution['test_info'] = {
            'snapshot_id': snapshot_id, # Store ID without extension
            'preset_id': preset_id,
            'algorithm': algorithm,  # Store the algorithm requested by the user
            'num_vehicles': num_vehicles,  # Store the requested number
            'test_type': test_type,
            'timestamp': datetime.now().isoformat(),
            'distance_type': solution.get('distance_type', 'unknown'),
            'algorithm_used': solution.get('algorithm_used', algorithm)  # Add algorithm actually used by the solver for clarity
        }

        # --- Save result to vrp_tests.db ---
        # Ensure the solution is serializable before saving
        serializable_solution = json.loads(json.dumps(solution, cls=NumpyEncoder))
        test_id = VRPTestingService.save_test_result(serializable_solution)
        solution['id'] = test_id # Add the new ID to the returned solution
        solution['test_info']['test_id'] = test_id # Also add to test_info
        current_app.logger.info(f"Test run saved with ID: {test_id}")
        # --- End Save ---

        # Prepare data reference for potential dynamic insertion (only needed fields)
        prepared_data_ref = {
            'snapshot_id': snapshot_id, # ID without extension
            'preset_id': preset_id,
            'api_key': api_key # Include API key if needed for re-preparation
        }

        return jsonify({
            'status': 'success',
            'solution': json.loads(json.dumps(solution, cls=NumpyEncoder)),
            'prepared_data_ref': prepared_data_ref # Send back reference for dynamic insertion
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': f"Error running test: {str(e)}"})

@vrp_testing_bp.route('/process_dynamic_pair', methods=['POST'])
def process_dynamic_pair():
    """Geocode, cluster, and find checkpoints for a new dynamic location pair."""
    data = request.json
    required_fields = ['pickup_lat', 'pickup_lon', 'dropoff_lat', 'dropoff_lon', 'snapshot_id', 'preset_id']
    if not data or not all(field in data for field in required_fields):
        return jsonify({'status': 'error', 'message': 'Missing required parameters for processing pair.'})

    try:
        pickup_lat = float(data['pickup_lat'])
        pickup_lon = float(data['pickup_lon'])
        dropoff_lat = float(data['dropoff_lat'])
        dropoff_lon = float(data['dropoff_lon'])
        snapshot_id = data['snapshot_id'] # ID without extension
        preset_id = data['preset_id']

        api_key = current_app.config.get('ORS_API_KEY')
        geo_dbscan = GeoDBSCAN(api_key=api_key)

        # Get preset data for warehouse coordinates (optional, might not be needed here)
        # warehouse_lat = data.get('warehouse_lat')
        # warehouse_lon = data.get('warehouse_lon')

        # Process Pickup Location - first just geocode it
        print(f"[DEBUG /process_dynamic_pair] Processing Pickup: ({pickup_lat}, {pickup_lon})")
        pickup_address = geo_dbscan.geocode_location(pickup_lat, pickup_lon)

        # Process Dropoff Location - first just geocode it
        print(f"[DEBUG /process_dynamic_pair] Processing Dropoff: ({dropoff_lat}, {dropoff_lon})")
        dropoff_address = geo_dbscan.geocode_location(dropoff_lat, dropoff_lon)

        # Now work with the snapshot DB for clustering
        # Ensure snapshot_id has the correct extension for DB access
        if not snapshot_id.endswith('.sqlite'):
            snapshot_id_db = f"{snapshot_id}.sqlite"
        else:
            snapshot_id_db = snapshot_id

        snapshot_path = os.path.join(current_app.root_path, "vrp_test_data", snapshot_id_db)
        db_path = snapshot_path  # Use the .sqlite file directly

        print(f"[DEBUG /process_dynamic_pair] Using database path: {db_path}")

        if not os.path.exists(db_path):
            return jsonify({
                'status': 'error',
                'message': f'Snapshot database not found at {db_path}'
            })

        # --- CORRECTED CALLS ---
        # Process pickup clustering using snapshot DB path
        pickup_cluster_id, pickup_loc_id = process_location_in_snapshot(
            db_path, pickup_lat, pickup_lon, pickup_address # Pass db_path, remove geo_dbscan
        )

        # Process dropoff clustering using snapshot DB path
        dropoff_cluster_id, dropoff_loc_id = process_location_in_snapshot(
            db_path, dropoff_lat, dropoff_lon, dropoff_address # Pass db_path, remove geo_dbscan
        )
        # --- END CORRECTION ---

        # --- Re-open connection if needed for checkpoint fetching ---
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        # ---

        # Get checkpoints for pickup cluster
        pickup_checkpoints = []
        if pickup_cluster_id:
            # Use the cursor from the re-opened connection
            cursor.execute(
                "SELECT id, lat, lon FROM security_checkpoints WHERE cluster_id = ?",
                (pickup_cluster_id,)
            )
            pickup_checkpoints = [dict(cp) for cp in cursor.fetchall()] or []

        # Get checkpoints for dropoff cluster
        dropoff_checkpoints = []
        if dropoff_cluster_id:
            # Use the cursor from the re-opened connection
            cursor.execute(
                "SELECT id, lat, lon FROM security_checkpoints WHERE cluster_id = ?",
                (dropoff_cluster_id,)
            )
            dropoff_checkpoints = [dict(cp) for cp in cursor.fetchall()] or []

        conn.close() # Close the connection used for checkpoint fetching

        pair_info = {
            'pickup': {
                'lat': pickup_lat,
                'lon': pickup_lon,
                'location_id': pickup_loc_id,
                'cluster_id': pickup_cluster_id,
                'address': pickup_address,
                'checkpoints': pickup_checkpoints
            },
            'dropoff': {
                'lat': dropoff_lat,
                'lon': dropoff_lon,
                'location_id': dropoff_loc_id,
                'cluster_id': dropoff_cluster_id,
                'address': dropoff_address,
                'checkpoints': dropoff_checkpoints
            }
        }

        return jsonify({'status': 'success', 'pair_info': pair_info})

    except ValueError as ve:
        print(f"[ERROR /process_dynamic_pair] Value error: {ve}")
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': f"Invalid input data: {str(ve)}"})
    except Exception as e:
        print(f"[ERROR /process_dynamic_pair] Unexpected error: {e}")
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': f"Error processing dynamic pair: {str(e)}"})

def process_location_in_snapshot(snapshot_db_path, lat, lon, address_details):
    """
    Assigns a cluster to the location based on snapshot data, mimicking GeoDBSCAN logic.
    1. Tries matching street stem pattern.
    2. If no match, finds the nearest cluster centroid.
    Ensures location and cluster assignment exist in the snapshot DB.
    Returns the assigned cluster_id and location_id.
    """
    conn = None
    assigned_cluster_id = None
    location_id = None
    street_name = address_details.get('street')

    try:
        conn = sqlite3.connect(snapshot_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 1. Try Street Stem Pattern Matching
        street_stem = VRPTestScenarioService._get_street_stem(street_name)
        print(f"[DEBUG process_location] Original Street: '{street_name}', Stem: '{street_stem}'")
        if street_stem:
            cursor.execute(
                "SELECT cluster_id FROM street_patterns WHERE stem_pattern = ?",
                (street_stem,)
            )
            pattern_match = cursor.fetchone()
            if pattern_match:
                assigned_cluster_id = pattern_match['cluster_id']
                print(f"[DEBUG process_location] Found cluster {assigned_cluster_id} via street stem pattern '{street_stem}'.")

        # 2. If no pattern match, find nearest cluster centroid
        if assigned_cluster_id is None:
            print(f"[DEBUG process_location] No street stem match for '{street_stem}'. Finding nearest centroid...")
            cursor.execute("SELECT id, centroid_lat, centroid_lon FROM clusters WHERE centroid_lat IS NOT NULL AND centroid_lon IS NOT NULL")
            centroids = cursor.fetchall()

            if not centroids:
                print("[WARN process_location] No cluster centroids found in the snapshot DB.")
                # Handle this case - maybe assign a default cluster or raise an error?
                # For now, we'll proceed without a cluster ID.
                assigned_cluster_id = None
            else:
                min_dist = float('inf')
                nearest_cluster_id = None
                for centroid in centroids:
                    dist = VRPTestScenarioService._haversine_distance(lat, lon, centroid['centroid_lat'], centroid['centroid_lon'])
                    if dist < min_dist:
                        min_dist = dist
                        nearest_cluster_id = centroid['id']

                if nearest_cluster_id is not None:
                    assigned_cluster_id = nearest_cluster_id
                    print(f"[DEBUG process_location] Assigned cluster {assigned_cluster_id} (nearest centroid) at distance {min_dist:.4f} km.")
                else:
                    # Should not happen if centroids list is not empty, but handle defensively
                    print("[WARN process_location] Could not determine nearest centroid despite having centroid data.")
                    assigned_cluster_id = None

        # 3. Ensure location exists and cluster link is set in the snapshot DB
        # Use the helper function (assuming it's correctly defined in VRPTestScenarioService)
        location_id = VRPTestScenarioService._ensure_location_in_snapshot(conn, lat, lon, address_details, assigned_cluster_id)
        print(f"[DEBUG process_location] Ensured location ID {location_id} with assigned cluster {assigned_cluster_id}.")

        conn.close()
        return assigned_cluster_id, location_id

    except sqlite3.Error as e:
        print(f"[ERROR process_location] Database error: {e}")
        if conn: conn.close()
        return None, None # Indicate failure
    except Exception as e:
        print(f"[ERROR process_location] Unexpected error: {e}")
        traceback.print_exc()
        if conn: conn.close()
        return None, None

@vrp_testing_bp.route('/insert_dynamic', methods=['POST'])
def insert_dynamic():
    """Recalculates a route after inserting new dynamic location pairs."""
    data = request.json
    # Define required fields for the request body
    required_fields = ['current_solution', 'prepared_data_ref', 'new_location_pairs', 'target_vehicle_index', 'insertion_point_index', 'algorithm']

    # Check for missing fields in the received data
    missing = [field for field in required_fields if field not in (data or {})]

    # If data is missing or required fields are absent, return an error
    if not data or missing:
        error_msg = f"Missing required parameters for dynamic insertion. Missing: {missing}. Received keys: {list(data.keys()) if data else 'None'}"
        current_app.logger.error(error_msg)
        # Return 400 Bad Request for missing parameters
        return jsonify({'status': 'error', 'message': error_msg}), 400

    try:
        # Extract data from the request
        current_solution = data['current_solution']
        prepared_data_ref = data['prepared_data_ref'] # Contains snapshot_id, preset_id, api_key etc.
        new_location_pairs = data['new_location_pairs'] # The array of P/D pairs from JS
        target_vehicle_index = int(data['target_vehicle_index']) # Index of the vehicle route to modify
        insertion_point_index = int(data['insertion_point_index']) # Index within the vehicle's stops list *after* which to insert
        algorithm = data.get('algorithm', 'or_tools') # Algorithm used for the initial run (influences Strategy A/B comparison)

        # Validate the structure of new_location_pairs minimally
        if not isinstance(new_location_pairs, list) or not all('pickup' in p and 'dropoff' in p for p in new_location_pairs):
             current_app.logger.error(f"Invalid format for new_location_pairs: {new_location_pairs}")
             return jsonify({'status': 'error', 'message': 'Invalid format for new_location_pairs.'}), 400

        # Re-prepare the necessary test data using the references provided.
        # This ensures the distance matrix, node maps, etc., are available for the service function.
        api_key = prepared_data_ref.get('api_key') or current_app.config.get('ORS_API_KEY')
        snapshot_id = prepared_data_ref.get('snapshot_id') # ID without extension
        preset_id = prepared_data_ref.get('preset_id')

        if not snapshot_id or not preset_id:
             error_msg = "Missing snapshot_id or preset_id in prepared_data_ref."
             current_app.logger.error(error_msg)
             return jsonify({'status': 'error', 'message': error_msg}), 400

        # Call the service function to prepare the data again
        # Pass snapshot_id WITHOUT extension
        prepared_data = VRPTestScenarioService.prepare_test_data(
            snapshot_id=snapshot_id,
            preset_id=preset_id,
            api_key=api_key
        )

        # Check if prepare_test_data returned an error structure or was None
        if not prepared_data or prepared_data.get('status') == 'error':
            error_msg = prepared_data.get('message', 'Failed to re-prepare test data for insertion') if prepared_data else 'Failed to re-prepare test data for insertion (None returned)'
            current_app.logger.error(f"Error re-preparing data for dynamic insertion: {error_msg}")
            return jsonify({'status': 'error', 'message': error_msg}), 500

        # --- Add Detailed Logging Before Calling insert_dynamic_locations ---
        current_app.logger.debug(f"[/insert_dynamic] Data PREPARED. Type: {type(prepared_data)}")
        if isinstance(prepared_data, dict):
            current_app.logger.debug(f"[/insert_dynamic] Keys in prepared_data BEFORE service call: {list(prepared_data.keys())}")
            # Specifically log the snapshot_id it should contain
            current_app.logger.debug(f"[/insert_dynamic] snapshot_id in prepared_data BEFORE service call: {prepared_data.get('snapshot_id')}")
        else:
             current_app.logger.error("[/insert_dynamic] prepared_data is NOT a dict before service call!")
        # --- End Detailed Logging ---


        current_app.logger.info(f"Calling insert_dynamic_locations for vehicle {target_vehicle_index} with {len(new_location_pairs)} pairs, inserting after index {insertion_point_index}.")

        # Call the service function that performs the comparison and insertion
        updated_solution = VRPTestScenarioService.insert_dynamic_locations(
            current_solution=current_solution,
            prepared_data=prepared_data, # Pass the newly prepared data
            new_location_pairs=new_location_pairs,
            target_vehicle_index=target_vehicle_index,
            insertion_point_index=insertion_point_index,
            algorithm=algorithm # Pass the original algorithm choice
        )

        # Check if the service function returned an error
        if updated_solution.get('status') == 'error':
            current_app.logger.error(f"Error during dynamic insertion service call: {updated_solution.get('message')}")
            # Return the error message from the service, potentially with a specific status code if available
            return jsonify(updated_solution), 500 # Or 200 if the service handles user errors gracefully

        # --- Save Updated Solution as New History Entry ---
        # Prepare test_info for saving the updated result
        original_test_info = current_solution.get('test_info', {})
        # Merge existing info with update-specific details
        updated_solution['test_info'] = {
            **original_test_info, # Copy original info
            'test_type': 'dynamic_updated', # Mark the type as updated
            'timestamp': datetime.now().isoformat(), # Update timestamp
            'parent_test_id': current_solution.get('id'), # Link to the original test ID
            'dynamic_locations_count': len(new_location_pairs),
            'insertion_vehicle': target_vehicle_index,
            'insertion_point': insertion_point_index,
            # Add info about the chosen strategy from the service result
            'dynamic_insertion_strategy': updated_solution.get('test_info', {}).get('dynamic_insertion_strategy'),
            'strategy_A_distance': updated_solution.get('test_info', {}).get('strategy_A_distance'),
            'strategy_B_distance': updated_solution.get('test_info', {}).get('strategy_B_distance'),
            # Ensure algorithm reflects what was used for comparison if needed
            'algorithm': algorithm
        }
        # Remove original 'id' if present before saving as new entry
        if 'id' in updated_solution:
             del updated_solution['id']

        # Save the result to vrp_tests.db
        try:
            # Ensure the solution is serializable before saving
            serializable_solution = json.loads(json.dumps(updated_solution, cls=NumpyEncoder))
            # Use the correct service to save to vrp_tests.db
            new_test_id = VRPTestingService.save_test_result(serializable_solution)
            updated_solution['id'] = new_test_id # Add the new ID to the returned solution
            updated_solution['test_info']['test_id'] = new_test_id # Also add to test_info
            current_app.logger.info(f"Dynamic update saved as new test history entry with ID: {new_test_id}")
        except Exception as save_err:
            current_app.logger.error(f"Failed to save dynamic update to test history: {save_err}", exc_info=True)
            # Decide if this should be a fatal error or just a warning
            # For now, log it and continue returning the result without the new ID if saving failed

        # --- End Save ---

        current_app.logger.info("Dynamic insertion successful.")
        return jsonify({
            'status': 'success',
            'updated_solution': json.loads(json.dumps(updated_solution, cls=NumpyEncoder))
        })

    except ValueError as ve:
         # Handle potential errors from int() conversion or other value issues
         current_app.logger.error(f"Value error during dynamic insertion: {ve}", exc_info=True)
         return jsonify({'status': 'error', 'message': f"Invalid input data: {str(ve)}"}), 400
    except Exception as e:
        # Catch any other unexpected errors
        current_app.logger.error(f"Unexpected error during dynamic insertion: {e}", exc_info=True)
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': f"Error inserting dynamic locations: {str(e)}"}), 500

@vrp_testing_bp.route('/test_history', methods=['GET'])
def get_test_history():
    """Get test history from the database"""
    tests = VRPTestingService.get_test_history()

    return jsonify({
        'status': 'success',
        'tests': tests
    })

@vrp_testing_bp.route('/test_result/<int:test_id>', methods=['GET'])
def get_test_result(test_id):
    """Get a specific test result"""
    result = VRPTestingService.get_test_result(test_id)

    if not result:
        return jsonify({
            'status': 'error',
            'message': 'Test result not found'
        })

    return jsonify({
        'status': 'success',
        'result': result
    })

@vrp_testing_bp.route('/compare_results', methods=['POST'])
def compare_results():
    """Compare multiple test results"""
    data = request.json

    if not data or not data.get('test_ids'):
        return jsonify({
            'status': 'error',
            'message': 'Missing test IDs'
        })

    comparison = VRPTestingService.compare_test_results(data['test_ids'])

    if not comparison:
        return jsonify({
            'status': 'error',
            'message': 'No valid test results found'
        })

    return jsonify({
        'status': 'success',
        'comparison': comparison
    })

@vrp_testing_bp.route('/delete_test', methods=['POST'])
def delete_test():
    """Delete a test from the history"""
    data = request.json

    if not data or not data.get('test_id'):
        return jsonify({
            'status': 'error',
            'message': 'Missing test ID'
        })

    test_id = data['test_id']

    try:
        success = VRPTestingService.delete_test(test_id)

        if success:
            return jsonify({
                'status': 'success',
                'message': 'Test deleted successfully'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Error deleting test'
            })
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': f"Error: {str(e)}"
        })

@vrp_testing_bp.route('/manage_cache', methods=['POST'])
def manage_cache():
    """Manage the application cache"""
    data = request.json
    action = data.get('action')

    if action == 'clear':
        cache_type = data.get('cache_type')
        older_than = data.get('older_than')

        cleared_count = CacheService.clear_cache(cache_type, older_than)

        return jsonify({
            'status': 'success',
            'message': f'Cleared {cleared_count} cache entries',
            'cleared_count': cleared_count
        })

    elif action == 'stats':
        conn = CacheService.get_db_connection()
        cursor = conn.cursor()

        stats = {}

        try:
            cursor.execute("SELECT COUNT(*) as count FROM route_cache")
            stats['route_cache_count'] = cursor.fetchone()['count']

            cursor.execute("SELECT COUNT(*) as count FROM cluster_cache")
            stats['cluster_cache_count'] = cursor.fetchone()['count']

            cursor.execute("SELECT COUNT(*) as count FROM function_cache")
            stats['function_cache_count'] = cursor.fetchone()['count']

            cursor.execute("SELECT SUM(length(route_data)) as size FROM route_cache")
            stats['route_cache_size'] = cursor.fetchone()['size'] or 0

            cursor.execute("SELECT SUM(length(cluster_data)) as size FROM cluster_cache")
            stats['cluster_cache_size'] = cursor.fetchone()['size'] or 0

            return jsonify({
                'status': 'success',
                'stats': stats
            })
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': f"Error getting cache stats: {str(e)}"
            })
        finally:
            conn.close()

    else:
        return jsonify({
            'status': 'error',
            'message': 'Unknown action'
        })