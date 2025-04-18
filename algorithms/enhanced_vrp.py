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

    # MODIFIED: Accept num_vehicles in init
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

    def solve(self, prepared_data, algorithm='or_tools'):
        """Solve checkpoint VRP using prepared data."""
        print(f"[DEBUG EnhancedVRP solve] Solving checkpoint VRP. Algorithm hint: {algorithm}, Vehicles: {self.num_vehicles}")
        start_time = time.time()

        # --- Data Extraction ---
        warehouse = prepared_data['warehouse']  # Already formatted dict
        # MODIFIED: Use the correct key from prepare_test_data
        checkpoints = prepared_data.get('active_routing_checkpoints', [])  # Use .get for safety
        distance_matrix = prepared_data.get('checkpoint_distance_matrix')
        required_clusters = set(prepared_data.get('required_clusters', []))
        checkpoint_to_clusters = prepared_data.get('checkpoint_to_clusters', {})

        # Add check for distance matrix as well
        if distance_matrix is None or len(distance_matrix) == 0:
            print("[ERROR EnhancedVRP solve] Distance matrix is missing or empty.")
            return {
                'warehouse': warehouse, 'destinations': self.destinations, 'routes': [],
                'total_distance': 0, 'computation_time': time.time() - start_time,
                'error': 'Distance matrix missing or invalid.', 'algorithm_used': algorithm
            }

        if not checkpoints:
            print("[ERROR EnhancedVRP solve] No active routing checkpoints found in prepared data.")
            # Return consistent error structure
            return {
                'warehouse': warehouse, 'destinations': self.destinations, 'routes': [],
                'total_distance': 0, 'computation_time': time.time() - start_time,
                'error': 'No checkpoints available for routing.', 'algorithm_used': algorithm
            }

        num_locations = len(checkpoints) + 1  # +1 for warehouse
        # Map matrix index (1+) to checkpoint data
        # Ensure this uses the 'checkpoints' variable correctly
        checkpoint_indices = {cp_idx: cp for cp_idx, cp in enumerate(checkpoints, 1)}
        # Map checkpoint coord key to matrix index (1+)
        checkpoint_coord_to_idx = {f"{cp['lat']:.6f},{cp['lon']:.6f}": idx for idx, cp in checkpoint_indices.items()}
        # Map matrix index (1+) to set of cluster IDs it serves
        idx_to_cluster_set = {
            idx: set(checkpoint_to_clusters.get(f"{cp_data['lat']:.6f},{cp_data['lon']:.6f}", []))
            for idx, cp_data in checkpoint_indices.items()
        }
        print(f"[DEBUG EnhancedVRP solve] Data prepared: {num_locations} matrix nodes ({len(checkpoints)} checkpoints), {len(required_clusters)} required clusters.")

        # --- Algorithm Selection ---
        effective_algorithm = algorithm
        routes_checkpoint_indices = []
        total_distance_calculated = 0.0
        solver_error = None

        # Map 'two_opt' from UI to 'heuristic' + 2-Opt refinement
        run_two_opt_refinement = (algorithm == 'two_opt')
        if run_two_opt_refinement:
            print("[DEBUG EnhancedVRP solve] Mapping UI algorithm 'two_opt' to 'heuristic' + 2-Opt refinement.")
            effective_algorithm = 'heuristic'

        try:
            if effective_algorithm == 'or_tools':
                if not HAS_ORTOOLS:
                    print("[ERROR EnhancedVRP solve] OR-Tools selected but library not found. Falling back to heuristic.")
                    effective_algorithm = 'heuristic'
                else:
                    try:
                        print("[DEBUG EnhancedVRP solve] Using Google OR-Tools algorithm...")
                        # PASS num_vehicles
                        routes_checkpoint_indices, total_distance_calculated = self._solve_checkpoint_vrp_ortools(
                            num_locations, distance_matrix, required_clusters, checkpoint_indices, checkpoint_to_clusters, idx_to_cluster_set, self.num_vehicles
                        )
                    except Exception as e:
                        print(f"[ERROR EnhancedVRP solve] OR-Tools failed: {e}. Falling back to heuristic.")
                        solver_error = f"OR-Tools failed: {e}"
                        effective_algorithm = 'heuristic'  # Force fallback on error

            # If heuristic is chosen or OR-Tools failed/unavailable
            if effective_algorithm == 'heuristic':
                print(f"[DEBUG EnhancedVRP solve] Using heuristic algorithm (NN-based)...")
                # PASS num_vehicles
                routes_checkpoint_indices, total_distance_calculated = self._solve_checkpoint_vrp_heuristic(
                    num_locations, distance_matrix, required_clusters, checkpoint_indices, idx_to_cluster_set, self.num_vehicles
                )
                # Apply 2-Opt refinement if requested
                if run_two_opt_refinement and not solver_error:  # Don't refine if OR-Tools already failed
                    print(f"[DEBUG EnhancedVRP solve] Applying 2-Opt refinement to heuristic routes...")
                    routes_checkpoint_indices, total_distance_calculated = self._improve_checkpoint_routes_with_two_opt(
                        routes_checkpoint_indices, distance_matrix
                    )
                    effective_algorithm = 'heuristic+2opt'  # Update label

        except Exception as e:
            print(f"[ERROR EnhancedVRP solve] Exception occurred during solving: {e}")
            return {
                'warehouse': warehouse, 'destinations': self.destinations, 'routes': [],
                'total_distance': 0, 'computation_time': time.time() - start_time,
                'error': str(e), 'algorithm_used': effective_algorithm
            }

        # --- Post-processing ---
        print(f"[DEBUG EnhancedVRP solve] Post-processing {len(routes_checkpoint_indices)} routes found by {effective_algorithm}...")
        final_routes = []
        # Get the mapping from matrix index (1+) back to checkpoint data
        checkpoint_indices_map = prepared_data.get('checkpoint_indices', {})
        warehouse_coords = prepared_data.get('warehouse')

        # --- ADD VALIDATION AND CAPTURE MISSING CLUSTERS ---
        # Ensure required_clusters is treated as a set
        required_clusters_list = prepared_data.get('required_clusters', []) # Get the list (or default empty list)
        required_clusters = set(required_clusters_list) # Convert to set

        idx_to_cluster_set = prepared_data.get('idx_to_cluster_set', {})
        covered_clusters = set()
        for route in routes_checkpoint_indices:
            for cp_idx in route:
                covered_clusters.update(idx_to_cluster_set.get(cp_idx, set()))
        missing_clusters = required_clusters - covered_clusters # Now this is set - set
        if missing_clusters:
             print(f"[WARN EnhancedVRP solve] Solution did not cover all required clusters. Missing: {missing_clusters}")
        else:
             print(f"[DEBUG EnhancedVRP solve] All {len(required_clusters)} required clusters covered.")
        # --- END VALIDATION ---

        for route_idx, route_indices in enumerate(routes_checkpoint_indices):
            route_stops = []
            route_path = []  # List of coordinate dicts for this route

            # Start at warehouse
            if warehouse_coords:
                route_path.append({'lat': warehouse_coords['lat'], 'lon': warehouse_coords['lon'], 'type': 'warehouse'})
            else:
                print("[WARN EnhancedVRP solve] Warehouse coordinates missing for path generation.")

            for cp_matrix_index in route_indices:
                checkpoint_data = checkpoint_indices_map.get(cp_matrix_index)
                if checkpoint_data:
                    route_stops.append({
                        'lat': checkpoint_data['lat'],
                        'lon': checkpoint_data['lon'],
                        'clusters_served': checkpoint_data.get('clusters', []),
                        'type': 'checkpoint'  # Mark stop type
                    })
                    route_path.append({
                        'lat': checkpoint_data['lat'],
                        'lon': checkpoint_data['lon'],
                        'type': 'checkpoint',
                        'matrix_idx': cp_matrix_index  # Add the index here
                    })
                else:
                    print(f"[ERROR EnhancedVRP solve] Checkpoint data not found for matrix index: {cp_matrix_index}")

            # End at warehouse
            if warehouse_coords:
                route_path.append({'lat': warehouse_coords['lat'], 'lon': warehouse_coords['lon'], 'type': 'warehouse'})

            # Calculate distance for this specific route using the original matrix
            route_dist = 0
            full_indices_for_dist = [0] + route_indices + [0]  # Use matrix indices
            for k in range(len(full_indices_for_dist) - 1):
                try:
                    route_dist += distance_matrix[full_indices_for_dist[k]][full_indices_for_dist[k + 1]]
                except IndexError:
                    print(f"[ERROR EnhancedVRP solve] IndexError calculating route distance. Indices: {full_indices_for_dist}, Matrix shape: {distance_matrix.shape}")
                    route_dist = float('inf')  # Penalize
                    break

            final_routes.append({
                'stops': route_stops,  # List of checkpoint dicts visited
                'path': route_path,   # List of coordinate dicts (warehouse -> CPs -> warehouse)
                'distance': route_dist
            })

        end_time = time.time()
        print(f"[DEBUG EnhancedVRP solve] Checkpoint VRP ({effective_algorithm}) finished in {end_time - start_time:.4f} seconds. Total distance: {total_distance_calculated:.2f} km")

        return {
            'warehouse': warehouse,
            'destinations': self.destinations,
            'routes': final_routes,
            'total_distance': float(total_distance_calculated),
            'computation_time': float(end_time - start_time),
            'algorithm_used': effective_algorithm,
            'missing_clusters': sorted(list(missing_clusters))  # Add the list of missing cluster IDs
        }

    # MODIFIED: Accept num_vehicles, implement multi-vehicle logic
    def _solve_checkpoint_vrp_heuristic(self, num_locations, distance_matrix, required_clusters, checkpoint_indices, idx_to_cluster_set, num_vehicles):
        """Multi-vehicle Nearest Neighbor heuristic for checkpoint VRP."""
        print(f"[DEBUG EnhancedVRP Heuristic] Starting heuristic calculation for {num_vehicles} vehicles...")
        print(f"[DEBUG] Required clusters to cover: {required_clusters}")
        print(f"[DEBUG] Available checkpoints: {list(checkpoint_indices.keys())}")
        print(f"[DEBUG] Cluster coverage by checkpoint:")
        for cp_idx, clusters in idx_to_cluster_set.items():
            print(f"  - CP #{cp_idx}: covers clusters {clusters}")

        all_routes_indices = []
        total_distance = 0

        unvisited_checkpoints = set(checkpoint_indices.keys())  # Indices 1 to N
        clusters_to_cover = set(required_clusters)

        vehicle_routes = [[] for _ in range(num_vehicles)]
        vehicle_distances = [0.0] * num_vehicles
        vehicle_current_loc = [0] * num_vehicles  # All start at warehouse (index 0)
        vehicle_clusters_covered = [set() for _ in range(num_vehicles)]

        # Greedily assign checkpoints ensuring cluster coverage
        while clusters_to_cover:
            best_assignment = None  # (vehicle_idx, checkpoint_idx, distance)
            min_dist = float('inf')

            # Find the best checkpoint to assign to *any* vehicle
            for v_idx in range(num_vehicles):
                current_loc_idx = vehicle_current_loc[v_idx]
                # Consider only checkpoints that cover remaining clusters or any unvisited if none cover remaining
                relevant_checkpoints = set()
                for cp_idx in unvisited_checkpoints:
                    if idx_to_cluster_set[cp_idx].intersection(clusters_to_cover):
                        relevant_checkpoints.add(cp_idx)

                # If no checkpoints cover remaining clusters, consider all unvisited
                candidates = relevant_checkpoints if relevant_checkpoints else unvisited_checkpoints

                if not candidates:
                    continue  # No more checkpoints for this vehicle to visit

                # Find nearest candidate for this vehicle
                for cp_idx in candidates:
                    dist = distance_matrix[current_loc_idx][cp_idx]
                    if dist < min_dist:
                        min_dist = dist
                        best_assignment = (v_idx, cp_idx, dist)

            if best_assignment:
                v_idx, cp_idx, dist = best_assignment
                print(f"[DEBUG EnhancedVRP Heuristic MultiVehicle] Assigning CP {cp_idx} (covers {idx_to_cluster_set[cp_idx]}) to Vehicle {v_idx+1} (Dist: {dist:.2f})")

                vehicle_routes[v_idx].append(cp_idx)
                vehicle_distances[v_idx] += dist
                vehicle_current_loc[v_idx] = cp_idx
                covered_by_cp = idx_to_cluster_set[cp_idx]
                vehicle_clusters_covered[v_idx].update(covered_by_cp)
                clusters_to_cover.difference_update(covered_by_cp)
                unvisited_checkpoints.remove(cp_idx)
            else:
                # No more valid assignments possible, but clusters might remain
                if clusters_to_cover:
                    print(f"[WARNING EnhancedVRP Heuristic MultiVehicle] Could not cover all clusters. Remaining: {clusters_to_cover}")
                break  # Exit loop

        # Add return-to-warehouse distance for each vehicle
        for v_idx in range(num_vehicles):
            if vehicle_routes[v_idx]:  # Only if the vehicle was used
                return_dist = distance_matrix[vehicle_current_loc[v_idx]][0]
                vehicle_distances[v_idx] += return_dist
                all_routes_indices.append(vehicle_routes[v_idx])  # Add the list of indices
                total_distance += vehicle_distances[v_idx]

        print(f"[DEBUG EnhancedVRP Heuristic] Heuristic finished. Found {len(all_routes_indices)} routes. Total distance: {total_distance:.2f}")
        print(f"[DEBUG] Final routes:")
        for vehicle_idx, route in enumerate(all_routes_indices):
            print(f"  - Vehicle {vehicle_idx+1}: {route}")
            covered_clusters = set()
            for cp_idx in route:
                covered_clusters.update(idx_to_cluster_set.get(cp_idx, set()))
            print(f"    Covers clusters: {covered_clusters}")

        # Return list of lists of indices, and total distance
        return all_routes_indices, total_distance

    # ADDED: 2-Opt refinement for checkpoint routes
    def _improve_checkpoint_routes_with_two_opt(self, routes_indices, distance_matrix):
        """Applies 2-Opt refinement to each checkpoint route."""
        print("[DEBUG EnhancedVRP 2Opt] Starting 2-Opt refinement for checkpoint routes...")
        refined_routes = []
        total_refined_distance = 0

        for route_indices in routes_indices:
            if len(route_indices) < 2:  # Need at least 2 checkpoints for 2-opt swap
                refined_routes.append(route_indices)
                # Recalculate distance for consistency
                dist = 0
                full_indices = [0] + route_indices + [0]
                for i in range(len(full_indices) - 1):
                    dist += distance_matrix[full_indices[i]][full_indices[i + 1]]
                total_refined_distance += dist
                continue

            # Create full route including warehouse for 2-Opt calculation
            # Indices are already 1-based for checkpoints
            full_route = [0] + route_indices + [0]
            current_best_route = list(full_route)  # Copy
            best_distance = self._calculate_checkpoint_route_distance(current_best_route, distance_matrix)

            improved = True
            while improved:
                improved = False
                for i in range(1, len(current_best_route) - 2):  # Don't swap warehouse start/end
                    for j in range(i + 1, len(current_best_route) - 1):
                        # Create new route by reversing segment [i, j]
                        new_route = current_best_route[:i] + current_best_route[i:j+1][::-1] + current_best_route[j+1:]
                        new_distance = self._calculate_checkpoint_route_distance(new_route, distance_matrix)

                        if new_distance < best_distance:
                            current_best_route = new_route
                            best_distance = new_distance
                            improved = True
                            # Restart scan from beginning after improvement
                            break
                    if improved:
                        break

            refined_route_indices = current_best_route[1:-1]  # Remove warehouse indices
            refined_routes.append(refined_route_indices)
            total_refined_distance += best_distance
            print(f"[DEBUG EnhancedVRP 2Opt] Refined route distance: {best_distance:.2f}")

        print(f"[DEBUG EnhancedVRP 2Opt] 2-Opt refinement finished. Total distance: {total_refined_distance:.2f}")
        return refined_routes, total_refined_distance

    # ADDED: Helper for 2-Opt distance calculation
    def _calculate_checkpoint_route_distance(self, route_indices, distance_matrix):
        """Calculates distance for a route given by checkpoint indices (incl. warehouse 0)."""
        distance = 0
        for i in range(len(route_indices) - 1):
            try:
                distance += distance_matrix[route_indices[i]][route_indices[i + 1]]
            except IndexError:
                print(f"[ERROR EnhancedVRP _calc_dist] IndexError. Indices: {route_indices}, Matrix shape: {distance_matrix.shape}")
                return float('inf')  # Penalize invalid routes
        return distance

    # MODIFIED: Accept num_vehicles
    def _solve_checkpoint_vrp_ortools(self, num_locations, distance_matrix, required_clusters, checkpoint_indices, checkpoint_to_clusters, idx_to_cluster_set, num_vehicles):
        """Google OR-Tools implementation for checkpoint VRP (Multi-Vehicle)."""
        if not HAS_ORTOOLS:
            raise ImportError("OR-Tools library not available.")  # Raise error to trigger fallback

        print(f"[DEBUG EnhancedVRP ORTools] Preparing data model for {num_vehicles} vehicles...")
        print(f"[DEBUG] Required clusters to cover: {required_clusters}")
        print(f"[DEBUG] Available checkpoints: {list(checkpoint_indices.keys())}")
        print(f"[DEBUG] Cluster coverage by checkpoint:")
        for cp_idx, clusters in idx_to_cluster_set.items():
            print(f"  - CP #{cp_idx}: covers clusters {clusters}")

        data = {}
        data['distance_matrix'] = distance_matrix.tolist()
        # Use the passed num_vehicles
        data['num_vehicles'] = num_vehicles
        data['depot'] = 0

        manager = pywrapcp.RoutingIndexManager(
            len(data['distance_matrix']),
            data['num_vehicles'],
            data['depot']
        )
        routing = pywrapcp.RoutingModel(manager)

        # Define distance callback (ensure integer distances)
        def distance_callback(from_index, to_index):
            # ... (keep existing callback logic with scaling) ...
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            if 0 <= from_node < len(data['distance_matrix']) and 0 <= to_node < len(data['distance_matrix']):
                return int(data['distance_matrix'][from_node][to_node] * 1000)  # Scale to integer
            else:
                print(f"[ERROR EnhancedVRP ORTools] Invalid node index in distance_callback: from={from_node}, to={to_node}")
                return 999999999  # Large penalty

        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        # --- ADD MAX DISTANCE CONSTRAINT ---
        MAX_ROUTE_DISTANCE_KM = 50 
        MAX_ROUTE_DISTANCE_SCALED = int(MAX_ROUTE_DISTANCE_KM * 1000)
        print(f"[DEBUG EnhancedVRP ORTools] Adding max route distance constraint: {MAX_ROUTE_DISTANCE_KM} km ({MAX_ROUTE_DISTANCE_SCALED} scaled)")
        routing.AddDimension(
            transit_callback_index,
            0,  # slack_max: No waiting time allowed
            MAX_ROUTE_DISTANCE_SCALED,  # capacity: Max distance per vehicle
            True,  # start_cumul_to_zero: Start distance count at 0 for each vehicle
            "DistanceDimension"
        )

        # Add required clusters constraints using AddDisjunction
        print("[DEBUG EnhancedVRP ORTools] Adding cluster visit constraints...")
        # Define a large penalty for skipping a cluster (e.g., equivalent to 1000 km)
        # Adjust this value based on typical route distances and ensure it's large enough
        # to strongly discourage skipping unless necessary.
        # Scaled by 1000 as distances are scaled.
        CLUSTER_SKIP_PENALTY = 10 * 1000  # Penalty in scaled integer units (1000km * 1000)
        routing.SetFixedCostOfAllVehicles(0)

        for cluster_id in required_clusters:
            serving_checkpoints_indices = []
            for idx, cp_data in checkpoint_indices.items():
                # Check if this checkpoint index serves the required cluster
                if cluster_id in idx_to_cluster_set.get(idx, set()):
                    serving_checkpoints_indices.append(idx)

            if serving_checkpoints_indices:
                # Vehicle must visit AT LEAST ONE of the checkpoints serving this cluster
                # Use CLUSTER_SKIP_PENALTY instead of 0 for a soft constraint
                print(f"[DEBUG EnhancedVRP ORTools] Constraint: Must visit one of CP indices {serving_checkpoints_indices} for Cluster {cluster_id} (Penalty for skip: {CLUSTER_SKIP_PENALTY})")
                routing.AddDisjunction(
                    [manager.NodeToIndex(cp_idx) for cp_idx in serving_checkpoints_indices],
                    CLUSTER_SKIP_PENALTY  # Use the penalty here
                )
            else:
                # This case should ideally not happen if prepare_data is correct
                print(f"[WARN EnhancedVRP ORTools] No checkpoints found serving required cluster {cluster_id}. Cannot enforce constraint.")

        # Set search parameters
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        search_parameters.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        )
        search_parameters.time_limit.seconds = 10  # Allow more time for multi-vehicle

        print(f"[DEBUG EnhancedVRP ORTools] Starting solver for {num_vehicles} vehicles...")
        solution = routing.SolveWithParameters(search_parameters)

        if not solution:
            print("[ERROR EnhancedVRP ORTools] Solver failed to find a solution.")
            raise RuntimeError("OR-Tools failed to find a solution for checkpoint VRP")

        print("[DEBUG EnhancedVRP ORTools] Solver finished. Extracting solution...")
        all_routes_indices = []
        total_distance_m = 0  # Use scaled distance from solver

        for vehicle_id in range(data['num_vehicles']):
            index = routing.Start(vehicle_id)
            route_indices = []
            route_distance_m = 0
            while not routing.IsEnd(index):
                node_index = manager.IndexToNode(index)
                if node_index != 0:  # Exclude depot
                    route_indices.append(node_index)
                previous_index = index
                index = solution.Value(routing.NextVar(index))
                route_distance_m += routing.GetArcCostForVehicle(previous_index, index, vehicle_id)

            if route_indices:  # Only add non-empty routes
                print(f"[DEBUG EnhancedVRP ORTools] Vehicle {vehicle_id+1} route: 0 -> {' -> '.join(map(str, route_indices))} -> 0. Distance (scaled): {route_distance_m}")
                all_routes_indices.append(route_indices)
                total_distance_m += route_distance_m
            else:
                print(f"[DEBUG EnhancedVRP ORTools] Vehicle {vehicle_id+1} has an empty route.")

        # Convert total distance back to original units (km)
        total_distance_km = total_distance_m / 1000.0
        print(f"[DEBUG EnhancedVRP ORTools] Extracted {len(all_routes_indices)} non-empty routes. Total distance: {total_distance_km:.2f} km")

        # Return list of lists of indices, and total distance
        return all_routes_indices, total_distance_km

    # Keep _haversine_distance if needed, otherwise remove
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

    def _validate_cluster_coverage(self, routes_checkpoint_indices, idx_to_cluster_set, required_clusters):
        """Validates that all required clusters are covered by the checkpoints in the routes"""
        covered_clusters = set()
        for route in routes_checkpoint_indices:
            for cp_idx in route:
                covered_clusters.update(idx_to_cluster_set.get(cp_idx, set()))
        
        missing_clusters = required_clusters - covered_clusters
        if missing_clusters:
            print(f"[ERROR] Solution fails to cover clusters: {missing_clusters}")
            return False
        
        print(f"[SUCCESS] All {len(required_clusters)} required clusters are covered.")
        return True