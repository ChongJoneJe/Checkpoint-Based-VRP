import time
from algorithms.vrp import VehicleRoutingProblem

class VRPService:
    @staticmethod
    def solve_vrp(warehouse, destinations, num_vehicles, algorithm="nearest_neighbor"):
        """Solve a vehicle routing problem"""
        start_time = time.time()
        
        # Initialize VRP solver
        vrp_solver = VehicleRoutingProblem(
            warehouse_coords=warehouse,
            destination_coords=destinations,
            num_vehicles=num_vehicles
        )
        
        # Solve the problem
        solution = vrp_solver.solve(algorithm=algorithm)
        
        # Calculate computation time
        computation_time = time.time() - start_time
        
        return {
            'routes': solution['routes'],
            'total_distance': solution['total_distance'],
            'computation_time': computation_time
        }