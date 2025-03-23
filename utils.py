import os
import json

# Path to the presets file
PRESETS_FILE = 'static/data/presets.json'

def load_presets():
    """Load presets from file"""
    if os.path.exists(PRESETS_FILE):
        with open(PRESETS_FILE, 'r') as f:
            return json.load(f)
    return {"presets": []}

def save_presets_to_file(presets_data):
    """Save presets to file"""
    os.makedirs(os.path.dirname(PRESETS_FILE), exist_ok=True)
    with open(PRESETS_FILE, 'w') as f:
        json.dump(presets_data, f, indent=2)