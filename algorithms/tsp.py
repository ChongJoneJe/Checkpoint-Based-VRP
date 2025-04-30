import numpy as np
from time import time
from typing import List, Dict, Any, Tuple, Optional

class TravellingSalesmanProblem:
    """
    Solves the Travelling Salesman Problem (TSP) using various algorithms.
    
    This class implements different TSP algorithms including:
    - Nearest Neighbor: Fast but suboptimal greedy approach
    - 2-opt: Local search improvement heuristic
    - Dynamic Programming (for small instances): Exact but O(n^2 * 2^n) complexity
    """
    
    def __init__(self, start_node: int, nodes: List[int], distances: np.ndarray):
        """
        Initialize the TSP solver.
        
        Args:
            start_node: Index of the starting node (typically warehouse)
            nodes: List of node indices to visit
            distances: Distance matrix where distances[i][j] is the distance from node i to j
        """
        self.start_node = start_node
        self.nodes = nodes
        self.distances = distances
        self.n_nodes = len(nodes)
        
        # Verify the nodes are in the distance matrix
        max_node_idx = max(nodes + [start_node])
        if max_node_idx >= len(distances):
            raise ValueError(f"Node index {max_node_idx} exceeds distance matrix dimension {len(distances)}")
    
    def solve_nearest_neighbor(self) -> Dict[str, Any]:
        """
        Solve TSP using the Nearest Neighbor algorithm.
        
        Returns:
            Dictionary with solution details:
            - path: List of node indices in the order they should be visited
            - distance: Total distance of the route
            - computation_time: Time taken to compute the solution
        """
        start_time = time()
        
        # Always start from the start_node (e.g., warehouse)
        current = self.start_node
        unvisited = self.nodes.copy()
        path = [current]
        total_distance = 0
        
        # Visit each node in the nearest neighbor order
        while unvisited:
            # Find nearest unvisited node
            nearest_idx = None
            min_distance = float('inf')
            
            for idx, node in enumerate(unvisited):
                dist = self.distances[current][node]
                if dist < min_distance:
                    min_distance = dist
                    nearest_idx = idx
            
            # Move to the nearest node
            current = unvisited.pop(nearest_idx)
            path.append(current)
            total_distance += min_distance
        
        # Return to start node to complete the cycle
        total_distance += self.distances[current][self.start_node]
        path.append(self.start_node)  # Return to start
        
        computation_time = time() - start_time
        
        return {
            'path': path,
            'distance': total_distance,
            'computation_time': computation_time
        }
    
    def solve_two_opt(self, initial_path: Optional[List[int]] = None) -> Dict[str, Any]:
        """
        Solve TSP using the 2-opt algorithm for local search improvement.
        
        Args:
            initial_path: Optional initial path to improve, otherwise uses nearest neighbor
            
        Returns:
            Dictionary with solution details:
            - path: List of node indices in the order they should be visited
            - distance: Total distance of the route
            - computation_time: Time taken to compute the solution
        """
        start_time = time()
        
        # Get initial path using nearest neighbor if not provided
        if not initial_path:
            nn_solution = self.solve_nearest_neighbor()
            path = nn_solution['path']
            best_distance = nn_solution['distance']
        else:
            path = initial_path
            best_distance = self._calculate_path_distance(path)
        
        improved = True
        while improved:
            improved = False
            
            # Try all possible 2-opt swaps
            for i in range(1, len(path) - 2):
                for j in range(i + 1, len(path) - 1):
                    # Calculate distance change for 2-opt swap
                    old_distance = (self.distances[path[i-1]][path[i]] + 
                                   self.distances[path[j]][path[j+1]])
                    new_distance = (self.distances[path[i-1]][path[j]] + 
                                   self.distances[path[i]][path[j+1]])
                    
                    # If improvement found, perform the swap
                    if new_distance < old_distance:
                        # Reverse the segment between i and j
                        path[i:j+1] = reversed(path[i:j+1])
                        improved = True
                        best_distance = self._calculate_path_distance(path)
                        break
                
                if improved:
                    break
        
        computation_time = time() - start_time
        
        return {
            'path': path,
            'distance': best_distance,
            'computation_time': computation_time
        }
    
    def _calculate_path_distance(self, path: List[int]) -> float:
        """Calculate the total distance of a given path."""
        total = 0
        for i in range(len(path) - 1):
            total += self.distances[path[i]][path[i + 1]]
        return total

    def solve_dp(self, max_nodes: int = 15) -> Dict[str, Any]:
        """
        Solve TSP using dynamic programming (exact but exponential).
        Only works for small instances due to O(n^2 * 2^n) complexity.
        
        Args:
            max_nodes: Maximum number of nodes to allow (safety limit)
            
        Returns:
            Dictionary with solution details:
            - path: List of node indices in the order they should be visited
            - distance: Total distance of the route
            - computation_time: Time taken to compute the solution
        """
        if len(self.nodes) > max_nodes:
            raise ValueError(f"Too many nodes ({len(self.nodes)}) for DP solution. Maximum allowed: {max_nodes}")
        
        start_time = time()
        
        # Remap nodes to 0...n-1 for simpler indexing
        node_to_idx = {self.start_node: 0}
        idx = 1
        for node in self.nodes:
            if node != self.start_node:
                node_to_idx[node] = idx
                idx += 1
        
        idx_to_node = {v: k for k, v in node_to_idx.items()}
        n = len(node_to_idx)
        
        # Create a remapped distance matrix
        dist = np.zeros((n, n))
        for i in range(n):
            for j in range(n):
                dist[i][j] = self.distances[idx_to_node[i]][idx_to_node[j]]

        dp = {}
        
        # Initialize with just the start node
        dp[(1, 0)] = 0 
        
        # Fill DP table for all subsets of nodes
        for mask in range(2, 1 << n):
            if not (mask & 1):
                continue
                
            for i in range(1, n):
                # Skip if current node i is not in the subset
                if not (mask & (1 << i)):
                    continue
                
                # Previous mask without node i
                prev_mask = mask ^ (1 << i)
                
                # Initialize min distance as infinity
                dp.setdefault((mask, i), float('inf'))
                
                # Try all possible previous nodes
                for j in range(n):
                    if (j == i) or not (prev_mask & (1 << j)):
                        continue
                        
                    dp[(mask, i)] = min(
                        dp[(mask, i)],
                        dp.get((prev_mask, j), float('inf')) + dist[j][i]
                    )
        
        # Find optimal distance for returning to start node
        final_mask = (1 << n) - 1  # All nodes visited
        best_distance = float('inf')
        
        for i in range(1, n):
            if dp.get((final_mask, i), float('inf')) + dist[i][0] < best_distance:
                best_distance = dp.get((final_mask, i), float('inf')) + dist[i][0]
        
        # Reconstruct the path
        path = [0]  # Start with node 0
        mask = final_mask
        pos = None
        
        # Find the last node before returning to start
        for i in range(1, n):
            if dp.get((final_mask, i), float('inf')) + dist[i][0] == best_distance:
                pos = i
                break
        
        # Reconstruct path backwards
        while pos != 0:
            path.append(pos)
            new_mask = mask ^ (1 << pos)
            
            # Find the previous node
            for i in range(n):
                if (i != pos) and (mask & (1 << i)) and \
                   dp.get((new_mask, i), float('inf')) + dist[i][pos] == dp.get((mask, pos), float('inf')):
                    pos = i
                    mask = new_mask
                    break
        
        # Convert path back to original node indices
        original_path = [idx_to_node[i] for i in reversed(path)]
        original_path.append(idx_to_node[0])  # Return to start
        
        computation_time = time() - start_time
        
        return {
            'path': original_path,
            'distance': best_distance,
            'computation_time': computation_time
        }