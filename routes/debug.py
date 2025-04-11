from flask import Blueprint, request, jsonify, render_template, current_app
import traceback
from utils.database import execute_read, execute_write
import io
from contextlib import redirect_stdout

debug_bp = Blueprint('debug', __name__, url_prefix='/debug')

@debug_bp.route('/clustering', methods=['GET', 'POST'])
def debug_clustering():
    """Debug endpoint for analyzing clustering patterns"""
    # Get optional location_id parameter
    location_id = request.args.get('location_id', None)
    
    try:
        # Get DBSCAN instance
        geocoder = current_app.config.get('geocoder')
        if not geocoder:
            return jsonify({
                "status": "error",
                "message": "Geocoder not available in application context"
            })
        
        # If POST request, get location_id from form
        if request.method == 'POST':
            location_id = request.form.get('location_id')
            
        # Convert to int if provided
        if location_id:
            try:
                location_id = int(location_id)
            except ValueError:
                return jsonify({
                    "status": "error",
                    "message": "Invalid location_id, must be an integer"
                })
        
        # Capture debug output to a string
        output = io.StringIO()
        with redirect_stdout(output):
            geocoder.debug_clustering(location_id)
        
        debug_output = output.getvalue()
        
        # If this is an AJAX request, return JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                "status": "success",
                "debug_output": debug_output
            })
        
        # Otherwise, render a template with the debug form
        return render_template('debug_clustering.html', 
                               debug_output=debug_output, 
                               location_id=location_id)
                               
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": f"Error during clustering debug: {str(e)}"
        })

@debug_bp.route('/search_locations', methods=['GET'])
def search_locations():
    """Search locations by street name or other attributes"""
    query = request.args.get('query', '').strip()
    
    if not query or len(query) < 3:
        return jsonify({
            "status": "error",
            "message": "Search query must be at least 3 characters"
        })
    
    try:
        # Search for locations matching the query
        search_term = f"%{query}%"
        locations = execute_read(
            """
            SELECT id, lat, lon, street, neighborhood, development, city
            FROM locations
            WHERE street LIKE ? OR neighborhood LIKE ? OR development LIKE ?
            ORDER BY id DESC
            LIMIT 20
            """,
            (search_term, search_term, search_term)
        )
        
        return jsonify({
            "status": "success",
            "locations": locations
        })
    
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": f"Error searching locations: {str(e)}"
        })
    
@debug_bp.route('/reassign_clusters', methods=['GET', 'POST'])
def reassign_clusters():
    """Force reclustering of all locations"""
    try:
        if request.method == 'POST':
            # Get DBSCAN instance
            geocoder = current_app.config.get('geocoder')
            if not geocoder:
                return jsonify({
                    "status": "error",
                    "message": "Geocoder not available in application context"
                })
                
            # Perform reassignment
            count = geocoder.reassign_all_clusters()
            
            return jsonify({
                "status": "success",
                "message": f"Successfully reassigned {count} locations to clusters"
            })
        else:
            # Show confirmation page
            return render_template('confirm_reassign.html')
                            
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": f"Error reassigning clusters: {str(e)}"
        })
    
