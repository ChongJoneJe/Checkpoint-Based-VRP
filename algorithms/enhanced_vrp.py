import numpy as np
import time
import math
# ADD: Import OR-Tools components safely
try:
    from ortools.constraint_solver import routing_enums_pb2
    from ortools.constraint_solver import pywrapcp
    HAS_ORTOOLS = True
except ImportError:
    HAS_ORTOOLS = False
    print("WARNING: Google OR-Tools not installed. OR-Tools algorithm will not be available for checkpoint VRP.")
    # Define dummy classes/enums if OR-Tools is not installed
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

from services.cache_service import CacheService

class EnhancedVehicleRoutingProblem:
    """
    Enhanced Vehicle Routing Problem solver that supports multiple entry/exit checkpoints
    for each cluster, allowing more optimal routes.
    Adapts to work with pre-calculated checkpoint matrices for scenario testing.
    """

    def __init__(self, warehouse, destinations, num_vehicles=1):
        """
        Initialize the enhanced VRP solver.

        Args:
            warehouse: {'lat': float, 'lon': float} coordinates of the warehouse
            destinations: List of {'lat': float, 'lon': float, 'id': any, 'cluster_id': any}
            num_vehicles: Number of vehicles to use
        """
        self.warehouse = warehouse
        self.destinations = destinations
        self.num_vehicles = num_vehicles
        self.cache_service = CacheService()

    def solve(self, prepared_data, algorithm='or_tools'):
        """
        Solve the VRP using pre-prepared data including checkpoint distance matrix.

        Args:
            prepared_data (dict): Output from VRPTestScenarioService.prepare_test_data.
                                  Must contain 'warehouse', 'active_routing_checkpoints',
                                  'checkpoint_distance_matrix', 'required_clusters',
                                  'checkpoint_to_clusters_map'.
            algorithm (str): Algorithm hint (e.g., 'or_tools', 'heuristic').

        Returns:
            dict: Solution containing routes, distance, time, etc.
        """
        print(f"[DEBUG EnhancedVRP] Solving checkpoint VRP with algorithm hint: {algorithm}")
        start_time = time.time()

        # Ensure warehouse has proper format
        warehouse = prepared_data['warehouse']
        if not isinstance(warehouse, dict):
            warehouse = {'lat': warehouse[0], 'lon': warehouse[1]}

        checkpoints = prepared_data['active_routing_checkpoints']  # Unique checkpoints
        distance_matrix = np.array(prepared_data['checkpoint_distance_matrix'])
        required_clusters = set(prepared_data['required_clusters'])
        checkpoint_to_clusters = prepared_data['checkpoint_to_clusters']  # Map checkpoint coord key to list of cluster_ids

        if not checkpoints:
            print("[ERROR EnhancedVRP] No active routing checkpoints found.")
            return {
                'warehouse': self.warehouse, 'destinations': self.destinations, 'routes': [],
                'total_distance': 0, 'computation_time': time.time() - start_time,
                'error': 'No checkpoints available for routing.'
            }

        num_locations = len(checkpoints) + 1  # +1 for warehouse
        checkpoint_indices = {cp_idx: cp for cp_idx, cp in enumerate(checkpoints, 1)}  # Map matrix index (1+) to checkpoint data
        checkpoint_coord_to_idx = {f"{cp['lat']:.6f},{cp['lon']:.6f}": idx for idx, cp in checkpoint_indices.items()}

        # --- Algorithm Selection ---
        effective_algorithm = algorithm
        if algorithm == 'two_opt':
            print("[DEBUG EnhancedVRP] Mapping UI algorithm 'two_opt' to 'heuristic' for checkpoint VRP.")
            effective_algorithm = 'heuristic'

        if effective_algorithm == 'or_tools':
            if not HAS_ORTOOLS:
                print("[ERROR EnhancedVRP] OR-Tools selected but library not found. Falling back to heuristic.")
                effective_algorithm = 'heuristic'
            else:
                try:
                    print("[DEBUG EnhancedVRP] Using Google OR-Tools algorithm for checkpoint routing...")
                    routes_checkpoint_indices, total_distance_calculated = self._solve_checkpoint_vrp_ortools(
                        num_locations, distance_matrix, required_clusters, checkpoint_indices, checkpoint_to_clusters
                    )
                except Exception as e:
                    print(f"[ERROR EnhancedVRP] OR-Tools failed: {e}. Falling back to heuristic.")
                    effective_algorithm = 'heuristic'

        if effective_algorithm == 'heuristic':
            print("[DEBUG EnhancedVRP] Using custom heuristic algorithm for checkpoint routing...")
            routes_checkpoint_indices, total_distance_calculated = self._solve_checkpoint_vrp_heuristic(
                num_locations, distance_matrix, required_clusters, checkpoint_indices, checkpoint_to_clusters
            )

        # --- Post-processing ---
        print(f"[DEBUG EnhancedVRP] Post-processing {len(routes_checkpoint_indices)} routes found by {effective_algorithm}...")
        final_routes = []
        for vehicle_route_indices in routes_checkpoint_indices:
            route_path_coords = [{'lat': warehouse['lat'], 'lon': warehouse['lon'], 'type': 'warehouse'}]
            route_stops_info = []

            for cp_idx in vehicle_route_indices:
                if cp_idx != 0:
                    cp_data = checkpoint_indices.get(cp_idx)
                    if cp_data:
                        route_path_coords.append({
                            'lat': cp_data['lat'], 
                            'lon': cp_data['lon'],
                            'type': 'checkpoint'
                        })
                        route_stops_info.append({
                            'type': 'checkpoint',
                            'lat': cp_data['lat'],
                            'lon': cp_data['lon'],
                            'clusters_served': cp_data.get('clusters', [])
                        })

            route_path_coords.append({'lat': warehouse['lat'], 'lon': warehouse['lon'], 'type': 'warehouse'})

            route_dist = 0
            full_indices = [0] + vehicle_route_indices + [0]
            for i in range(len(full_indices) - 1):
                route_dist += distance_matrix[full_indices[i]][full_indices[i + 1]]

            final_routes.append({
                'stops': route_stops_info,
                'distance': float(route_dist),
                'path': route_path_coords,
                'checkpoint_indices': vehicle_route_indices
            })

        computation_time = time.time() - start_time
        print(f"[DEBUG EnhancedVRP] Checkpoint VRP ({effective_algorithm}) solved in {computation_time:.4f} seconds.")

        solution = {
            'warehouse': warehouse,
            'destinations': self.destinations,
            'routes': final_routes,
            'total_distance': float(total_distance_calculated),
            'computation_time': float(computation_time),
            'algorithm_used': effective_algorithm
        }
        return solution

    def _solve_checkpoint_vrp_heuristic(self, num_locations, distance_matrix, required_clusters, checkpoint_indices, checkpoint_to_clusters):
        """
        Simplified Nearest Neighbor heuristic for checkpoint VRP.
        Ensures all required clusters are covered.
        Replace with a proper VRP solver (like OR-Tools) for better results.
        """
        print("[DEBUG EnhancedVRP Heuristic] Starting heuristic calculation...")
        routes = []
        total_distance = 0

        idx_to_cluster_set = {}
        for idx, cp_data in checkpoint_indices.items():
            coord_key = f"{cp_data['lat']:.6f},{cp_data['lon']:.6f}"
            idx_to_cluster_set[idx] = set(checkpoint_to_clusters.get(coord_key, []))

        unvisited_checkpoints = set(checkpoint_indices.keys())
        clusters_to_cover = set(required_clusters)

        current_location_idx = 0
        current_route = []
        route_distance = 0

        while clusters_to_cover:
            best_next_idx = -1
            min_dist = float('inf')

            for next_idx in unvisited_checkpoints:
                if idx_to_cluster_set[next_idx].intersection(clusters_to_cover):
                    dist = distance_matrix[current_location_idx][next_idx]
                    if dist < min_dist:
                        min_dist = dist
                        best_next_idx = next_idx

            if best_next_idx == -1 and unvisited_checkpoints:
                best_next_idx = min(unvisited_checkpoints, key=lambda idx: distance_matrix[current_location_idx][idx])
                min_dist = distance_matrix[current_location_idx][best_next_idx]

            if best_next_idx != -1:
                current_route.append(best_next_idx)
                route_distance += min_dist
                current_location_idx = best_next_idx
                unvisited_checkpoints.remove(best_next_idx)
                clusters_to_cover.difference_update(idx_to_cluster_set[best_next_idx])
            else:
                break

        route_distance += distance_matrix[current_location_idx][0]
        routes.append(current_route)
        total_distance = route_distance

        print(f"[DEBUG EnhancedVRP Heuristic] Heuristic finished. Found {len(routes)} route(s). Total distance: {total_distance:.2f}")
        return routes, total_distance

    def _solve_checkpoint_vrp_ortools(self, num_locations, distance_matrix, required_clusters, checkpoint_indices, checkpoint_to_clusters):
        """
        Google OR-Tools implementation for checkpoint VRP solving.
        This typically produces more optimal routes than the heuristic approach.
        Requires ortools package to be installed.
        """
        if not HAS_ORTOOLS:
            print("[ERROR EnhancedVRP ORTools] OR-Tools library not available.")
            return [], 0

        print("[DEBUG EnhancedVRP ORTools] Preparing data model for checkpoint OR-Tools...")
        data = {}
        data['distance_matrix'] = distance_matrix.tolist()
        data['num_vehicles'] = 1
        data['depot'] = 0

        manager = pywrapcp.RoutingIndexManager(
            len(data['distance_matrix']),
            data['num_vehicles'], 
            data['depot']
        )

        routing = pywrapcp.RoutingModel(manager)

        def distance_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            if 0 <= from_node < len(data['distance_matrix']) and 0 <= to_node < len(data['distance_matrix']):
                return int(data['distance_matrix'][from_node][to_node] * 1000)
            else:
                print(f"[ERROR EnhancedVRP ORTools] Invalid node index in distance_callback: from={from_node}, to={to_node}")
                return 999999999

        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        print("[DEBUG EnhancedVRP ORTools] Adding cluster visit constraints...")
        for cluster_id in required_clusters:
            serving_checkpoints = []
            for idx, cp_data in checkpoint_indices.items():
                if idx == 0:
                    continue
                cp_key = f"{cp_data['lat']:.6f},{cp_data['lon']:.6f}"
                if cluster_id in checkpoint_to_clusters.get(cp_key, []):
                    serving_checkpoints.append(idx)
            
            if serving_checkpoints:
                routing.AddDisjunction([manager.NodeToIndex(cp) for cp in serving_checkpoints], 0)

        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        search_parameters.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        )
        search_parameters.time_limit.seconds = 5

        print("[DEBUG EnhancedVRP ORTools] Starting solver...")
        solution = routing.SolveWithParameters(search_parameters)

        if not solution:
            print("[ERROR EnhancedVRP ORTools] Solver failed to find a solution.")
            raise RuntimeError("OR-Tools failed to find a solution for checkpoint VRP")

        print("[DEBUG EnhancedVRP ORTools] Solver finished. Extracting solution...")
        routes = []
        total_distance = 0

        for vehicle_id in range(data['num_vehicles']):
            route = []
            index = routing.Start(vehicle_id)

            while not routing.IsEnd(index):
                node = manager.IndexToNode(index)
                if node != 0:
                    route.append(node)
                index = solution.Value(routing.NextVar(index))

            if route:
                routes.append(route)
                route_distance = 0
                prev_idx = 0
                for node in route:
                    route_distance += distance_matrix[prev_idx][node]
                    prev_idx = node
                route_distance += distance_matrix[prev_idx][0]
                total_distance += route_distance

        total_distance_km = total_distance / 1000.0
        print(f"[DEBUG EnhancedVRP ORTools] Extracted {len(routes)} routes. Total distance: {total_distance_km:.2f} km")
        return routes, total_distance_km

    def _haversine_distance(self, lat1, lon1, lat2, lon2):
        """
        Calculate the Haversine distance between two points in kilometers
        """
        R = 6371  # Earth radius in km

        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))

        return R * c  # Distance in kilometers