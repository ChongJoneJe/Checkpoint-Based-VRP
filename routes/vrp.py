from flask import request, jsonify
from routes import vrp_bp
from services.vrp_service import VRPService
from services.preset_service import PresetService
from algorithms.vrp import VehicleRoutingProblem

@vrp_bp.route('/solve', methods=['POST'])
def solve_vrp():
    """Solve a vehicle routing problem"""
    data = request.json
    
    if not data.get('preset_id') or not data.get('num_vehicles'):
        return jsonify({"status": "error", "message": "Missing required parameters"})
    
    try:
        # Get preset locations
        preset_data = PresetService.get_preset_by_id(data['preset_id'])
        
        if not preset_data:
            return jsonify({"status": "error", "message": "Preset not found"})
        
        if not preset_data['warehouse'] or not preset_data['destinations']:
            return jsonify({"status": "error", "message": "Preset missing warehouse or destinations"})
        
        # Solve VRP
        algorithm = data.get('algorithm', 'nearest_neighbor')
        num_vehicles = int(data['num_vehicles'])
        
        if num_vehicles < 1:
            return jsonify({"status": "error", "message": "Number of vehicles must be at least 1"})
        
        # Check if checkpoint optimization was requested
        use_checkpoints = data.get('use_checkpoints', False)
        
        # Choose the appropriate solver
        if use_checkpoints:
            solution = VRPService.solve_vrp_with_checkpoints(
                warehouse=preset_data['warehouse'],
                destinations=preset_data['destinations'],
                num_vehicles=num_vehicles
            )
        else:
            solution = VRPService.solve_vrp(
                warehouse=preset_data['warehouse'],
                destinations=preset_data['destinations'],
                num_vehicles=num_vehicles,
                algorithm=algorithm
            )
        
        return jsonify({
            "status": "success",
            "solution": solution
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": f"Error solving VRP: {str(e)}"
        })
    
@vrp_bp.route('/solve_multi', methods=['POST'])
def solve_vrp_multi():
    """Solve a vehicle routing problem with multiple entry/exit checkpoints"""
    data = request.json
    
    if not data.get('preset_id') or not data.get('num_vehicles'):
        return jsonify({"status": "error", "message": "Missing required parameters"})
    
    try:
        # Get preset locations
        preset_data = PresetService.get_preset_by_id(data['preset_id'])
        
        if not preset_data:
            return jsonify({"status": "error", "message": "Preset not found"})
        
        if not preset_data['warehouse'] or not preset_data['destinations']:
            return jsonify({"status": "error", "message": "Preset missing warehouse or destinations"})
        
        # Solve VRP with enhanced algorithm
        num_vehicles = int(data['num_vehicles'])
        snapshot_path = data.get('snapshot_path')
        
        if num_vehicles < 1:
            return jsonify({"status": "error", "message": "Number of vehicles must be at least 1"})
        
        solution = VRPService.solve_vrp_with_multi_checkpoints(
            warehouse=preset_data['warehouse'],
            destinations=preset_data['destinations'],
            num_vehicles=num_vehicles,
            snapshot_path=snapshot_path
        )
        
        return jsonify({
            "status": "success",
            "solution": solution
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": f"Error solving VRP: {str(e)}"
        })