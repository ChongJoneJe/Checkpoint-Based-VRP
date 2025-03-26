from flask import request, jsonify, Blueprint
from services.clustering_service import ClusteringService
from services.preset_service import PresetService

# Create blueprint
clustering_bp = Blueprint('clustering', __name__)

@clustering_bp.route('/get_clusters', methods=['GET'])
def get_clusters():
    """Get clusters for visualization"""
    preset_id = request.args.get('preset_id', None)
    
    try:
        # Get cluster data from service
        clusters, warehouse, stats = ClusteringService.get_clusters(preset_id)
        
        return jsonify({
            "status": "success", 
            "clusters": clusters,
            "warehouse": warehouse,
            "stats": stats
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": f"Error loading clusters: {str(e)}"
        })

@clustering_bp.route('/run_clustering', methods=['POST'])
def run_clustering():
    """Run clustering on locations"""
    data = request.json
    
    if not data.get('preset_id'):
        return jsonify({"status": "error", "message": "Missing preset_id"})
    
    try:
        # Get clustering parameters
        preset_id = data.get('preset_id')
        eps = data.get('eps', 0.5)
        min_samples = data.get('min_samples', 2)
        
        # Run clustering algorithm
        results = ClusteringService.run_clustering_for_preset(preset_id, eps, min_samples)
        
        return jsonify({
            "status": "success",
            "message": "Clustering completed successfully",
            "clusters": results
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": f"Error running clustering: {str(e)}"
        })

@clustering_bp.route('/get_presets_for_clustering', methods=['GET'])
def get_presets_for_clustering():
    """Get presets with geocoded info for clustering visualization"""
    print("Endpoint called: get_presets_for_clustering")
    try:
        # Use the simple function instead of ORM
        presets_data = PresetService.get_all_presets_basic()
        return jsonify({"presets": presets_data})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)})