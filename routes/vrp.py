from flask import request, jsonify
import time
import random
from routes import vrp_bp
from routes.presets import load_presets

@vrp_bp.route('/solve_vrp', methods=['POST'])
def solve_vrp():
    """Solve the VRP based on the selected preset and algorithm"""
    data = request.json
    
    if not data.get('preset_id'):
        return jsonify({"status": "error", "message": "No preset selected"})
    
    # Get the preset data
    presets_data = load_presets()
    preset = None
    for p in presets_data["presets"]:
        if p["id"] == data['preset_id']:
            preset = p
            break
    
    if not preset:
        return jsonify({"status": "error", "message": "Preset not found"})
    
    # Get algorithm and vehicle count
    algorithm = data.get('algorithm', 'nearest_neighbor')
    vehicle_count = data.get('vehicle_count', 1)
    
    # Here you would implement or call your VRP solving algorithm
    # For now, we'll return a dummy result
    
    # Record start time
    start_time = time.time()
    
    # Dummy processing time
    time.sleep(1)
    
    # Generate dummy routes
    routes = []
    destinations = list(range(len(preset["destinations"])))
    random.shuffle(destinations)
    
    # Divide destinations between vehicles
    chunk_size = len(destinations) // vehicle_count
    if chunk_size == 0:
        chunk_size = 1
    
    for i in range(vehicle_count):
        start_idx = i * chunk_size
        end_idx = start_idx + chunk_size if i < vehicle_count - 1 else len(destinations)
        
        if start_idx >= len(destinations):
            break
            
        vehicle_stops = destinations[start_idx:end_idx]
        
        # Calculate dummy distance
        distance = random.uniform(10, 50)
        
        routes.append({
            "stops": vehicle_stops,
            "distance": distance
        })
    
    # Calculate total distance and computation time
    total_distance = sum(route["distance"] for route in routes)
    computation_time = time.time() - start_time
    
    return jsonify({
        "status": "success",
        "routes": routes,
        "total_distance": total_distance,
        "computation_time": computation_time
    })