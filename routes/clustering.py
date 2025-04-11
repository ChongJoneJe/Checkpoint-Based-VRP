from flask import render_template, request, jsonify, Blueprint, current_app
from services.clustering_service import ClusteringService
from services.preset_service import PresetService
from utils.database import execute_read, execute_write
from algorithms.dbscan import GeoDBSCAN
from services.debug_service import DebugService
from services.checkpoint_service import CheckpointService

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
    try:
        presets = PresetService.get_all_presets_basic()
        return jsonify({"presets": presets, "status": "success"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"presets": [], "status": "error", "message": str(e)})

@clustering_bp.route('/debug_checkpoint/<int:cluster_id>', methods=['GET'])
def debug_checkpoint(cluster_id):
    """Debug route for testing checkpoint generation"""
    try:
        # Get geocoder instance
        geocoder = current_app.config.get('geocoder')
        if not geocoder:
            return jsonify({
                "status": "error",
                "message": "Geocoder not available"
            })
        
        # Use the service to get debug info
        result = DebugService.debug_checkpoint(cluster_id, geocoder)
        
        return jsonify({
            "status": "success",
            **result
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": f"Error in debug: {str(e)}",
            "traceback": traceback.format_exc()
        })

@clustering_bp.route('/checkpoints/<int:cluster_id>', methods=['GET'])
def get_cluster_checkpoints(cluster_id):
    """Get checkpoints for a specific cluster"""
    try:
        print(f"DEBUG: Fetching checkpoints for cluster {cluster_id}")
        result = CheckpointService.get_checkpoints(cluster_id)
        
        # Convert to JSON-serializable dict and log
        response_data = {
            "status": "success",
            **result
        }
        print(f"DEBUG: Response data: {response_data}")
        
        return jsonify(response_data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": f"Error getting checkpoints: {str(e)}"
        })

@clustering_bp.route('/generate_checkpoints/<int:cluster_id>', methods=['POST'])
def generate_cluster_checkpoints(cluster_id):
    """Generate checkpoints for a specific cluster"""
    try:
        geocoder = current_app.config.get('geocoder')
        result = CheckpointService.generate_checkpoints(cluster_id, geocoder)
        return jsonify({
            "status": "success",
            "message": f"Generated {result['count']} checkpoints",
            "checkpoints": result["checkpoints"]
        })
    except ValueError as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": f"Error generating checkpoints: {str(e)}"
        })

@clustering_bp.route('/delete_checkpoint/<int:checkpoint_id>', methods=['POST'])
def delete_checkpoint(checkpoint_id):
    """Delete a checkpoint"""
    try:
        CheckpointService.delete_checkpoint(checkpoint_id)
        return jsonify({
            "status": "success",
            "message": "Checkpoint deleted successfully"
        })
    except ValueError as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": f"Error deleting checkpoint: {str(e)}"
        })

@clustering_bp.route('/network_viz/<int:cluster_id>', methods=['GET'])
def get_network_visualization(cluster_id):
    """Check if network visualization is available for a cluster"""
    try:
        result = CheckpointService.check_visualization(cluster_id, current_app.root_path)
        return jsonify({
            "status": "success",
            **result
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        })