from flask import render_template, request, jsonify, Blueprint, current_app, flash, redirect, url_for
from utils.database import execute_read, execute_write
import os
import traceback

checkpoints_bp = Blueprint('checkpoints', __name__)

@checkpoints_bp.route('/cluster/<int:cluster_id>/checkpoints', methods=['GET'])
def view_cluster_checkpoints(cluster_id):
    """Get checkpoints for a specific cluster - returns JSON for API use"""
    try:
        # Get checkpoints for this cluster
        checkpoints = execute_read(
            """SELECT id, lat, lon, from_road_type, to_road_type, confidence 
            FROM security_checkpoints WHERE cluster_id = ?""",
            (cluster_id,)
        )
        
        # Get cluster info
        cluster = execute_read(
            "SELECT id, name, centroid_lat, centroid_lon FROM clusters WHERE id = ?",
            (cluster_id,),
            one=True
        )
        
        formatted_checkpoints = []
        for cp in checkpoints:
            formatted_checkpoints.append({
                'id': cp['id'],
                'lat': cp['lat'],
                'lon': cp['lon'],
                'from_type': cp['from_road_type'] if 'from_road_type' in cp else '',
                'to_type': cp['to_road_type'] if 'to_road_type' in cp else '',
                'confidence': cp['confidence'] if 'confidence' in cp else 0.7
            })
        
        return jsonify({
            'status': 'success',
            'checkpoints': formatted_checkpoints,
            'cluster': dict(cluster) if cluster else {}  
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error getting checkpoints: {str(e)}")
        
        # Return JSON error response
        return jsonify({
            'status': 'error',
            'message': f'Error retrieving checkpoints: {str(e)}'
        }), 500

@checkpoints_bp.route('/checkpoint/add', methods=['POST'])
def add_checkpoint():
    """Add a new checkpoint manually"""
    cluster_id = request.form.get('cluster_id', type=int)
    lat = request.form.get('lat', type=float)
    lon = request.form.get('lon', type=float)
    from_type = request.form.get('from_type', 'manual')
    to_type = request.form.get('to_type', 'manual')
    confidence = 1.0 
    
    if not cluster_id or not lat or not lon:
        flash("Missing required information", "error")
        return redirect(url_for('checkpoints.view_cluster_checkpoints', cluster_id=cluster_id))
    
    # Add the checkpoint
    checkpoint_id = execute_write(
        """INSERT INTO security_checkpoints 
        (cluster_id, lat, lon, from_road_type, to_road_type, confidence)
        VALUES (?, ?, ?, ?, ?, ?)""",
        (cluster_id, lat, lon, from_type, to_type, confidence)
    )
    
    flash("Checkpoint added successfully", "success")
    return redirect(url_for('checkpoints.view_cluster_checkpoints', cluster_id=cluster_id))

@checkpoints_bp.route('/checkpoint/<int:checkpoint_id>/delete', methods=['POST'])
def delete_checkpoint_html(checkpoint_id):  
    """Delete a checkpoint with HTML response"""
    # Get cluster ID for redirection
    checkpoint = execute_read(
        "SELECT cluster_id FROM security_checkpoints WHERE id = ?",
        (checkpoint_id,),
        one=True
    )
    
    if not checkpoint:
        flash("Checkpoint not found", "error")
        return redirect(url_for('clustering.view_clusters'))
    
    cluster_id = checkpoint['cluster_id']
    
    # Delete the checkpoint
    execute_write(
        "DELETE FROM security_checkpoints WHERE id = ?",
        (checkpoint_id,)
    )
    
    flash("Checkpoint deleted successfully", "success")
    return redirect(url_for('checkpoints.view_cluster_checkpoints', cluster_id=cluster_id))

@checkpoints_bp.route('/checkpoint/<int:checkpoint_id>/update', methods=['POST'])
def update_checkpoint(checkpoint_id):
    """Update a checkpoint's position"""
    lat = request.form.get('lat', type=float)
    lon = request.form.get('lon', type=float)
    
    # Get cluster ID for redirection
    checkpoint = execute_read(
        "SELECT cluster_id FROM security_checkpoints WHERE id = ?",
        (checkpoint_id,),
        one=True
    )
    
    if not checkpoint:
        flash("Checkpoint not found", "error")
        return redirect(url_for('clustering.view_clusters'))
    
    cluster_id = checkpoint['cluster_id']
    
    # Update the checkpoint
    execute_write(
        "UPDATE security_checkpoints SET lat = ?, lon = ? WHERE id = ?",
        (lat, lon, checkpoint_id)
    )
    
    flash("Checkpoint updated successfully", "success")
    return redirect(url_for('checkpoints.view_cluster_checkpoints', cluster_id=cluster_id))

@checkpoints_bp.route('/checkpoint/save_checkpoints/<int:cluster_id>', methods=['POST'])
def save_checkpoints_api(cluster_id):
    """API endpoint to save updated checkpoint positions for a cluster"""
    try:
        data = request.json
        if not data or 'checkpoints' not in data:
            return jsonify({
                'status': 'error',
                'message': 'No checkpoint data provided'
            })
        
        checkpoints = data['checkpoints']
        
        # Update each checkpoint in the database
        for checkpoint in checkpoints:
            if 'id' not in checkpoint or 'lat' not in checkpoint or 'lon' not in checkpoint:
                continue
            
            # Check if it's a temporary ID (for new checkpoints)
            is_new = isinstance(checkpoint['id'], str) and checkpoint['id'].startswith('temp-')
            
            if is_new:
                # Insert new checkpoint
                execute_write(
                    """INSERT INTO security_checkpoints 
                    (cluster_id, lat, lon, from_road_type, to_road_type, confidence)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        cluster_id,
                        checkpoint['lat'],
                        checkpoint['lon'],
                        checkpoint.get('from_type', 'unclassified'),
                        checkpoint.get('to_type', 'residential'),
                        checkpoint.get('confidence', 0.7)
                    )
                )
            else:
                # Update existing checkpoint
                execute_write(
                    """UPDATE security_checkpoints 
                    SET lat = ?, lon = ?, from_road_type = ?, to_road_type = ?
                    WHERE id = ?""",
                    (
                        checkpoint['lat'],
                        checkpoint['lon'],
                        checkpoint.get('from_type', 'unclassified'),
                        checkpoint.get('to_type', 'residential'),
                        checkpoint['id']
                    )
                )
        
        return jsonify({
            'status': 'success',
            'message': f'Saved {len(checkpoints)} checkpoints for cluster {cluster_id}'
        })
        
    except Exception as e:
        print(f"Error saving checkpoints: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error saving checkpoints: {str(e)}'
        })

@checkpoints_bp.route('/checkpoint/delete_checkpoint/<int:checkpoint_id>', methods=['POST'])
def delete_checkpoint_api(checkpoint_id):
    """API endpoint to delete a specific checkpoint with JSON response"""
    try:
        # Delete the checkpoint from the database
        execute_write(
            "DELETE FROM security_checkpoints WHERE id = ?",
            (checkpoint_id,)
        )
        
        return jsonify({
            'status': 'success',
            'message': f'Checkpoint {checkpoint_id} deleted successfully'
        })
        
    except Exception as e:
        print(f"Error deleting checkpoint: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error deleting checkpoint: {str(e)}'
        })

@checkpoints_bp.route('/checkpoints/<int:cluster_id>', methods=['GET'])
def get_checkpoints_for_cluster(cluster_id):
    """API endpoint to get checkpoints for a specific cluster (alternate URL)"""
    try:
        # Get checkpoints for this cluster
        checkpoints = execute_read(
            """SELECT id, lat, lon, from_road_type as from_type, to_road_type as to_type, confidence 
            FROM security_checkpoints WHERE cluster_id = ?""",
            (cluster_id,)
        )
        
        # Get cluster info
        cluster = execute_read(
            "SELECT id, name, centroid_lat, centroid_lon FROM clusters WHERE id = ?",
            (cluster_id,),
            one=True
        )
        
        # Format data for response
        formatted_checkpoints = []
        for cp in checkpoints:
            formatted_checkpoints.append({
                'id': cp['id'],
                'lat': cp['lat'],
                'lon': cp['lon'],
                'from_type': cp.get('from_type', ''),
                'to_type': cp.get('to_type', ''),
                'confidence': cp.get('confidence', 0.7)
            })
        
        return jsonify({
            'status': 'success',
            'checkpoints': formatted_checkpoints,
            'cluster': cluster
        })
        
    except Exception as e:
        print(f"Error getting checkpoints: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error retrieving checkpoints: {str(e)}'
        })

@checkpoints_bp.route('/cluster/<int:cluster_id>/generate', methods=['POST'])
def generate_cluster_checkpoints(cluster_id):
    """API endpoint to generate security checkpoints for a cluster"""
    try:
        from algorithms.dbscan import GeoDBSCAN
        dbscan = GeoDBSCAN()

        checkpoints = dbscan.identify_cluster_access_points(cluster_id, regenerate=True)
        
        return jsonify({
            'status': 'success',
            'checkpoints': checkpoints,
            'message': f'Generated {len(checkpoints)} checkpoints'
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error generating checkpoints: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error generating checkpoints: {str(e)}'
        })

@checkpoints_bp.route('/cluster/<int:cluster_id>/save', methods=['POST'])
def api_save_checkpoints(cluster_id):
    """API endpoint to save updated checkpoint positions for a cluster"""
    try:
        data = request.json
        if not data or 'checkpoints' not in data:
            return jsonify({
                'status': 'error',
                'message': 'No checkpoint data provided'
            })
        
        checkpoints = data['checkpoints']
        updated_count = 0
        new_count = 0
        
        # Update each checkpoint in the database
        for checkpoint in checkpoints:
            if 'id' not in checkpoint or 'lat' not in checkpoint or 'lon' not in checkpoint:
                continue
            
            # Check if it's a temporary ID (for new checkpoints)
            is_new = isinstance(checkpoint['id'], str) and checkpoint['id'].startswith('temp-')
            
            if is_new:
                # Insert new checkpoint
                execute_write(
                    """INSERT INTO security_checkpoints 
                    (cluster_id, lat, lon, from_road_type, to_road_type, confidence)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        cluster_id,
                        checkpoint['lat'],
                        checkpoint['lon'],
                        checkpoint.get('from_type', 'unclassified'),
                        checkpoint.get('to_type', 'residential'),
                        checkpoint.get('confidence', 0.7)
                    )
                )
                new_count += 1
            else:
                # Update existing checkpoint
                execute_write(
                    """UPDATE security_checkpoints 
                    SET lat = ?, lon = ?, from_road_type = ?, to_road_type = ?
                    WHERE id = ?""",
                    (
                        checkpoint['lat'],
                        checkpoint['lon'],
                        checkpoint.get('from_type', 'unclassified'),
                        checkpoint.get('to_type', 'residential'),
                        checkpoint['id']
                    )
                )
                updated_count += 1
        
        return jsonify({
            'status': 'success',
            'message': f'Saved {updated_count} updated and {new_count} new checkpoints for cluster {cluster_id}'
        })
        
    except Exception as e:
        print(f"Error saving checkpoints: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error saving checkpoints: {str(e)}'
        })

@checkpoints_bp.route('/<int:checkpoint_id>/delete', methods=['POST'])
def api_delete_checkpoint(checkpoint_id):
    """API endpoint to delete a specific checkpoint"""
    try:
        # Delete the checkpoint from the database
        execute_write(
            "DELETE FROM security_checkpoints WHERE id = ?",
            (checkpoint_id,)
        )
        
        return jsonify({
            'status': 'success',
            'message': f'Checkpoint {checkpoint_id} deleted successfully'
        })
        
    except Exception as e:
        print(f"Error deleting checkpoint: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error deleting checkpoint: {str(e)}'
        })