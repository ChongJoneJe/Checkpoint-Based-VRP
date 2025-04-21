import numpy as np
import time
import math
import itertools

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


class EnhancedVehicleRoutingProblem:
    """
    Enhanced Vehicle Routing Problem solver that supports multiple entry/exit checkpoints
    for each cluster, allowing more optimal routes.
    Adapts to work with pre-calculated checkpoint matrices for scenario testing.
    """

    def __init__(self, warehouse, destinations, num_vehicles=1):
        """
        Initialize the solver.

        Args:
            warehouse (dict): Warehouse coordinates {'lat': float, 'lon': float}.
            destinations (list): List of destination dictionaries (used for context).
            num_vehicles (int): Number of vehicles available.
        """
        self.warehouse = warehouse
        self.destinations = destinations  # Keep for context if needed
        self.num_vehicles = num_vehicles
        print(f"[DEBUG EnhancedVRP __init__] Initialized with {self.num_vehicles} vehicles.")

    def solve(self, prepared_data, algorithm='or_tools', options=None):
        """
        Solve checkpoint VRP using prepared data. Handles both full VRP and subproblems.

        Args:
            prepared_data (dict): Contains warehouse, checkpoints, matrix, clusters, etc.
                                  May contain 'subproblem_locations' for subproblem context.
            algorithm (str): 'or_tools', 'heuristic', or 'two_opt'.
            options (dict, optional): Additional options, especially for subproblems:
                                      {'is_subproblem': bool, 'start_node': int, 'end_node': int,
                                       'pickup_delivery_pairs': list[(int, int)]}.

        Returns:
            dict: A dictionary containing the solution routes, distance, time, etc., or an error message.
        """
        print(f"[DEBUG EnhancedVRP solve] Solving checkpoint VRP. Algorithm hint: {algorithm}, Instance Vehicles: {self.num_vehicles}")
        start_time = time.time()
        options = options or {}

        # --- Data Extraction ---
        warehouse = prepared_data.get('warehouse') # Should always be present
        checkpoints = prepared_data.get('active_routing_checkpoints', []) # Intermediate nodes for full VRP
        distance_matrix = prepared_data.get('checkpoint_distance_matrix')
        required_clusters = set(prepared_data.get('required_clusters', [])) # For full VRP cluster coverage check
        checkpoint_to_clusters = prepared_data.get('checkpoint_to_clusters', {}) # For full VRP cluster coverage check
        subproblem_locations_list = prepared_data.get('subproblem_locations') # Full list for subproblems

        # --- Initial Validation ---
        if warehouse is None:
             print("[ERROR EnhancedVRP solve] Warehouse data is missing.")
             # Cannot proceed without warehouse context
             return {'error': 'Warehouse data missing.', 'computation_time': time.time() - start_time}

        if distance_matrix is None or not isinstance(distance_matrix, np.ndarray) or distance_matrix.size == 0:
            print("[ERROR EnhancedVRP solve] Distance matrix is missing or invalid.")
            return {
                'warehouse': warehouse, 'destinations': self.destinations, 'routes': [],
                'total_distance': 0, 'computation_time': time.time() - start_time,
                'error': 'Distance matrix missing or invalid.', 'algorithm_used': algorithm
            }

        # --- Determine Problem Size and Node Mapping ---
        num_locations = 0
        if subproblem_locations_list is not None and isinstance(subproblem_locations_list, list):
            # If subproblem_locations is provided, use its length
            num_locations = len(subproblem_locations_list)
            print(f"[DEBUG EnhancedVRP solve] Using num_locations from subproblem_locations: {num_locations}")
        elif distance_matrix is not None:
             # Otherwise, use the matrix dimension (should match for full VRP)
             num_locations = distance_matrix.shape[0]
             print(f"[DEBUG EnhancedVRP solve] Using num_locations from distance_matrix shape: {num_locations}")
        else:
             # Should not happen if matrix check passed, but as a fallback
             print("[ERROR EnhancedVRP solve] Cannot determine number of locations.")
             return {'error': 'Cannot determine number of locations.', 'computation_time': time.time() - start_time}

        if num_locations == 0:
             print("[ERROR EnhancedVRP solve] Number of locations is zero.")
             return {'error': 'Number of locations is zero.', 'computation_time': time.time() - start_time}

        # Create a map from matrix index (0 to num_locations-1) to location data
        node_indices_map = {}
        if subproblem_locations_list is not None:
             # For subproblems, the indices relate directly to the subproblem_locations list
             if len(subproblem_locations_list) != num_locations:
                  print(f"[ERROR EnhancedVRP solve] Mismatch: len(subproblem_locations)={len(subproblem_locations_list)} != num_locations={num_locations}")
                  return {'error': 'Subproblem location list size mismatch.', 'computation_time': time.time() - start_time}
             node_indices_map = {idx: data for idx, data in enumerate(subproblem_locations_list)}
             print(f"[DEBUG EnhancedVRP solve] Created node_indices_map for subproblem (size {len(node_indices_map)})")
        else:
             # Original mapping for full VRP (0 is warehouse, 1+ are checkpoints)
             if len(checkpoints) != num_locations - 1:
                  print(f"[WARN EnhancedVRP solve] Mismatch between len(checkpoints)={len(checkpoints)} and num_locations-1={num_locations-1}")
                  # Allow proceeding, but mapping might be incomplete if checkpoints list was wrong
             node_indices_map = {0: warehouse}
             node_indices_map.update({cp_idx: cp for cp_idx, cp in enumerate(checkpoints, 1)})
             print(f"[DEBUG EnhancedVRP solve] Created node_indices_map for full VRP (size {len(node_indices_map)})")

        # Required for cluster coverage check in full VRP heuristic/post-processing
        idx_to_cluster_set = {
            idx: set(checkpoint_to_clusters.get(f"{cp_data['lat']:.6f},{cp_data['lon']:.6f}", []))
            for idx, cp_data in node_indices_map.items() if idx != 0 # Exclude warehouse
        }

        print(f"[DEBUG EnhancedVRP solve] Final num_locations for solver: {num_locations}")

        # --- Algorithm Setup ---
        routes_checkpoint_indices = []
        total_distance_calculated = 0.0
        solver_error = None
        effective_algorithm_used = algorithm

        run_two_opt_refinement = (algorithm == 'two_opt')
        if run_two_opt_refinement:
            print("[DEBUG EnhancedVRP solve] Mapping UI algorithm 'two_opt' to 'heuristic' + 2-Opt refinement.")
            effective_algorithm = 'heuristic'

        # --- Main Solving Logic ---
        try:
            # Determine if it's a subproblem and get parameters
            is_subproblem = options.get('is_subproblem', False)
            start_node = options.get('start_node', 0)
            end_node = options.get('end_node', num_locations - 1 if is_subproblem else 0)
            current_num_vehicles = 1 if is_subproblem else self.num_vehicles
            pickup_delivery_pairs = options.get('pickup_delivery_pairs', []) if is_subproblem else []


            # Validate start/end node indices passed from options using the CORRECTED num_locations
            if not (0 <= start_node < num_locations):
                 raise ValueError(f"Invalid start_node ({start_node}) received in options for problem with {num_locations} locations.")
            if not (0 <= end_node < num_locations):
                 raise ValueError(f"Invalid end_node ({end_node}) received in options for problem with {num_locations} locations.")

            # --- OR-Tools Solver Path ---
            if algorithm == 'or_tools':
                effective_algorithm_used = 'or_tools' # Confirm attempt
                if not HAS_ORTOOLS:
                    print("[ERROR EnhancedVRP solve] OR-Tools selected but library not found.")
                    solver_error = "OR-Tools library not found."
                    # DO NOT FALLBACK - return error immediately
                    end_time = time.time()
                    return {
                        'warehouse': warehouse, 'destinations': self.destinations, 'routes': [],
                        'total_distance': 0, 'computation_time': float(end_time - start_time),
                        'error': solver_error, 'algorithm_used': 'or_tools (failed: not found)'
                    }
                else:
                    try:
                        print("[DEBUG EnhancedVRP solve] Using Google OR-Tools algorithm...")
                        manager = None
                        routing = None
                        # Setup Manager: Defines nodes, vehicles, starts, ends
                        if is_subproblem:
                            print(f"[DEBUG EnhancedVRP solve OR-Tools] Subproblem setup: NumLoc={num_locations}, Vehicles=1, Start={start_node}, End={end_node}")
                            manager = pywrapcp.RoutingIndexManager(num_locations, 1, [start_node], [end_node])
                        else:
                            print(f"[DEBUG EnhancedVRP solve OR-Tools] Full VRP setup: NumLoc={num_locations}, Vehicles={current_num_vehicles}, Depot={start_node}") # Depot is start_node (0)
                            manager = pywrapcp.RoutingIndexManager(num_locations, current_num_vehicles, start_node) # Depot is always 0

                        if manager is None:
                             raise RuntimeError("Failed to initialize RoutingIndexManager.")

                        # Setup Model: Uses the manager to build the routing model
                        routing = pywrapcp.RoutingModel(manager)

                        # Distance Callback: How OR-Tools gets distances
                        def distance_callback(from_index, to_index):
                            from_node = manager.IndexToNode(from_index)
                            to_node = manager.IndexToNode(to_index)
                            if 0 <= from_node < distance_matrix.shape[0] and 0 <= to_node < distance_matrix.shape[0]:
                                return int(distance_matrix[from_node][to_node] * 1000) # Use integers (e.g., meters)
                            else:
                                print(f"[ERROR distance_callback] Invalid node indices: {from_node}, {to_node} for matrix shape {distance_matrix.shape}")
                                return 999999999 # Penalize invalid access

                        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
                        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

                        # Distance Dimension: For constraints like max distance, P/D order
                        dimension_name = 'Distance'
                        max_route_distance_meters_scaled = 100 * 1000 * 1000
                        routing.AddDimension(
                            transit_callback_index,
                            0,  # no slack allowed
                            max_route_distance_meters_scaled,
                            True,  
                            dimension_name)
                        distance_dimension = routing.GetDimensionOrDie(dimension_name)
                        # distance_dimension.SetGlobalSpanCostCoefficient(100)

                        routing.SetFixedCostOfVehicle(0, 0) # No fixed cost for vehicles
                        # Pickup and Delivery Constraints (ONLY for subproblems with pairs)
                        if is_subproblem and pickup_delivery_pairs:
                            print(f"[DEBUG EnhancedVRP solve OR-Tools] Adding {len(pickup_delivery_pairs)} P/D constraints for subproblem.")
                            for pair_index, (pickup_idx, delivery_idx) in enumerate(pickup_delivery_pairs):
                                if 0 <= pickup_idx < num_locations and 0 <= delivery_idx < num_locations:
                                    pickup_node_rm = manager.NodeToIndex(pickup_idx)
                                    delivery_node_rm = manager.NodeToIndex(delivery_idx)
                                    routing.AddPickupAndDelivery(pickup_node_rm, delivery_node_rm)
                                    routing.solver().Add(routing.VehicleVar(pickup_node_rm) == routing.VehicleVar(delivery_node_rm)) # Same vehicle
                                    routing.solver().Add(distance_dimension.CumulVar(pickup_node_rm) <= distance_dimension.CumulVar(delivery_node_rm)) # Order
                                    print(f"  - Added constraint: Pickup Node {pickup_idx} -> Delivery Node {delivery_idx}")
                                else:
                                    print(f"[WARN EnhancedVRP solve OR-Tools] Invalid P/D node indices ({pickup_idx}, {delivery_idx}) for num_locations={num_locations}. Skipping constraint.")

                        # Search Parameters
                        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
                        search_parameters.first_solution_strategy = (
                            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)
                        search_parameters.local_search_metaheuristic = (
                            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH)
                        search_parameters.time_limit.FromSeconds(30) # Time limit

                        # Solve
                        print("[DEBUG EnhancedVRP solve OR-Tools] Starting solver...")
                        solution = routing.SolveWithParameters(search_parameters)
                        print("[DEBUG EnhancedVRP solve OR-Tools] Solver finished.")

                        # Process OR-Tools Solution
                        if solution:
                            print("[DEBUG EnhancedVRP solve OR-Tools] Solution found.")
                            routes_checkpoint_indices = [] # Reset/initialize
                            total_distance_meters = 0
                            num_vehicles_in_model = 1 if is_subproblem else current_num_vehicles

                            for vehicle_id in range(num_vehicles_in_model):
                                index = routing.Start(vehicle_id)
                                route_nodes = []
                                while not routing.IsEnd(index):
                                    node_index = manager.IndexToNode(index)
                                    # Add node to route *unless* it's the designated start or end node of the problem
                                    is_problem_start_node = (node_index == start_node)
                                    # For full VRP, end node is also start node (0). For subproblem, it's different.
                                    is_problem_end_node = (node_index == end_node and is_subproblem) or \
                                                          (node_index == start_node and not is_subproblem and routing.IsEnd(solution.Value(routing.NextVar(index)))) # Check if it's the depot AND the last stop

                                    if not is_problem_start_node and not is_problem_end_node:
                                         route_nodes.append(node_index)

                                    previous_index = index
                                    index = solution.Value(routing.NextVar(index))
                                    # Accumulate distance directly from solution objective if possible, or arc costs
                                    # route_distance += routing.GetArcCostForVehicle(previous_index, index, vehicle_id) # Less reliable if objective is complex

                                if route_nodes: # Only add routes that visit intermediate nodes
                                    routes_checkpoint_indices.append(route_nodes)
                                    print(f"  - Vehicle {vehicle_id} Route Nodes: {route_nodes}")
                                else:
                                     print(f"  - Vehicle {vehicle_id} Route is empty or only visits start/end.")

                            total_distance_meters = solution.ObjectiveValue()
                            total_distance_calculated = total_distance_meters / 1000.0 # Convert to km
                            print(f"  - OR-Tools Objective (Total Distance): {total_distance_calculated:.2f} km")

                            # Subproblem check
                            if is_subproblem and len(routes_checkpoint_indices) > 1:
                                 print(f"[WARN EnhancedVRP solve OR-Tools] Subproblem solve resulted in {len(routes_checkpoint_indices)} routes, expected 1. Check constraints/setup.")
                                 # Decide how to handle this - maybe take the longest/first? For now, keep all.

                        else:
                            print("[ERROR EnhancedVRP solve OR-Tools] No solution found.")
                            solver_error = "OR-Tools failed to find a solution."

                    except Exception as ortools_exc:
                        print(f"[ERROR EnhancedVRP solve] OR-Tools failed: {ortools_exc}. Falling back to heuristic.")
                        import traceback
                        traceback.print_exc()
                        solver_error = f"OR-Tools failed: {ortools_exc}"

            # --- Heuristic Solver Path (Includes 2-Opt refinement if requested) ---
            # This path is executed ONLY if algorithm is 'heuristic' or 'two_opt'
            elif algorithm == 'heuristic' or algorithm == 'two_opt':
                effective_algorithm_used = 'heuristic' # Base algorithm
                # --- Constraint Check for Dynamic Subproblems ---
                if is_subproblem and pickup_delivery_pairs:
                    if not HAS_ORTOOLS:
                        # If OR-Tools is NOT available, we cannot enforce constraints. Error out.
                        print("[ERROR EnhancedVRP solve] Heuristic/2-Opt requested for subproblem with P/D pairs, but OR-Tools is unavailable to enforce constraints.")
                        solver_error = "OR-Tools needed but unavailable to enforce P/D constraints for dynamic subproblems using Heuristic/2-Opt."
                        # Return immediately as the result would be invalid
                        end_time = time.time()
                        return {
                            'warehouse': warehouse, 'destinations': self.destinations, 'routes': [],
                            'total_distance': 0, 'computation_time': float(end_time - start_time),
                            'error': solver_error, 'algorithm_used': f'{algorithm} (failed constraint check)'
                        }
                    else:
                        # OR-Tools IS available, but user chose heuristic/2-opt. Proceed with warning.
                        print("[CRITICAL WARN EnhancedVRP solve Heuristic] Heuristic/2-Opt running for subproblem with P/D pairs. ORDER CONSTRAINTS ARE NOT ENFORCED. Route may be logically invalid.")

                print(f"[DEBUG EnhancedVRP solve] Using heuristic algorithm (NN-based)...")
                # Call the heuristic solver
                routes_checkpoint_indices, total_distance_calculated = self._solve_checkpoint_vrp_heuristic(
                    num_locations, distance_matrix, required_clusters, node_indices_map, idx_to_cluster_set,
                    current_num_vehicles, start_node, end_node, is_subproblem
                )

                # Apply 2-Opt refinement if requested and heuristic succeeded
                if algorithm == 'two_opt':
                    effective_algorithm_used = 'heuristic+2opt' # Update final algorithm string
                    print(f"[DEBUG EnhancedVRP solve] Applying 2-Opt refinement to heuristic routes...")
                    if distance_matrix is None:
                        print("[ERROR EnhancedVRP solve] Cannot run 2-Opt: Missing distance matrix.")
                        # This shouldn't happen due to earlier checks, but good to be safe
                        solver_error = "Missing distance matrix for 2-Opt."
                    else:
                        routes_checkpoint_indices, total_distance_calculated = self._improve_checkpoint_routes_with_two_opt(
                            routes_checkpoint_indices, distance_matrix, start_node, end_node
                        )
            else:
                 # Should not happen if UI is correct, but handle unknown algorithm
                 print(f"[ERROR EnhancedVRP solve] Unknown algorithm specified: {algorithm}")
                 solver_error = f"Unknown algorithm: {algorithm}"

            # --- Final Check for Solver Errors before Post-processing ---
            if solver_error:
                 print(f"[ERROR EnhancedVRP solve] Solver phase failed: {solver_error}")
                 end_time = time.time()
                 return {
                     'warehouse': warehouse, 'destinations': self.destinations, 'routes': [],
                     'total_distance': 0, 'computation_time': float(end_time - start_time),
                     'error': solver_error, 'algorithm_used': effective_algorithm_used + " (failed)"
                 }

            # --- Log Raw Solver Output ---
            if effective_algorithm_used == 'or_tools' and not solver_error:
                print(f"[DEBUG EnhancedVRP solve] OR-Tools raw routes (indices): {routes_checkpoint_indices}")
            elif effective_algorithm_used.startswith('heuristic'): # Covers 'heuristic' and 'heuristic+2opt'
                print(f"[DEBUG EnhancedVRP solve] Heuristic raw routes (indices): {routes_checkpoint_indices}")

            # --- Post-processing (Convert raw indices to structured route data) ---
            solution_routes = []
            final_total_distance = 0.0
            print(f"[DEBUG EnhancedVRP solve] Post-processing {len(routes_checkpoint_indices)} routes found by {effective_algorithm_used}...")

            for vehicle_id, route_indices in enumerate(routes_checkpoint_indices):
                print(f"[DEBUG EnhancedVRP solve] Processing Vehicle {vehicle_id}, Raw Indices: {route_indices}")
                route_path = [] # Full sequence including start/end for visualization/geometry
                route_stops = [] # Primary stops (e.g., checkpoints) for display

                # Get the correct start location data using node_indices_map
                start_loc_data = node_indices_map.get(start_node)
                if start_loc_data:
                    route_path.append({
                        'lat': start_loc_data['lat'], 'lon': start_loc_data['lon'],
                        'type': start_loc_data.get('type', 'warehouse' if not is_subproblem else 'subproblem_start'),
                        'is_dynamic': start_loc_data.get('is_dynamic', False),
                        'matrix_idx': start_node # Include matrix index
                    })
                else:
                    print(f"[WARN EnhancedVRP solve] Could not find start node data (Index: {start_node}) for vehicle {vehicle_id}")

                # Process intermediate indices (route_indices should NOT contain start/end from solver)
                for node_matrix_index in route_indices:
                    loc_data = node_indices_map.get(node_matrix_index) # Use the map

                    if loc_data:
                        loc_type = loc_data.get('type', 'unknown')
                        print(f"[DEBUG EnhancedVRP solve]  -> Adding stop: Index={node_matrix_index}, Type={loc_type}, Coords=({loc_data.get('lat')},{loc_data.get('lon')})")

                        # Always add to the detailed path
                        path_point = {
                            'lat': loc_data['lat'], 'lon': loc_data['lon'],
                            'type': loc_type,
                            'matrix_idx': node_matrix_index,
                            'id': loc_data.get('id'),
                            'is_dynamic': loc_data.get('is_dynamic', False)
                        }
                        route_path.append(path_point)

                        # Add to 'stops' list if it's a primary stop type (e.g., checkpoint)
                        # Adjust this condition based on what should be listed as a numbered stop
                        if loc_type == 'checkpoint':
                            route_stops.append({
                                'lat': loc_data['lat'], 'lon': loc_data['lon'],
                                'clusters_served': list(idx_to_cluster_set.get(node_matrix_index, set())), # Get clusters served by this index
                                'type': 'checkpoint',
                                'is_dynamic': loc_data.get('is_dynamic', False),
                                'matrix_idx': node_matrix_index
                            })
                        # Optionally add dynamic P/D to stops list as well if needed for display
                        elif loc_type in ['pickup', 'dropoff'] and loc_data.get('is_dynamic', False):
                             route_stops.append({
                                'lat': loc_data['lat'], 'lon': loc_data['lon'],
                                'type': loc_type,
                                'is_dynamic': True,
                                'matrix_idx': node_matrix_index
                            })

                    else:
                        print(f"[ERROR EnhancedVRP solve] Location data not found for matrix index: {node_matrix_index} using node_indices_map.")

                # Get the correct end location data using node_indices_map
                end_loc_data = node_indices_map.get(end_node)
                if end_loc_data:
                     # Avoid adding depot (0) again if it's the same as start_node (full VRP)
                     if not (not is_subproblem and start_node == end_node):
                        route_path.append({
                            'lat': end_loc_data['lat'], 'lon': end_loc_data['lon'],
                            'type': end_loc_data.get('type', 'warehouse' if not is_subproblem else 'subproblem_end'),
                            'is_dynamic': end_loc_data.get('is_dynamic', False),
                            'matrix_idx': end_node # Include matrix index
                        })
                else:
                    print(f"[WARN EnhancedVRP solve] Could not find end node data (Index: {end_node}) for vehicle {vehicle_id}")

                # Calculate distance for this specific route using the full path indices
                full_path_indices = [p['matrix_idx'] for p in route_path if 'matrix_idx' in p]
                route_dist = self._calculate_checkpoint_route_distance(full_path_indices, distance_matrix)
                final_total_distance += route_dist

                solution_routes.append({
                    'vehicle_id': vehicle_id,
                    'path': route_path,    # Full path for geometry/visualization
                    'stops': route_stops,   # Primary stops for listing/markers
                    'distance': route_dist # Use calculated distance for this route
                })
                print(f"[DEBUG EnhancedVRP solve] Vehicle {vehicle_id} - Final route_path length: {len(route_path)}")
                print(f"[DEBUG EnhancedVRP solve] Vehicle {vehicle_id} - Final route_stops length: {len(route_stops)}")


            end_time = time.time()
            # Use the summed distance from post-processing for consistency
            total_distance_calculated = final_total_distance
            print(f"[DEBUG EnhancedVRP solve] Checkpoint VRP ({effective_algorithm_used}) finished in {end_time - start_time:.4f} seconds. Total distance: {total_distance_calculated:.2f} km")

            # Calculate missing clusters (only relevant for full VRP)
            missing_clusters_list = []
            if not is_subproblem:
                 covered_clusters = set(itertools.chain.from_iterable([idx_to_cluster_set.get(idx, set()) for route in routes_checkpoint_indices for idx in route]))
                 missing_clusters_list = sorted(list(required_clusters - covered_clusters))
                 if missing_clusters_list:
                      print(f"[WARN EnhancedVRP solve] Missing required clusters: {missing_clusters_list}")

            return {
                'warehouse': warehouse,
                'destinations': self.destinations,
                'routes': solution_routes,
                'total_distance': float(total_distance_calculated),
                'computation_time': float(end_time - start_time),
                'algorithm_used': effective_algorithm_used,
                'error': None, 
                'missing_clusters': missing_clusters_list
            }

        except Exception as e:
            # Catch-all for unexpected errors during the process
            print(f"[ERROR EnhancedVRP solve] Exception occurred during solving: {e}")
            import traceback
            traceback.print_exc()
            return {
                'warehouse': warehouse, 'destinations': self.destinations, 'routes': [],
                'total_distance': 0, 'computation_time': time.time() - start_time,
                'error': f"Unexpected error: {e}", 'algorithm_used': effective_algorithm_used + " (exception)"
            }

    def _solve_checkpoint_vrp_heuristic(self, num_locations, distance_matrix, required_clusters, checkpoint_indices, idx_to_cluster_set, num_vehicles, start_node=0, end_node=0, is_subproblem=False):
        """
        Multi-vehicle Nearest Neighbor heuristic for checkpoint VRP.
        Adapts for single-vehicle subproblems with specified start/end nodes.

        Args:
            num_locations (int): Total number of nodes in the matrix (including start/end).
            distance_matrix (np.ndarray): The distance matrix to use.
            required_clusters (set): Clusters to cover (used only for full VRP).
            checkpoint_indices (dict): Map matrix index -> checkpoint data (used only for full VRP).
            idx_to_cluster_set (dict): Map matrix index -> set of clusters covered (used only for full VRP).
            num_vehicles (int): Number of vehicles (should be 1 for subproblem).
            start_node (int): The starting node index for the route(s). Defaults to 0.
            end_node (int): The ending node index for the route(s). Defaults to 0.
            is_subproblem (bool): Flag indicating if this is a single-route subproblem.

        Returns:
            tuple: (list_of_routes, total_distance)
                   For subproblems, list_of_routes contains a single route (list of intermediate node indices).
        """
        if is_subproblem:
            print(f"[DEBUG EnhancedVRP Heuristic Subproblem] Starting heuristic for subproblem. Start={start_node}, End={end_node}")
            if num_vehicles != 1:
                print(f"[WARN EnhancedVRP Heuristic Subproblem] Expected 1 vehicle for subproblem, got {num_vehicles}. Using 1.")
                num_vehicles = 1

            intermediate_nodes = set(range(num_locations)) - {start_node, end_node}
            if not intermediate_nodes:
                print("[DEBUG EnhancedVRP Heuristic Subproblem] No intermediate nodes to visit.")
                dist = distance_matrix[start_node][end_node] if 0 <= start_node < num_locations and 0 <= end_node < num_locations else 0
                return [[]], dist

            route_indices = []
            current_loc_idx = start_node
            total_distance = 0.0
            unvisited_intermediate = set(intermediate_nodes)

            while unvisited_intermediate:
                nearest_node = min(unvisited_intermediate, key=lambda node: distance_matrix[current_loc_idx][node])

                dist_to_nearest = distance_matrix[current_loc_idx][nearest_node]
                total_distance += dist_to_nearest
                route_indices.append(nearest_node)
                current_loc_idx = nearest_node
                unvisited_intermediate.remove(nearest_node)
                print(f"[DEBUG EnhancedVRP Heuristic Subproblem] Visiting node {nearest_node} (Dist: {dist_to_nearest:.2f})")

            dist_to_end = distance_matrix[current_loc_idx][end_node]
            total_distance += dist_to_end
            print(f"[DEBUG EnhancedVRP Heuristic Subproblem] Returning to end node {end_node} (Dist: {dist_to_end:.2f})")

            print(f"[DEBUG EnhancedVRP Heuristic Subproblem] Finished. Route: {route_indices}, Total Distance: {total_distance:.2f}")
            return [route_indices], total_distance

        else:
            print(f"[DEBUG EnhancedVRP Heuristic Full] Starting heuristic calculation for {num_vehicles} vehicles...")
            all_routes_indices = []
            total_distance = 0
            unvisited_checkpoints = set(checkpoint_indices.keys())
            clusters_to_cover = set(required_clusters)
            vehicle_routes = [[] for _ in range(num_vehicles)]
            vehicle_distances = [0.0] * num_vehicles
            vehicle_current_loc = [start_node] * num_vehicles
            vehicle_clusters_covered = [set() for _ in range(num_vehicles)]

            while clusters_to_cover:
                best_assignment = None
                min_dist = float('inf')
                for v_idx in range(num_vehicles):
                    current_loc_idx = vehicle_current_loc[v_idx]
                    relevant_checkpoints = {cp_idx for cp_idx in unvisited_checkpoints if idx_to_cluster_set.get(cp_idx, set()).intersection(clusters_to_cover)}
                    candidates = relevant_checkpoints if relevant_checkpoints else unvisited_checkpoints
                    if not candidates: continue
                    for cp_idx in candidates:
                        dist = distance_matrix[current_loc_idx][cp_idx]
                        if dist < min_dist:
                            min_dist = dist
                            best_assignment = (v_idx, cp_idx, dist)

                if best_assignment:
                    v_idx, cp_idx, dist = best_assignment
                    vehicle_routes[v_idx].append(cp_idx)
                    vehicle_distances[v_idx] += dist
                    vehicle_current_loc[v_idx] = cp_idx
                    covered_by_cp = idx_to_cluster_set.get(cp_idx, set())
                    vehicle_clusters_covered[v_idx].update(covered_by_cp)
                    clusters_to_cover.difference_update(covered_by_cp)
                    unvisited_checkpoints.remove(cp_idx)
                else:
                    if clusters_to_cover: print(f"[WARN EnhancedVRP Heuristic Full] Could not cover all clusters. Remaining: {clusters_to_cover}")
                    break

            for v_idx in range(num_vehicles):
                if vehicle_routes[v_idx]:
                    return_dist = distance_matrix[vehicle_current_loc[v_idx]][end_node]
                    vehicle_distances[v_idx] += return_dist
                    all_routes_indices.append(vehicle_routes[v_idx])
                    total_distance += vehicle_distances[v_idx]

            print(f"[DEBUG EnhancedVRP Heuristic Full] Finished. Found {len(all_routes_indices)} routes. Total distance: {total_distance:.2f}")
            return all_routes_indices, total_distance

    def _improve_checkpoint_routes_with_two_opt(self, routes_indices, distance_matrix, start_node=0, end_node=0):
        """
        Applies 2-Opt refinement to each checkpoint route.
        Accepts start_node and end_node for subproblem compatibility.
        Uses the provided distance_matrix.
        """
        print(f"[DEBUG EnhancedVRP 2Opt] Starting 2-Opt refinement. StartNode={start_node}, EndNode={end_node}")
        refined_routes = []
        total_refined_distance = 0

        # For subproblem, routes_indices should contain only one route list
        for route_indices in routes_indices:
            if len(route_indices) < 2:  # Need at least 2 intermediate stops for 2-opt swap
                refined_routes.append(route_indices)
                full_indices_for_dist = [start_node] + route_indices + [end_node]
                # Pass the correct matrix
                dist = self._calculate_checkpoint_route_distance(full_indices_for_dist, distance_matrix)
                total_refined_distance += dist
                continue

            # Create full route including the correct start and end nodes
            full_route = [start_node] + route_indices + [end_node]
            current_best_route = list(full_route)
            # Pass the correct matrix
            best_distance = self._calculate_checkpoint_route_distance(current_best_route, distance_matrix)

            improved = True
            while improved:
                improved = False
                # Iterate through swappable indices (excluding start and end nodes)
                for i in range(1, len(current_best_route) - 2):
                    for j in range(i + 1, len(current_best_route) - 1):
                        new_route = current_best_route[:i] + current_best_route[i:j+1][::-1] + current_best_route[j+1:]
                        # Pass the correct matrix
                        new_distance = self._calculate_checkpoint_route_distance(new_route, distance_matrix)

                        if new_distance < best_distance:
                            current_best_route = new_route
                            best_distance = new_distance
                            improved = True
                            break  # Restart scan after improvement
                    if improved:
                        break

            # Extract intermediate indices, excluding the specific start/end nodes
            refined_route_indices = current_best_route[1:-1]
            refined_routes.append(refined_route_indices)
            total_refined_distance += best_distance
            print(f"[DEBUG EnhancedVRP 2Opt] Refined route distance: {best_distance:.2f}")

        print(f"[DEBUG EnhancedVRP 2Opt] 2-Opt refinement finished. Total distance: {total_refined_distance:.2f}")
        return refined_routes, total_refined_distance

    def _calculate_checkpoint_route_distance(self, route_indices, distance_matrix):
        """Calculates distance for a route given by indices using the provided matrix."""
        distance = 0
        for i in range(len(route_indices) - 1):
            try:
                idx1 = route_indices[i]
                idx2 = route_indices[i+1]
                if 0 <= idx1 < distance_matrix.shape[0] and 0 <= idx2 < distance_matrix.shape[0]:
                    distance += distance_matrix[idx1][idx2]
                else:
                    print(f"[ERROR EnhancedVRP _calc_dist] Index out of bounds. Indices: {idx1}, {idx2}. Matrix shape: {distance_matrix.shape}")
                    return float('inf')
            except IndexError:
                print(f"[ERROR EnhancedVRP _calc_dist] IndexError. Indices: {route_indices}, Matrix shape: {distance_matrix.shape}")
                return float('inf')
        return distance