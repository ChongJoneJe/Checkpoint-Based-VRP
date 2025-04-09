from flask import render_template, request, jsonify, Blueprint, current_app
from services.clustering_service import ClusteringService
from services.preset_service import PresetService
from utils.database import execute_read, execute_write
from algorithms.dbscan import GeoDBSCAN

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
    
@clustering_bp.route('/checkpoints/<int:cluster_id>', methods=['GET'])
def get_cluster_checkpoints(cluster_id):
    """Get checkpoints for a cluster"""
    try:
        # Get the cluster details
        cluster = execute_read(
            "SELECT id, name, centroid_lat, centroid_lon FROM clusters WHERE id = ?",
            (cluster_id,),
            one=True
        )
        
        if not cluster:
            return jsonify({"status": "error", "message": "Cluster not found"})
        
        # Get all checkpoints for this cluster
        checkpoints = execute_read(
            """SELECT id, lat, lon, from_road_type, to_road_type, confidence, source
               FROM security_checkpoints
               WHERE cluster_id = ?""",
            (cluster_id,)
        )
        
        return jsonify({
            "status": "success",
            "cluster": cluster,
            "checkpoints": checkpoints
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)})

@clustering_bp.route('/checkpoints/<int:cluster_id>', methods=['POST'])
def update_cluster_checkpoints(cluster_id):
    """Update or add checkpoints for a cluster"""
    try:
        data = request.json
        checkpoints = data.get('checkpoints', [])
        
        # Clear existing checkpoints for this cluster
        execute_write(
            "DELETE FROM security_checkpoints WHERE cluster_id = ?",
            (cluster_id,)
        )
        
        # Add the new checkpoints
        for cp in checkpoints:
            execute_write(
                """INSERT INTO security_checkpoints 
                   (cluster_id, lat, lon, from_road_type, to_road_type, confidence, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    cluster_id,
                    cp['lat'],
                    cp['lon'],
                    cp.get('from_type', 'unknown'),
                    cp.get('to_type', 'residential'),
                    cp.get('confidence', 1.0),
                    cp.get('source', 'manual')
                )
            )
        
        return jsonify({
            "status": "success",
            "message": f"Updated {len(checkpoints)} checkpoints for cluster {cluster_id}"
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)})

@clustering_bp.route('/generate_checkpoints', methods=['POST'])
def generate_checkpoints():
    """Generate security checkpoints for clusters"""
    try:
        data = request.json
        cluster_id = data.get('cluster_id')
        
        # Get geocoder with API key
        from flask import current_app
        api_key = current_app.config.get('ORS_API_KEY')
        geocoder = GeoDBSCAN(api_key=api_key)
        
        # If specific cluster_id provided, generate for just that cluster
        if cluster_id:
            # Clear existing checkpoints
            execute_write(
                "DELETE FROM security_checkpoints WHERE cluster_id = ?",
                (cluster_id,)
            )
            
            # Generate new checkpoints
            checkpoints = geocoder.identify_cluster_access_points(cluster_id)
            
            return jsonify({
                "status": "success",
                "message": f"Generated checkpoints for cluster {cluster_id}",
                "checkpoints": checkpoints
            })
        else:
            # Handle bulk generation for all clusters
            clusters = execute_read("SELECT id FROM clusters")
            
            processed = 0
            for cluster in clusters:
                cluster_id = cluster['id']
                
                # Clear existing checkpoints
                execute_write(
                    "DELETE FROM security_checkpoints WHERE cluster_id = ?",
                    (cluster_id,)
                )
                
                # Generate new checkpoints
                checkpoints = geocoder.identify_cluster_access_points(cluster_id)
                if checkpoints:
                    processed += 1
            
            return jsonify({
                "status": "success",
                "message": f"Generated checkpoints for {processed} clusters",
                "total_clusters": len(clusters)
            })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": f"Error generating checkpoints: {str(e)}"
        })

@clustering_bp.route('/cluster_details/<int:cluster_id>', methods=['GET'])
def cluster_details(cluster_id):
    """Get detailed information about a specific cluster"""
    try:
        # Get cluster information
        cluster = execute_read(
            """SELECT id, name, centroid_lat, centroid_lon 
               FROM clusters WHERE id = ?""",
            (cluster_id,),
            one=True
        )
        
        if not cluster:
            return jsonify({"status": "error", "message": "Cluster not found"})
        
        # Get locations in this cluster
        locations = execute_read(
            """SELECT l.id, l.lat, l.lon, l.street
               FROM locations l
               JOIN location_clusters lc ON l.id = lc.location_id
               WHERE lc.cluster_id = ?""",
            (cluster_id,)
        )
        
        # Get checkpoints for this cluster
        checkpoints = execute_read(
            """SELECT id, lat, lon, from_road_type, to_road_type, confidence
               FROM security_checkpoints
               WHERE cluster_id = ?""",
            (cluster_id,)
        )
        
        return jsonify({
            "status": "success",
            "cluster": cluster,
            "locations": locations,
            "checkpoints": checkpoints
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)})
