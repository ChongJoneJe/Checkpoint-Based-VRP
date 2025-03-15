import numpy as np

def euclidean_distance(p1, p2):
    """Calculate Euclidean distance between two points."""
    return np.linalg.norm(np.array(p1) - np.array(p2))

def haversine_distance(p1, p2):
    """
    Calculate haversine distance between two points in kilometers.
    Points should be [lat, lon] coordinates in decimal degrees.
    """
    # Convert decimal degrees to radians
    lat1, lon1 = np.radians(p1[0]), np.radians(p1[1])
    lat2, lon2 = np.radians(p2[0]), np.radians(p2[1])
    
    # Haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
    c = 2 * np.arcsin(np.sqrt(a))
    r = 6371  # Radius of Earth in kilometers
    
    return c * r

def calculate_distance_matrix(locations, distance_fn=haversine_distance):
    """
    Calculate distance matrix for a set of locations.
    
    Args:
        locations: List of Location objects or coordinate arrays
        distance_fn: Function to calculate distance
        
    Returns:
        2D array of distances between locations
    """
    n = len(locations)
    matrix = np.zeros((n, n))
    
    for i in range(n):
        for j in range(i+1, n):
            if hasattr(locations[i], 'coordinates'):
                # If Location objects
                dist = distance_fn(locations[i].coordinates, locations[j].coordinates)
            else:
                # If coordinate arrays
                dist = distance_fn(locations[i], locations[j])
            
            matrix[i, j] = dist
            matrix[j, i] = dist
            
    return matrix