import numpy as np
import openrouteservice
from openrouteservice.distance_matrix import distance_matrix
import os
import random
import math
from config import DEFAULT_VEHICLE

class VehicleRoutingProblem:
    """
    Vehicle Routing Problem solver that routes vehicles from a warehouse to multiple destinations
    and back to the warehouse, optimizing for distance.
    """
    
    def __init__(self, warehouse_coords, destination_coords, num_vehicles=1, api_key=None):
        """
        Initialize the VRP solver
        
        Args:
            warehouse_coords (list): [lat, lon] of the warehouse
            destination_coords (list): List of [lat, lon] coordinates for destinations
            num_vehicles (int): Number of vehicles available
            api_key (str): OpenRouteService API key (optional)
        """
        self.warehouse = warehouse_coords
        self.destinations = destination_coords
        self.num_vehicles = num_vehicles
        self.api_key = api_key or os.environ.get('ORS_API_KEY')
        self.client = None
        
        # Create distance matrix
        self.distance_matrix = self._calculate_distance_matrix()
    
    def _calculate_distance_matrix(self):
        """
        Calculate the distance matrix between all points using either API or Euclidean distance
        
        Returns:
            numpy.ndarray: Distance matrix with warehouse as first point
        """
        # If API key is available, use OpenRouteService for real routes
        if self.api_key:
            try:
                client = openrouteservice.Client(key=self.api_key)
                
                # Combine warehouse and destinations
                all_coords = [self.warehouse] + self.destinations
                
                # Format for ORS (lon, lat)
                ors_coords = [[point[1], point[0]] for point in all_coords]
                
                # Request distance matrix
                matrix = client.distance_matrix(
                    locations=ors_coords,
                    profile='driving-car',
                    metrics=['distance'],
                    units='km'
                )
                
                # Convert to numpy array and return
                return np.array(matrix['distances'])
                
            except Exception as e:
                print(f"OpenRouteService API error: {str(e)}")
                print("Falling back to Euclidean distance")
        
        # Fall back to Euclidean distance calculation
        all_coords = [self.warehouse] + self.destinations
        n = len(all_coords)
        matrix = np.zeros((n, n))
        
        for i in range(n):
            for j in range(n):
                if i != j:
                    lat1, lon1 = all_coords[i]
                    lat2, lon2 = all_coords[j]
                    matrix[i, j] = self._haversine_distance(lat1, lon1, lat2, lon2)
        
        return matrix
    
    def _haversine_distance(self, lat1, lon1, lat2, lon2):
        """
        Calculate the Haversine distance between two points in kilometers
        """
        R = 6371  # Earth radius in km
        
        # Convert to radians
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        return R * c  # Distance in kilometers
    
    def solve(self, algorithm="nearest_neighbor"):
        """
        Solve the VRP problem using the specified algorithm
        
        Args:
            algorithm (str): The algorithm to use ("nearest_neighbor", "two_opt", or "checkpoints")
            
        Returns:
            dict: Solution containing routes and total distance
        """
        if algorithm == "nearest_neighbor":
            return self._solve_nearest_neighbor()
        elif algorithm == "two_opt":
            nn_solution = self._solve_nearest_neighbor()
            return self._improve_with_two_opt(nn_solution)
        elif algorithm == "checkpoints":
            return self.solve_with_checkpoints()
        else:
            raise ValueError(f"Unknown algorithm: {algorithm}")
    
    def _solve_nearest_neighbor(self):
        """
        Solve using the Nearest Neighbor algorithm
        
        Returns:
            dict: Solution with routes and total distance
        """
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
        
        return {"routes": routes, "total_distance": total_distance}
    
    def _improve_with_two_opt(self, initial_solution):
        """
        Improve a solution using 2-opt local search
        
        Args:
            initial_solution (dict): Initial solution to improve
            
        Returns:
            dict: Improved solution
        """
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
        
        return improved_solution
    
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
    
    def solve_with_checkpoints(self):
        """
        Optimized VRP solver using security checkpoints to minimize route calculations
        """
        # Get clusters and their checkpoints from database
        clusters_with_checkpoints = self._get_clusters_with_checkpoints()
        
        # Group destinations by cluster
        destinations_by_cluster = self._group_destinations_by_cluster()
        
        # Calculate only necessary routes (warehouse→checkpoint, checkpoint→destinations)
        optimized_routes = {}
        
        # 1. Calculate warehouse→checkpoint routes (once per cluster)
        for cluster_id, checkpoint in clusters_with_checkpoints.items():
            # Cache key for route
            cache_key = f"wh_to_cp_{cluster_id}"
            
            # Get from cache or calculate
            if cache_key in self._route_cache:
                route = self._route_cache[cache_key]
            else:
                route = self._calculate_route(
                    self.warehouse[0], self.warehouse[1],
                    checkpoint['lat'], checkpoint['lon']
                )
                self._route_cache[cache_key] = route
            
            # Store route
            optimized_routes[cluster_id] = {
                'warehouse_to_checkpoint': route,
                'checkpoint': checkpoint,
                'destinations': []
            }
        
        # 2. Calculate checkpoint→destination routes
        for cluster_id, destinations in destinations_by_cluster.items():
            if cluster_id not in clusters_with_checkpoints:
                continue
                
            checkpoint = clusters_with_checkpoints[cluster_id]
            
            for i, dest in enumerate(destinations):
                # Cache key for route
                cache_key = f"cp_{cluster_id}_to_dest_{i}"
                
                # Get from cache or calculate
                if cache_key in self._route_cache:
                    route = self._route_cache[cache_key]
                else:
                    route = self._calculate_route(
                        checkpoint['lat'], checkpoint['lon'],
                        dest[0], dest[1]
                    )
                    self._route_cache[cache_key] = route
                
                # Add to optimized routes
                optimized_routes[cluster_id]['destinations'].append({
                    'index': i,
                    'coords': dest,
                    'route': route
                })
        
        # 3. Solve the VRP within each cluster
        solution = self._solve_with_checkpoints(optimized_routes)
        
        return solution
    
    def calculate_routes_through_checkpoints(self, warehouse, checkpoints, destinations):
        """
        Calculate optimized routes through security checkpoints
        
        Args:
            warehouse: [lat, lon] of warehouse
            checkpoints: Dict of {cluster_id: checkpoint_data}
            destinations: Dict of {cluster_id: list of [lat, lon] destinations}
            
        Returns:
            dict: Route information optimized through checkpoints
        """
        if not self.client:
            self.client = openrouteservice.Client(key=self.api_key)
        
        route_data = {}
        
        # Initialize route cache for efficiency
        if not hasattr(self, '_route_cache'):
            self._route_cache = {}
        
        # For each cluster, calculate warehouse→checkpoint→destinations→checkpoint→warehouse
        for cluster_id, checkpoint in checkpoints.items():
            if cluster_id not in destinations:
                continue
                
            # Step 1: Calculate warehouse to checkpoint (just once per cluster)
            wh_to_cp_key = f"{warehouse[0]:.5f},{warehouse[1]:.5f}|{checkpoint['lat']:.5f},{checkpoint['lon']:.5f}"
            
            if wh_to_cp_key in self._route_cache:
                wh_to_cp_route = self._route_cache[wh_to_cp_key]
            else:
                try:
                    wh_to_cp_route = self.client.directions(
                        coordinates=[[warehouse[1], warehouse[0]], [checkpoint['lon'], checkpoint['lat']]],
                        profile='driving-car',
                        format='geojson'
                    )
                    self._route_cache[wh_to_cp_key] = wh_to_cp_route
                except Exception as e:
                    print(f"Error calculating route warehouse→checkpoint: {str(e)}")
                    wh_to_cp_route = None
            
            # Step 2: Calculate routes from checkpoint to each destination
            cp_to_dests = []
            
            for dest in destinations[cluster_id]:
                cp_to_dest_key = f"{checkpoint['lat']:.5f},{checkpoint['lon']:.5f}|{dest[0]:.5f},{dest[1]:.5f}"
                
                if cp_to_dest_key in self._route_cache:
                    cp_to_dest_route = self._route_cache[cp_to_dest_key]
                else:
                    try:
                        cp_to_dest_route = self.client.directions(
                            coordinates=[[checkpoint['lon'], checkpoint['lat']], [dest[1], dest[0]]],
                            profile='driving-car',
                            format='geojson'
                        )
                        self._route_cache[cp_to_dest_key] = cp_to_dest_route
                    except Exception as e:
                        print(f"Error calculating route checkpoint→destination: {str(e)}")
                        cp_to_dest_route = None
                
                cp_to_dests.append({
                    'destination': dest,
                    'route': cp_to_dest_route
                })
            
            # Store all routes for this cluster
            route_data[cluster_id] = {
                'checkpoint': checkpoint,
                'warehouse_to_checkpoint': wh_to_cp_route,
                'checkpoint_to_destinations': cp_to_dests
            }
        
        return route_data