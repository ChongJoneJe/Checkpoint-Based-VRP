# base test environment with a warehouse and drop-off points
import numpy as np
from config import NUM_NODES, LAT_RANGE, LON_RANGE, WAREHOUSE

def create_test_environment():
    """
    Generate a test environment with a fixed warehouse and random drop-off points.
    
    Returns:
        warehouse (tuple): The warehouse location (lat, lon).
        locations (np.ndarray): Array of drop-off points (lat, lon).
    """
    # Use the warehouse defined in config
    warehouse_loc = (3.127993, 101.466972) #J&T

    locations = np.array([
        [3.108874, 101.475246],  # setia home
        [3.115765, 101.475830],  # jalan setia duta
        [3.098476, 101.466822],  # jalan duat villa
        # Add more locations as needed
    ])
    return warehouse_loc, locations

if __name__ == "__main__":
    warehouse, locations = create_test_environment()
    print("Warehouse:", warehouse)
    print("Drop-off points:\n", locations)
