from flask import request, jsonify
import os
import numpy as np
from routes import clustering_bp
from algorithms.dbscan import GeoDBSCAN

@clustering_bp.route('/run_clustering', methods=['POST'])
def run_clustering():
    """Run DBSCAN clustering on a set of locations"""
    data = request.json
    
    if not data.get('locations') or len(data.get('locations', [])) < 2:
        return jsonify({"status": "error", "message": "Need at least 2 locations for clustering"})
    
    try:
        # Get parameters
        locations = data['locations']
        eps = data.get('eps', 0.5)  # Default to 0.5 km
        min_samples = data.get('min_samples', 2)  # Default to minimum 2 points per cluster
        
        # Initialize and run the clustering algorithm
        api_key = os.environ.get('ORS_API_KEY', 'your_api_key_here')
        clusterer = GeoDBSCAN(eps=eps, min_samples=min_samples, api_key=api_key)
        clusterer.fit(np.array(locations))
        
        # Prepare result
        result = {
            'labels': clusterer.labels_.tolist(),
            'intersections': []
        }
        
        # Add intersection points if available
        for node_id, coords in clusterer.intersection_points.items():
            result["intersections"].append({
                "id": str(node_id),
                "coords": coords
            })
        
        return jsonify({
            "status": "success", 
            "result": result
        })
    except Exception as e:
        return jsonify({
            "status": "error", 
            "message": f"Clustering error: {str(e)}"
        })