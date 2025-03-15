# Algorithm parameters
ALGORITHM_CONFIGS = {
    'nearest_neighbor': {
        'name': 'Nearest Neighbor',
        'description': 'Simple greedy algorithm that visits the nearest unvisited location'
    },
    'clarke_wright': {
        'name': 'Clarke-Wright Savings',
        'description': 'Creates routes by merging trips based on savings'
    },
    'two_opt': {
        'name': 'Two-Opt Improvement',
        'description': 'Improves routes by swapping edges to eliminate crossings'
    }
}

# Clustering parameters
CLUSTERING_CONFIGS = {
    'kmeans': {
        'name': 'K-Means',
        'max_clusters': 10
    }
}

# Vehicle parameters
DEFAULT_VEHICLE = {
    'capacity': 1000,  # kg
    'speed': 50,      # km/h
    'working_hours': 8,  # hours
    'cost_per_km': 0.5  # cost units
}

# Map settings
MAP_SETTINGS = {
    'default_center': [3.127993, 101.466972],  # Malaysia
    'default_zoom': 13
}

# Dynamic VRP settings
DYNAMIC_SETTINGS = {
    'time_step': 5,  # minutes per simulation step
    'new_order_probability': 0.3  # probability of new order per time step
}

# File paths
DATA_DIRECTORY = 'static/data'
PRESETS_FILE = f'{DATA_DIRECTORY}/presets.json'
LOCATIONS_FILE = f'{DATA_DIRECTORY}/locations.json'
