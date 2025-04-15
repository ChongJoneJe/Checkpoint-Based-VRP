from flask import Blueprint, render_template, request, jsonify, current_app
from services.vrp_service import VRPService
from services.preset_service import PresetService  # Keep if used elsewhere
from services.vrp_testing_service import VRPTestingService, NumpyEncoder
from services.cache_service import CacheService
from services.test_scenario_service import VRPTestScenarioService  # Import new service
from save_db import create_database_snapshot
import os
import json
import numpy as np
import traceback
from datetime import datetime

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
    num_vehicles = int(data['num_vehicles'])
    test_type = data['test_type']
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
                num_vehicles=num_vehicles,
                algorithm=algorithm,  # Pass the selected algorithm
                api_key=api_key  # Pass API key here
            )
            solution['distance_type'] = solution.get('distance_type', 'haversine')

        elif test_type == 'checkpoints' or test_type == 'dynamic':
            # Prepare data (includes distance matrix calculation for checkpoints)
            prepared_data = VRPTestScenarioService.prepare_test_data(
                snapshot_id, preset_id, api_key=api_key
            )
            if not prepared_data or prepared_data.get('status') == 'error':
                error_msg = prepared_data.get('message', 'Failed to prepare test data') if isinstance(prepared_data, dict) else 'Failed to prepare test data'
                return jsonify({'status': 'error', 'message': error_msg})

            # Add api_key to prepared_data if not already present, for EnhancedVRP
            prepared_data['api_key'] = api_key

            print(f"[DEBUG Route] Calling VRPTestScenarioService.run_checkpoint_vrp_scenario with algorithm: {algorithm}")
            solution = VRPTestScenarioService.run_checkpoint_vrp_scenario(
                prepared_data,
                num_vehicles=num_vehicles,
                algorithm=algorithm  # Pass 'two_opt' or 'or_tools'
            )

        else:
            return jsonify({'status': 'error', 'message': f'Invalid test type: {test_type}'})

        solution['test_info'] = {
            'snapshot_id': snapshot_id,
            'preset_id': preset_id,
            'algorithm': algorithm,  # Store the algorithm requested by the user
            'num_vehicles': num_vehicles,
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

@vrp_testing_bp.route('/insert_dynamic', methods=['POST'])
def insert_dynamic():
    """Recalculates a route after inserting new dynamic locations"""
    data = request.json

    required_fields = ['current_solution', 'prepared_data_ref', 'insertion_index', 'new_locations']
    if not data or not all(field in data for field in required_fields):
        return jsonify({'status': 'error', 'message': 'Missing required parameters for dynamic insertion'})

    try:
        current_solution = data['current_solution']
        prepared_data_ref = data['prepared_data_ref']
        insertion_index = int(data['insertion_index'])
        new_locations = data['new_locations']
        num_vehicles = int(data.get('num_vehicles', 1))
        algorithm = data.get('algorithm', 'or_tools')

        prepared_data = VRPTestScenarioService.prepare_test_data(
            prepared_data_ref['snapshot_id'],
            prepared_data_ref['preset_id']
        )
        if not prepared_data:
            return jsonify({'status': 'error', 'message': 'Failed to re-prepare test data for insertion'})

        updated_solution = VRPTestScenarioService.insert_dynamic_location(
            current_solution=current_solution,
            prepared_data=prepared_data,
            insertion_index=insertion_index,
            new_locations=new_locations,
            num_vehicles=num_vehicles,
            algorithm=algorithm
        )

        if updated_solution.get('status') == 'error':
            return jsonify(updated_solution)

        updated_solution['test_info'] = current_solution.get('test_info', {})
        updated_solution['test_info']['timestamp'] = datetime.now().isoformat()
        updated_solution['test_info']['is_dynamic_update'] = True

        return jsonify({
            'status': 'success',
            'updated_solution': json.loads(json.dumps(updated_solution, cls=NumpyEncoder))
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': f"Error inserting dynamic location: {str(e)}"})

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