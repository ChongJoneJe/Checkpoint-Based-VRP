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
        snapshot_path = os.path.join(current_app.root_path, "vrp_test_data", snapshot_id)
        
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

    snapshot_id = data['snapshot_id']
    preset_id = data['preset_id']
    algorithm = data.get('algorithm', 'two_opt')  # Default to NN+2Opt
    num_vehicles = int(data.get('num_vehicles', 1))  # Ensure num_vehicles is extracted correctly
    test_type = data.get('test_type', 'static')
    api_key = data.get('api_key') or current_app.config.get('ORS_API_KEY')

    try:
        snapshot_path = os.path.join(current_app.root_path, "vrp_test_data", snapshot_id)
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

            # Add api_key to prepared_data if not already present
            prepared_data['api_key'] = api_key

            print(f"[DEBUG Route] Calling VRPTestScenarioService.run_checkpoint_vrp_scenario. Algorithm: {algorithm}, Vehicles: {num_vehicles}")
            solution = VRPTestScenarioService.run_checkpoint_vrp_scenario(
                prepared_data,
                num_vehicles=num_vehicles,  # Pass num_vehicles
                algorithm=algorithm  # Pass 'two_opt' or 'or_tools'
            )

        else:
            return jsonify({'status': 'error', 'message': f'Invalid test type: {test_type}'})

        solution['test_info'] = {
            'snapshot_id': snapshot_id,
            'preset_id': preset_id,
            'algorithm': algorithm,  # Store the algorithm requested by the user
            'num_vehicles': num_vehicles,  # Store the requested number
            'test_type': test_type,
            'timestamp': datetime.now().isoformat(),
            'distance_type': solution.get('distance_type', 'unknown'),
            'algorithm_used': solution.get('algorithm_used', algorithm)  # Add algorithm actually used by the solver for clarity
        }

        test_id = VRPTestingService.save_test_result(solution)
        solution['id'] = test_id

        return jsonify({
            'status': 'success',
            'solution': json.loads(json.dumps(solution, cls=NumpyEncoder))
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
        snapshot_id = data['snapshot_id']
        preset_id = data['preset_id']

        api_key = current_app.config.get('ORS_API_KEY')
        geo_dbscan = GeoDBSCAN(api_key=api_key)

        # Get preset data for warehouse coordinates
        warehouse_lat = data.get('warehouse_lat')
        warehouse_lon = data.get('warehouse_lon')

        # Process Pickup Location - first just geocode it
        print(f"[DEBUG /process_dynamic_pair] Processing Pickup: ({pickup_lat}, {pickup_lon})")
        pickup_address = geo_dbscan.geocode_location(pickup_lat, pickup_lon)
        
        # Process Dropoff Location - first just geocode it
        print(f"[DEBUG /process_dynamic_pair] Processing Dropoff: ({dropoff_lat}, {dropoff_lon})")
        dropoff_address = geo_dbscan.geocode_location(dropoff_lat, dropoff_lon)
        
        # Now work with the snapshot DB for clustering
        # FIXED: Use the correct path to the snapshot database - the .sqlite file itself
        # FIX 1: If snapshot_id already includes .sqlite extension
        if not snapshot_id.endswith('.sqlite'):
            snapshot_id = f"{snapshot_id}.sqlite"
            
        snapshot_path = os.path.join(current_app.root_path, "vrp_test_data", snapshot_id)
        
        # FIX 2: The snapshot file itself is the database, don't append 'snapshot.db'
        db_path = snapshot_path  # Use the .sqlite file directly
        
        print(f"[DEBUG /process_dynamic_pair] Using database path: {db_path}")
        
        if not os.path.exists(db_path):
            return jsonify({
                'status': 'error', 
                'message': f'Snapshot database not found at {db_path}'
            })
        
        # Connect to the snapshot database
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        # Process pickup clustering using snapshot DB
        pickup_loc_id, pickup_cluster_id = process_location_in_snapshot(
            conn, pickup_lat, pickup_lon, pickup_address, geo_dbscan
        )
        
        # Process dropoff clustering using snapshot DB
        dropoff_loc_id, dropoff_cluster_id = process_location_in_snapshot(
            conn, dropoff_lat, dropoff_lon, dropoff_address, geo_dbscan
        )
        
        # Get checkpoints for pickup cluster
        pickup_checkpoints = []
        if pickup_cluster_id:
            pickup_checkpoints = conn.execute(
                "SELECT id, lat, lon FROM security_checkpoints WHERE cluster_id = ?",
                (pickup_cluster_id,)
            ).fetchall()
            pickup_checkpoints = [dict(cp) for cp in pickup_checkpoints] or []
        
        # Get checkpoints for dropoff cluster
        dropoff_checkpoints = []
        if dropoff_cluster_id:
            dropoff_checkpoints = conn.execute(
                "SELECT id, lat, lon FROM security_checkpoints WHERE cluster_id = ?",
                (dropoff_cluster_id,)
            ).fetchall()
            dropoff_checkpoints = [dict(cp) for cp in dropoff_checkpoints] or []
        
        conn.close()

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

def process_location_in_snapshot(conn, lat, lon, address, geo_dbscan):
    """Process a location for clustering using the snapshot database."""
    cursor = conn.cursor()
    
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
    
    # Try to find a good cluster match
    # First, try exact street match
    cursor.execute(
        """
        SELECT lc.cluster_id
        FROM locations l
        JOIN location_clusters lc ON l.id = lc.location_id
        WHERE LOWER(l.street) = LOWER(?) AND l.street != ''
        LIMIT 1
        """,
        (address.get('street', ''),)
    )
    cluster_match = cursor.fetchone()
    
    if cluster_match:
        # Use existing cluster
        cluster_id = cluster_match['cluster_id']
        
        # Assign to this cluster
        cursor.execute(
            "INSERT OR REPLACE INTO location_clusters (location_id, cluster_id) VALUES (?, ?)",
            (location_id, cluster_id)
        )
    else:
        # Try to determine cluster using pattern matching (simplified)
        # In a real implementation, we would use more sophisticated cluster matching
        
        # For now, just try to find nearby locations and use their cluster
        cursor.execute(
            """
            SELECT l.id, l.lat, l.lon, lc.cluster_id
            FROM locations l
            JOIN location_clusters lc ON l.id = lc.location_id
            ORDER BY ((l.lat - ?)*(l.lat - ?) + (l.lon - ?)*(l.lon - ?)) ASC
            LIMIT 1
            """,
            (lat, lat, lon, lon)
        )
        nearest = cursor.fetchone()
        
        if nearest:
            cluster_id = nearest['cluster_id']
            
            # Assign to nearest cluster
            cursor.execute(
                "INSERT OR REPLACE INTO location_clusters (location_id, cluster_id) VALUES (?, ?)",
                (location_id, cluster_id)
            )
        else:
            # No suitable cluster found
            cluster_id = None
    
    conn.commit()
    return location_id, cluster_id

@vrp_testing_bp.route('/insert_dynamic', methods=['POST'])
def insert_dynamic():
    """Recalculates a route after inserting new dynamic location pairs."""
    data = request.json
    required_fields = ['current_solution', 'prepared_data_ref', 'new_location_pairs', 'target_vehicle_index', 'insertion_point_index', 'algorithm'] # Ensure algorithm is required too if needed downstream

    # Check for missing fields
    missing = [field for field in required_fields if field not in (data or {})]

    if not data or missing:
        error_msg = f"Missing required parameters for dynamic insertion. Missing: {missing}. Received keys: {list(data.keys()) if data else 'None'}"
        current_app.logger.error(error_msg)
        # Return 400 Bad Request for missing parameters
        return jsonify({'status': 'error', 'message': error_msg}), 400
    
    try:
        current_solution = data['current_solution']
        prepared_data_ref = data['prepared_data_ref'] # Contains snapshot_id, preset_id, api_key
        new_location_pairs = data['new_location_pairs'] # The array from JS
        target_vehicle_index = int(data['target_vehicle_index'])
        insertion_point_index = int(data['insertion_point_index']) # Get insertion point index
        algorithm = data.get('algorithm', 'or_tools') # Get algorithm from request if provided

        # Validate pairs structure minimally
        if not isinstance(new_location_pairs, list) or not all('pickup' in p and 'dropoff' in p for p in new_location_pairs):
             return jsonify({'status': 'error', 'message': 'Invalid format for new_location_pairs.'})

        # Re-prepare data using the references. This ensures the distance matrix etc. are available.
        # Pass the API key from the reference object.
        api_key = prepared_data_ref.get('api_key') or current_app.config.get('ORS_API_KEY')
        
        # FIXED: Ensure the database path is correct for prepare_test_data
        snapshot_id = prepared_data_ref['snapshot_id']
        # Ensure snapshot_id has .sqlite extension
        if not snapshot_id.endswith('.sqlite'):
            snapshot_id = f"{snapshot_id}.sqlite"
            
        prepared_data = VRPTestScenarioService.prepare_test_data(
            snapshot_id,
            prepared_data_ref['preset_id'],
            api_key=api_key
        )

        # Check if prepare_test_data returned an error structure
        if not prepared_data or prepared_data.get('status') == 'error':
            error_msg = prepared_data.get('message', 'Failed to re-prepare test data for insertion') if prepared_data else 'Failed to re-prepare test data for insertion'
            current_app.logger.error(f"Error re-preparing data for dynamic insertion: {error_msg}")
            return jsonify({'status': 'error', 'message': error_msg})

        # Add api_key and db_path to prepared_data if needed by the insertion service
        prepared_data['api_key'] = api_key
        snapshot_path = os.path.join(current_app.root_path, "vrp_test_data", snapshot_id)
        prepared_data['db_path'] = snapshot_path  # Use the .sqlite file directly

        current_app.logger.info(f"Calling insert_dynamic_locations for vehicle {target_vehicle_index} with {len(new_location_pairs)} pairs, inserting after index {insertion_point_index}.")

        # Call the correct service method with the correct arguments
        updated_solution = VRPTestScenarioService.insert_dynamic_locations(
            current_solution=current_solution,
            prepared_data=prepared_data,
            new_location_pairs=new_location_pairs,
            target_vehicle_index=target_vehicle_index,
            insertion_point_index=insertion_point_index, # Pass index to service
            algorithm=algorithm
        )

        if updated_solution.get('status') == 'error':
            current_app.logger.error(f"Error during dynamic insertion service call: {updated_solution.get('message')}")
            return jsonify(updated_solution)

        # --- Save Updated Solution as New History Entry ---
        # Prepare test_info for saving
        original_test_info = current_solution.get('test_info', {})
        updated_solution['test_info'] = {
            'snapshot_id': original_test_info.get('snapshot_id', prepared_data_ref.get('snapshot_id')),
            'preset_id': original_test_info.get('preset_id', prepared_data_ref.get('preset_id')),
            'algorithm': algorithm, # Use the algorithm used for insertion
            'num_vehicles': original_test_info.get('num_vehicles', current_solution.get('num_vehicles')),
            'test_type': 'dynamic_updated', # Mark the type
            'timestamp': datetime.now().isoformat(),
            'parent_test_id': original_test_info.get('test_id'), # Link to the original test if ID was present
            'dynamic_locations_count': len(new_location_pairs),
            'insertion_vehicle': target_vehicle_index,
            'insertion_point': insertion_point_index
        }

        # Save the result (this function needs the solution dict)
        try:
            # Ensure the solution is serializable before saving
            serializable_solution = json.loads(json.dumps(updated_solution, cls=NumpyEncoder))
            new_test_id = VRPTestingService.save_test_result(serializable_solution)
            updated_solution['id'] = new_test_id # Add the new ID to the returned solution
            updated_solution['test_info']['test_id'] = new_test_id # Also add to test_info
            current_app.logger.info(f"Dynamic update saved as new test history entry with ID: {new_test_id}")
        except Exception as save_err:
            current_app.logger.error(f"Failed to save dynamic update to test history: {save_err}", exc_info=True)
            # Decide if this should be a fatal error or just a warning
            # For now, log it and continue returning the result

        # --- End Save ---

        current_app.logger.info("Dynamic insertion successful.")
        # Return the updated solution (now including the new 'id')
        return jsonify({
            'status': 'success',
            'updated_solution': json.loads(json.dumps(updated_solution, cls=NumpyEncoder))
        })

    except ValueError as ve:
         current_app.logger.error(f"Value error during dynamic insertion: {ve}", exc_info=True)
         return jsonify({'status': 'error', 'message': f"Invalid input data: {str(ve)}"})
    except Exception as e:
        current_app.logger.error(f"Unexpected error during dynamic insertion: {e}", exc_info=True)
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': f"Error inserting dynamic locations: {str(e)}"})

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