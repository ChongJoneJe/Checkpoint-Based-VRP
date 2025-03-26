from flask import request, jsonify
from routes import presets_bp
from services.preset_service import PresetService

@presets_bp.route('/get_presets', methods=['GET'])
def get_presets():
    """Get all available presets from the database"""
    try:
        presets_data = PresetService.get_all_presets()
        return jsonify({"presets": presets_data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@presets_bp.route('/save_preset', methods=['POST'])
def save_preset():
    """Save a preset of locations to the database"""
    data = request.json
    
    if not data.get('name') or not data.get('warehouse') or not data.get('destinations'):
        return jsonify({"status": "error", "message": "Missing required data"})
    
    try:
        preset_id = PresetService.save_preset(
            data['name'], 
            data['warehouse'], 
            data['destinations']
        )
        
        return jsonify({
            "status": "success",
            "message": "Preset saved successfully",
            "preset_id": preset_id
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@presets_bp.route('/get_preset/<preset_id>', methods=['GET'])
def get_preset(preset_id):
    """Get a specific preset by ID from the database"""
    try:
        preset_data = PresetService.get_preset_by_id(preset_id)
        
        if not preset_data:
            return jsonify({"status": "error", "message": "Preset not found"})
        
        return jsonify({
            "status": "success",
            "preset": preset_data
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@presets_bp.route('/delete_preset/<preset_id>', methods=['DELETE'])
def delete_preset(preset_id):
    """Delete a preset by ID from the database"""
    try:
        success = PresetService.delete_preset(preset_id)
        
        if not success:
            return jsonify({"status": "error", "message": "Preset not found"})
        
        return jsonify({
            "status": "success",
            "message": "Preset deleted successfully"
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

def load_presets():
    """Load all presets from the database - function for internal use by other routes"""
    try:
        return {"presets": PresetService.get_all_presets()}
    except Exception as e:
        print(f"Error loading presets: {str(e)}")
        return {"presets": []}