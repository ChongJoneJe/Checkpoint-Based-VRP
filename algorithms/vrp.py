import numpy as np
import openrouteservice
from openrouteservice.distance_matrix import distance_matrix
import os
import random
import math
from config import DEFAULT_VEHICLE
import time
from algorithms.tsp import TravellingSalesmanProblem

try:
    from ortools.constraint_solver import routing_enums_pb2
    from ortools.constraint_solver import pywrapcp
    HAS_ORTOOLS = True
except ImportError:
    HAS_ORTOOLS = False
    print("WARNING: Google OR-Tools not installed. OR-Tools algorithm will not be available for static VRP.")
    class routing_enums_pb2:
        class FirstSolutionStrategy:
            PATH_CHEAPEST_ARC = None
        class LocalSearchMetaheuristic:
            GUIDED_LOCAL_SEARCH = None
    class pywrapcp:
        @staticmethod
        def RoutingIndexManager(*args, **kwargs): return None
        @staticmethod
        def RoutingModel(*args, **kwargs): return None
        @staticmethod
        def DefaultRoutingSearchParameters(): return None


class VehicleRoutingProblem:
    """
    Vehicle Routing Problem solver that routes vehicles from a warehouse to multiple destinations
    and back to the warehouse, optimizing for distance.
    """
    
    def __init__(self, warehouse, destinations, num_vehicles=1, api_key=None):
        """
        Initialize VRP instance
        
        Args:
            warehouse: [lat, lon] coordinates of the warehouse
            destinations: List of [lat, lon] coordinates for delivery destinations
            num_vehicles: Number of vehicles to use
            api_key: OpenRouteService API key (optional)
        """
        self.warehouse = warehouse
        self.destinations = destinations
        self.num_vehicles = min(num_vehicles, len(destinations))
        self.api_key = api_key
        self.using_road_network = False 
        
        self.checkpoints = []  # Will be populated if needed
        
        self.client = None
        
        # Create distance matrix
        self.distance_matrix = self._calculate_distance_matrix()
    
    def _calculate_distance_matrix(self):
        """
        Calculate distance matrix between all locations using OpenRouteService.
        Raises an exception if ORS fails.
        """
        self.using_road_network = False # Assume failure initially
        if not self.api_key:
            print("[ERROR VRP] ORS API key is missing. Cannot calculate road network distances.")
            raise ValueError("ORS API key is required for distance matrix calculation.")

        try:
            client = openrouteservice.Client(key=self.api_key)

            # Format coordinates for ORS (lon, lat)
            all_coords = [self.warehouse] + self.destinations
            # Ensure coordinates are [lat, lon] format before swapping
            ors_coords = [[float(point[1]), float(point[0])] for point in all_coords if len(point) == 2]

            if len(ors_coords) != len(all_coords):
                 raise ValueError("Invalid coordinate format found in warehouse or destinations.")

            print(f"[DEBUG VRP] Requesting ORS distance matrix for {len(ors_coords)} locations...")
            # Request distance matrix
            matrix_result = client.distance_matrix(
                locations=ors_coords,
                profile='driving-car',
                metrics=['distance'],
                units='km'
            )

            # Check response structure
            if 'distances' not in matrix_result or not isinstance(matrix_result['distances'], list):
                raise ValueError("ORS distance matrix response format unexpected.")

            distances = np.array(matrix_result['distances'])
            if distances.shape != (len(ors_coords), len(ors_coords)):
                 raise ValueError(f"ORS distance matrix shape mismatch. Expected ({len(ors_coords)}, {len(ors_coords)}), Got {distances.shape}")

            print("[DEBUG VRP] Successfully received ORS distance matrix.")
            self.using_road_network = True
            return distances # Return NumPy array

        except openrouteservice.exceptions.ApiError as ors_error:
             print(f"[ERROR VRP] OpenRouteService API error during distance matrix calculation: {ors_error}")
             raise ConnectionError(f"ORS API Error: {ors_error.message} (Status: {ors_error.status_code})") from ors_error
        except Exception as e:
            print(f"[ERROR VRP] Unexpected error during ORS distance matrix calculation: {e}")
            import traceback
            traceback.print_exc()
            # Re-raise as a generic error indicating failure
            raise RuntimeError(f"Failed to calculate ORS distance matrix: {e}") from e

    def _haversine_distance(self, lat1, lon1, lat2, lon2):
        """
        Calculate the Haversine distance between two points in kilometers
        """
        R = 6371  

        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        return R * c  # Distance in kilometers
    
    def _compute_distance_matrix(self, locations):
        """
        Calculate distance matrix for a given set of locations
        
        Args:
            locations: List of [lat, lon] coordinates
        
        Returns:
            numpy.ndarray: Distance matrix
        """
        n = len(locations)
        matrix = np.zeros((n, n))
        
        # Try to use OpenRouteService if API key is available
        if self.api_key:
            try:
                client = openrouteservice.Client(key=self.api_key)
                
                # Format for ORS (lon, lat)
                ors_coords = [[point[1], point[0]] for point in locations]
                
                # Request distance matrix
                result = client.distance_matrix(
                    locations=ors_coords,
                    profile='driving-car',
                    metrics=['distance'],
                    units='km'
                )
                
                # Convert to numpy array and return
                return np.array(result['distances'])
                    
            except Exception as e:
                print(f"OpenRouteService API error: {str(e)}")
                print("Falling back to Euclidean distance")
        
        # Fall back to Euclidean distance calculation
        for i in range(n):
            for j in range(n):
                if i != j:
                    lat1, lon1 = locations[i]
                    lat2, lon2 = locations[j]
                    matrix[i, j] = self._haversine_distance(lat1, lon1, lat2, lon2)
        
        return matrix

    def solve(self, algorithm="nearest_neighbor"):
        """
        Solve the VRP problem using the specified algorithm.

        Args:
            algorithm (str): Algorithm: "nearest_neighbor", "two_opt", "or_tools".

        Returns:
            dict: Solution containing routes and total distance.
        """
        print(f"[DEBUG VRP] Solving static VRP with algorithm: {algorithm}")
        start_time = time.time()

        if algorithm == "nearest_neighbor":
            solution = self._solve_nearest_neighbor()
        elif algorithm == "two_opt":
            print("[DEBUG VRP] Running Nearest Neighbor as base for 2-Opt...")
            nn_solution = self._solve_nearest_neighbor()
            print("[DEBUG VRP] Improving NN solution with 2-Opt...")
            solution = self._improve_with_two_opt(nn_solution)
        elif algorithm == "or_tools":
            if not HAS_ORTOOLS:
                print("[ERROR VRP] OR-Tools selected but library not found. Falling back to two_opt.")
                # Fallback to two_opt if OR-Tools isn't available
                nn_solution = self._solve_nearest_neighbor()
                solution = self._improve_with_two_opt(nn_solution)
            else:
                print("[DEBUG VRP] Solving static VRP with OR-Tools...")
                solution = self._solve_static_vrp_ortools()
        else:
            print(f"[ERROR VRP] Unknown algorithm: {algorithm}. Falling back to nearest_neighbor.")
            solution = self._solve_nearest_neighbor()

        computation_time = time.time() - start_time
        solution['computation_time'] = computation_time
        print(f"[DEBUG VRP] Static VRP ({algorithm}) solved in {computation_time:.4f} seconds.")
        return solution

    def _solve_nearest_neighbor(self):
        """Solve using the Nearest Neighbor algorithm."""
        print("[DEBUG VRP NN] Starting Nearest Neighbor calculation...")
        # Number of destinations
        n_destinations = len(self.destinations)
        
        if n_destinations == 0:
            return {"routes": [], "total_distance": 0}
        
        # Initialize unvisited destinations
        unvisited = set(range(n_destinations))
        
        # Calculate the ideal number of stops per vehicle
        stops_per_vehicle = math.ceil(n_destinations / self.num_vehicles)
        
        # Initialize routes and total distance
        routes = []
        total_distance = 0
        
        # For each vehicle
        for v in range(min(self.num_vehicles, n_destinations)):
            if not unvisited:
                break
                
            # Start a new route
            route = {"stops": [], "distance": 0}
            current = 0  # Start at warehouse (index 0)
            
            # Assign up to stops_per_vehicle destinations to this vehicle
            for _ in range(min(stops_per_vehicle, len(unvisited))):
                if not unvisited:
                    break
                    
                # Find the nearest unvisited destination
                nearest = min(unvisited, key=lambda i: self.distance_matrix[current][i+1])
                unvisited.remove(nearest)
                
                # Add to route
                route["stops"].append(nearest)
                route["distance"] += self.distance_matrix[current][nearest+1]
                
                # Update current position
                current = nearest + 1  # +1 because destinations start at index 1
            
            # Add return to warehouse
            route["distance"] += self.distance_matrix[current][0]
            
            # Add route to solution
            routes.append(route)
            total_distance += route["distance"]
        
        print(f"[DEBUG VRP NN] Nearest Neighbor finished. Total distance: {total_distance:.2f}")
        return {"routes": routes, "total_distance": total_distance}

    def _improve_with_two_opt(self, initial_solution):
        """Improve a solution using 2-opt local search."""
        print("[DEBUG VRP 2Opt] Starting 2-Opt improvement...")
        improved_solution = {"routes": [], "total_distance": 0}
        
        for route in initial_solution["routes"]:
            # Skip routes with fewer than 3 stops (no improvement possible)
            if len(route["stops"]) < 3:
                improved_solution["routes"].append(route)
                improved_solution["total_distance"] += route["distance"]
                continue
            
            # Create a full route including warehouse at start and end
            full_route = [0] + [stop+1 for stop in route["stops"]] + [0]
            
            # Apply 2-opt
            improved = False
            while improved:
                improved = False
                best_distance = self._calculate_route_distance(full_route)
                
                for i in range(1, len(full_route) - 2):
                    for j in range(i + 1, len(full_route) - 1):
                        # Create a new route by reversing the segment between i and j
                        new_route = full_route[:i] + full_route[i:j+1][::-1] + full_route[j+1:]
                        new_distance = self._calculate_route_distance(new_route)
                        
                        if new_distance < best_distance:
                            full_route = new_route
                            best_distance = new_distance
                            improved = True
                            break
                    
                    if improved:
                        break
            
            # Create improved route
            improved_route = {
                "stops": [idx-1 for idx in full_route[1:-1]],  # Remove warehouse and convert back to 0-indexed
                "distance": self._calculate_route_distance(full_route)
            }
            
            improved_solution["routes"].append(improved_route)
            improved_solution["total_distance"] += improved_route["distance"]
        
        print(f"[DEBUG VRP 2Opt] 2-Opt finished. Improved distance: {improved_solution['total_distance']:.2f}")
        return improved_solution

    def _solve_static_vrp_ortools(self):
        """Solve static VRP using Google OR-Tools."""
        if not HAS_ORTOOLS:
             # This case is handled in solve(), but added for safety
            print("[ERROR VRP ORTools] OR-Tools library not available.")
            return {"routes": [], "total_distance": 0, "error": "OR-Tools library not installed"}

        print("[DEBUG VRP ORTools] Preparing data model for static OR-Tools...")
        data = {}
        data['distance_matrix'] = self.distance_matrix.tolist() # Use pre-calculated matrix
        data['num_vehicles'] = self.num_vehicles
        data['depot'] = 0 # Warehouse is index 0

        if not data['distance_matrix']:
             print("[ERROR VRP ORTools] Distance matrix is empty.")
             return {"routes": [], "total_distance": 0, "error": "Distance matrix is empty"}

        num_locations = len(data['distance_matrix'])
        if num_locations <= 1: # Only warehouse
             return {"routes": [], "total_distance": 0}

        print(f"[DEBUG VRP ORTools] Num locations: {num_locations}, Num vehicles: {data['num_vehicles']}")

        try:
            manager = pywrapcp.RoutingIndexManager(num_locations, data['num_vehicles'], data['depot'])
            routing = pywrapcp.RoutingModel(manager)

            def distance_callback(from_index, to_index):
                from_node = manager.IndexToNode(from_index)
                to_node = manager.IndexToNode(to_index)
                # Ensure indices are within bounds
                if 0 <= from_node < len(data['distance_matrix']) and 0 <= to_node < len(data['distance_matrix']):
                     # OR-Tools expects integer distances, multiply by 1000 and cast
                     return int(data['distance_matrix'][from_node][to_node] * 1000)
                else:
                     print(f"[ERROR VRP ORTools] Invalid node index in distance_callback: from={from_node}, to={to_node}")
                     return 999999999 # Return a large penalty for invalid indices

            transit_callback_index = routing.RegisterTransitCallback(distance_callback)
            routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

            search_parameters = pywrapcp.DefaultRoutingSearchParameters()
            search_parameters.first_solution_strategy = (
                routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
            )
            search_parameters.local_search_metaheuristic = (
                routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
            )
            search_parameters.time_limit.seconds = 10 # Increased time limit for potentially larger static problems

            print("[DEBUG VRP ORTools] Starting solver...")
            assignment = routing.SolveWithParameters(search_parameters)

            if not assignment:
                print("[ERROR VRP ORTools] Solver failed to find a solution.")
                return {"routes": [], "total_distance": 0, "error": "OR-Tools solver failed"}

            print("[DEBUG VRP ORTools] Solver finished. Extracting solution...")
            final_routes = []
            total_distance = 0
            for vehicle_id in range(data['num_vehicles']):
                index = routing.Start(vehicle_id)
                route_nodes = []
                route_distance_m = 0 # Distance in meters (scaled by 1000)
                while not routing.IsEnd(index):
                    node_index = manager.IndexToNode(index)
                    if node_index != data['depot']: # Exclude depot from stops list
                        route_nodes.append(node_index - 1) # Convert back to 0-based destination index
                    previous_index = index
                    index = assignment.Value(routing.NextVar(index))
                    route_distance_m += routing.GetArcCostForVehicle(previous_index, index, vehicle_id)

                if route_nodes: # Only add routes that visit at least one destination
                    route_distance_km = route_distance_m / 1000.0 # Convert back to km
                    final_routes.append({
                        'stops': route_nodes,
                        'distance': route_distance_km
                    })
                    total_distance += route_distance_km

            print(f"[DEBUG VRP ORTools] Extracted {len(final_routes)} routes. Total distance: {total_distance:.2f} km")
            return {"routes": final_routes, "total_distance": total_distance}

        except Exception as e:
            print(f"[ERROR VRP ORTools] Exception during OR-Tools solving: {e}")
            import traceback
            traceback.print_exc()
            return {"routes": [], "total_distance": 0, "error": f"OR-Tools exception: {e}"}

    def _calculate_route_distance(self, route):
        """
        Calculate the total distance of a route
        
        Args:
            route (list): List of location indices (including warehouse)
            
        Returns:
            float: Total route distance
        """
        distance = 0
        for i in range(len(route) - 1):
            distance += self.distance_matrix[route[i]][route[i+1]]
        return distance