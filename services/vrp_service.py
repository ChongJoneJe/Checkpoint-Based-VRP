import time
import os
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

    @staticmethod
    def solve_vrp_with_checkpoints(warehouse, destinations, num_vehicles):
        """Solve a vehicle routing problem using checkpoint optimization"""
        start_time = time.time()
        
        # Initialize VRP solver with checkpoint optimization
        vrp_solver = VehicleRoutingProblem(
            warehouse_coords=warehouse,
            destination_coords=destinations,
            num_vehicles=num_vehicles,
            api_key=os.environ.get('ORS_API_KEY')  # Make sure this is set
        )
        
        # Solve using checkpoint optimization
        solution = vrp_solver.solve_with_checkpoints()
        
        # Calculate computation time
        computation_time = time.time() - start_time
        
        return {
            'routes': solution['routes'],
            'total_distance': solution['total_distance'],
            'uses_checkpoints': True,
            'computation_time': computation_time
        }