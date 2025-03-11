# create test, visualize map, run solver
from environment import create_test_environment
from visualization import initialize_map, add_marker
from static_vrp import solve_static_vrp
import folium

def main():
    # Step 1: Create test environment
    warehouse, locations = create_test_environment()
    
    # Step 2: Visualize the base map with warehouse and drop-off points
    m = initialize_map(center=warehouse)
    add_marker(m, warehouse, "Warehouse", "black")
    for idx, point in enumerate(locations):
        add_marker(m, tuple(point), f"Drop-off {idx+1}", "blue")
    m.save("base_map.html")
    print("Base map saved as base_map.html")
    
    # Step 3: Solve static VRP for baseline comparison
    route, total_distance = solve_static_vrp(warehouse, locations)
    print("Static VRP Route:", route)
    print("Total Distance:", total_distance)

if __name__ == "__main__":
    main()
