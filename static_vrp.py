# basic static vrp solution
import numpy as np
from config import WAREHOUSE

def compute_euclidean_distance(p1, p2):
    return np.linalg.norm(np.array(p1) - np.array(p2))

def solve_static_vrp(warehouse, locations):
    """
    Solve a static VRP using a simple nearest-neighbor approach.
    
    Args:
        warehouse (tuple): Starting and ending point (lat, lon).
        locations (np.ndarray): Array of drop-off points (lat, lon).
        
    Returns:
        route (list): Ordered list of locations starting and ending at the warehouse.
        total_distance (float): Total route distance.
    """
    remaining = list(locations)
    route = [warehouse]
    current = warehouse
    total_distance = 0.0
    
    while remaining:
        # Find the nearest location
        distances = [compute_euclidean_distance(current, point) for point in remaining]
        nearest_index = np.argmin(distances)
        nearest = remaining.pop(nearest_index)
        route.append(nearest)
        total_distance += distances[nearest_index]
        current = nearest
    
    # Return to warehouse
    total_distance += compute_euclidean_distance(current, warehouse)
    route.append(warehouse)
    
    return route, total_distance

if __name__ == "__main__":
    # Sample test case using the static VRP solver.
    warehouse = WAREHOUSE
    # Example: use 5 random points
    locations = np.array([
        (40.02, -73.98),
        (40.06, -73.96),
        (40.08, -73.94),
        (40.03, -73.99),
        (40.07, -73.97)
    ])
    
    route, total_distance = solve_static_vrp(warehouse, locations)
    print("Static VRP Route:")
    for point in route:
        print(point)
    print("Total distance:", total_distance)
