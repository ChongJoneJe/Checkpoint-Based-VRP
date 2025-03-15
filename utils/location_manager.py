import os
import json
import uuid
import numpy as np
from models.location import Location
from config import PRESETS_FILE, LOCATIONS_FILE

def ensure_data_directory():
    """Ensure data directory exists."""
    os.makedirs(os.path.dirname(PRESETS_FILE), exist_ok=True)

def load_presets():
    """Load all saved location presets."""
    ensure_data_directory()
    if os.path.exists(PRESETS_FILE):
        with open(PRESETS_FILE, 'r') as f:
            return json.load(f)
    return {"presets": []}

def save_preset(name, warehouse, destinations):
    """Save a new preset with the given locations."""
    presets_data = load_presets()
    
    # Generate unique ID
    preset_id = str(uuid.uuid4())
    
    # Create new preset
    new_preset = {
        "id": preset_id,
        "name": name,
        "warehouse": warehouse,
        "destinations": destinations,
        "created_at": str(datetime.now())
    }
    
    # Add to presets
    presets_data["presets"].append(new_preset)
    
    # Save updated presets
    with open(PRESETS_FILE, 'w') as f:
        json.dump(presets_data, f, indent=2)
    
    return preset_id

def get_preset(preset_id):
    """Get a preset by ID."""
    presets_data = load_presets()
    
    for preset in presets_data["presets"]:
        if preset["id"] == preset_id:
            return preset
    
    return None

def delete_preset(preset_id):
    """Delete a preset by ID."""
    presets_data = load_presets()
    
    # Filter out the preset to delete
    presets_data["presets"] = [p for p in presets_data["presets"] if p["id"] != preset_id]
    
    # Save updated presets
    with open(PRESETS_FILE, 'w') as f:
        json.dump(presets_data, f, indent=2)

def convert_preset_to_locations(preset):
    """Convert a preset to Location objects."""
    warehouse = Location(
        id=-1, 
        lat=preset["warehouse"][0], 
        lon=preset["warehouse"][1],
        type='warehouse',
        name='Warehouse'
    )
    
    destinations = []
    for i, dest in enumerate(preset["destinations"]):
        destinations.append(Location(
            id=i,
            lat=dest[0],
            lon=dest[1],
            type='destination',
            name=f"Destination {i+1}"
        ))
    
    return warehouse, destinations

def convert_locations_to_arrays(warehouse, destinations):
    """Convert Location objects to numpy arrays for algorithms."""
    warehouse_array = np.array([warehouse.lat, warehouse.lon])
    destinations_array = np.array([[d.lat, d.lon] for d in destinations])
    
    return warehouse_array, destinations_array