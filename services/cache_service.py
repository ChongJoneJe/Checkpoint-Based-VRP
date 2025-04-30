import json
import hashlib
import time
import sqlite3
from flask import current_app
import os
from functools import wraps
import threading

class CacheService:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(CacheService, cls).__new__(cls)
                # Initialize cache storage only once
                cls._instance._cache = {}
                cls._instance._expirations = {}
                print("[DEBUG CacheService] Initialized Singleton in-memory cache.")
        return cls._instance

    def get(self, key):
        """Retrieve an item from the cache if it exists and hasn't expired."""
        with self._lock: # Ensure thread safety
            if key in self._cache:
                if key in self._expirations and time.time() > self._expirations[key]:
                    print(f"[DEBUG CacheService] Cache expired for key: {key}")
                    # Item expired, remove it
                    del self._cache[key]
                    del self._expirations[key]
                    return None 
                else:
                    print(f"[DEBUG CacheService] Cache hit for key: {key}")
                    return self._cache[key] # Return cached item
            else:
                print(f"[DEBUG CacheService] Cache miss for key: {key}")
                return None # Indicate cache miss (not found)

    def set(self, key, value, timeout=None):
        """Add an item to the cache with an optional timeout (in seconds)."""
        with self._lock: 
            self._cache[key] = value
            if timeout:
                self._expirations[key] = time.time() + timeout
                print(f"[DEBUG CacheService] Set cache for key: {key} with timeout {timeout}s")
            else:
                # Remove any existing expiration if timeout is None
                if key in self._expirations:
                    del self._expirations[key]
                print(f"[DEBUG CacheService] Set cache for key: {key} with no timeout")

    def delete(self, key):
        """Remove an item from the cache."""
        with self._lock: # Ensure thread safety
            if key in self._cache:
                del self._cache[key]
                if key in self._expirations:
                    del self._expirations[key]
                print(f"[DEBUG CacheService] Deleted cache for key: {key}")
                return True
            return False

    def clear(self):
        """Clear the entire cache."""
        with self._lock: # Ensure thread safety
            self._cache = {}
            self._expirations = {}
            print("[DEBUG CacheService] Cache cleared.")
    
    @staticmethod
    def get_db_connection():
        """Get a connection to the database"""
        db_path = os.path.join(current_app.root_path, 'static', 'data', 'locations.db')
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def get_route_cache(start_coords, end_coords):
        """
        Get cached route between two coordinates
        
        Args:
            start_coords: [lat, lon] of start point
            end_coords: [lat, lon] of end point
            
        Returns:
            dict: Cached route data or None if not found
        """
        # Create cache key from coordinates
        cache_key = f"route:{start_coords[0]:.5f},{start_coords[1]:.5f}:{end_coords[0]:.5f},{end_coords[1]:.5f}"
        
        conn = CacheService.get_db_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT route_data FROM route_cache WHERE cache_key = ?", (cache_key,))
            result = cursor.fetchone()
            
            if result:
                print(f"[CACHE] Route cache hit for {cache_key}")
                return json.loads(result['route_data'])
            else:
                print(f"[CACHE] Route cache miss for {cache_key}")
                return None
        except Exception as e:
            print(f"[CACHE] Error retrieving from route cache: {str(e)}")
            return None
        finally:
            conn.close()
    
    @staticmethod
    def set_route_cache(start_coords, end_coords, route_data):
        """
        Cache route data between two coordinates
        
        Args:
            start_coords: [lat, lon] of start point
            end_coords: [lat, lon] of end point
            route_data: Route data to cache
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Create cache key from coordinates
        cache_key = f"route:{start_coords[0]:.5f},{start_coords[1]:.5f}:{end_coords[0]:.5f},{end_coords[1]:.5f}"
        
        conn = CacheService.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Convert dict to JSON string
            route_json = json.dumps(route_data)
            
            # Check if entry already exists
            cursor.execute("SELECT 1 FROM route_cache WHERE cache_key = ?", (cache_key,))
            if cursor.fetchone():
                cursor.execute("UPDATE route_cache SET route_data = ? WHERE cache_key = ?", 
                              (route_json, cache_key))
            else:
                cursor.execute("INSERT INTO route_cache (cache_key, route_data) VALUES (?, ?)", 
                              (cache_key, route_json))
            
            conn.commit()
            print(f"[CACHE] Route cached for {cache_key}")
            return True
        except Exception as e:
            print(f"[CACHE] Error caching route: {str(e)}")
            return False
        finally:
            conn.close()
    
    @staticmethod
    def get_cluster_cache(params):
        """
        Get cached clustering results for given parameters
        
        Args:
            params: dict of clustering parameters
            
        Returns:
            dict: Cached clustering results or None if not found
        """
        # Create a deterministic cache key from the parameters
        sorted_params = json.dumps(params, sort_keys=True)
        cache_key = f"cluster:{hashlib.md5(sorted_params.encode()).hexdigest()}"
        
        conn = CacheService.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Check if we need to create the table first
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cluster_cache (
                    cache_key TEXT PRIMARY KEY,
                    cluster_data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("SELECT cluster_data FROM cluster_cache WHERE cache_key = ?", (cache_key,))
            result = cursor.fetchone()
            
            if result:
                print(f"[CACHE] Cluster cache hit for {cache_key}")
                return json.loads(result['cluster_data'])
            else:
                print(f"[CACHE] Cluster cache miss for {cache_key}")
                return None
        except Exception as e:
            print(f"[CACHE] Error retrieving from cluster cache: {str(e)}")
            return None
        finally:
            conn.close()
    
    @staticmethod
    def set_cluster_cache(params, cluster_data):
        """
        Cache clustering results for given parameters
        
        Args:
            params: dict of clustering parameters
            cluster_data: Clustering results to cache
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Create a deterministic cache key from the parameters
        sorted_params = json.dumps(params, sort_keys=True)
        cache_key = f"cluster:{hashlib.md5(sorted_params.encode()).hexdigest()}"
        
        conn = CacheService.get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Ensure table exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cluster_cache (
                    cache_key TEXT PRIMARY KEY,
                    cluster_data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Convert dict to JSON string
            cluster_json = json.dumps(cluster_data)
            
            # Check if entry already exists
            cursor.execute("SELECT 1 FROM cluster_cache WHERE cache_key = ?", (cache_key,))
            if cursor.fetchone():
                cursor.execute("UPDATE cluster_cache SET cluster_data = ? WHERE cache_key = ?", 
                              (cluster_json, cache_key))
            else:
                cursor.execute("INSERT INTO cluster_cache (cache_key, cluster_data) VALUES (?, ?)", 
                              (cache_key, cluster_json))
            
            conn.commit()
            print(f"[CACHE] Clusters cached for {cache_key}")
            return True
        except Exception as e:
            print(f"[CACHE] Error caching clusters: {str(e)}")
            return False
        finally:
            conn.close()
    
    @staticmethod
    def clear_cache(cache_type=None, older_than=None):
        """
        Clear cache entries
        
        Args:
            cache_type: 'route', 'cluster', or None for all
            older_than: Clear entries older than this many seconds
            
        Returns:
            int: Number of entries cleared
        """
        conn = CacheService.get_db_connection()
        cursor = conn.cursor()
        
        try:
            if cache_type == 'route':
                if older_than:
                    cursor.execute(
                        "DELETE FROM route_cache WHERE strftime('%s','now') - strftime('%s',created_at) > ?", 
                        (older_than,)
                    )
                else:
                    cursor.execute("DELETE FROM route_cache")
            elif cache_type == 'cluster':
                if older_than:
                    cursor.execute(
                        "DELETE FROM cluster_cache WHERE strftime('%s','now') - strftime('%s',created_at) > ?", 
                        (older_than,)
                    )
                else:
                    cursor.execute("DELETE FROM cluster_cache")
            else:
                # Clear all caches
                if older_than:
                    cursor.execute(
                        "DELETE FROM route_cache WHERE strftime('%s','now') - strftime('%s',created_at) > ?", 
                        (older_than,)
                    )
                    cursor.execute(
                        "DELETE FROM cluster_cache WHERE strftime('%s','now') - strftime('%s',created_at) > ?", 
                        (older_than,)
                    )
                else:
                    cursor.execute("DELETE FROM route_cache")
                    cursor.execute("DELETE FROM cluster_cache")
            
            rows_affected = cursor.rowcount
            conn.commit()
            print(f"[CACHE] Cleared {rows_affected} cache entries")
            return rows_affected
        except Exception as e:
            print(f"[CACHE] Error clearing cache: {str(e)}")
            return 0
        finally:
            conn.close()
    
    @staticmethod
    def cached(cache_time=86400):
        """
        Decorator for caching function results
        
        Args:
            cache_time: Cache validity in seconds (default: 24 hours)
            
        Returns:
            Decorated function
        """
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                # Create a unique key from function name and arguments
                key_parts = [func.__name__]
                key_parts.extend([str(arg) for arg in args])
                key_parts.extend([f"{k}={v}" for k, v in sorted(kwargs.items())])
                
                cache_key = f"func:{hashlib.md5(':'.join(key_parts).encode()).hexdigest()}"
                
                conn = CacheService.get_db_connection()
                cursor = conn.cursor()
                
                try:
                    # Ensure table exists
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS function_cache (
                            cache_key TEXT PRIMARY KEY,
                            result TEXT NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    
                    # Check for existing cache entry
                    cursor.execute(
                        """SELECT result, created_at FROM function_cache 
                           WHERE cache_key = ? AND 
                           strftime('%s','now') - strftime('%s',created_at) < ?""", 
                        (cache_key, cache_time)
                    )
                    
                    result = cursor.fetchone()
                    
                    if result:
                        print(f"[CACHE] Function cache hit for {func.__name__}")
                        return json.loads(result['result'])
                    
                    # Cache miss, execute function
                    function_result = func(*args, **kwargs)
                    
                    # Cache the result
                    result_json = json.dumps(function_result)
                    
                    cursor.execute("SELECT 1 FROM function_cache WHERE cache_key = ?", (cache_key,))
                    if cursor.fetchone():
                        cursor.execute(
                            "UPDATE function_cache SET result = ?, created_at = CURRENT_TIMESTAMP WHERE cache_key = ?", 
                            (result_json, cache_key)
                        )
                    else:
                        cursor.execute(
                            "INSERT INTO function_cache (cache_key, result) VALUES (?, ?)", 
                            (cache_key, result_json)
                        )
                    
                    conn.commit()
                    print(f"[CACHE] Function result cached for {func.__name__}")
                    
                    return function_result
                    
                except Exception as e:
                    print(f"[CACHE] Error in function cache: {str(e)}")
                    # If caching fails, still return the original function result
                    return func(*args, **kwargs)
                finally:
                    conn.close()
            
            return wrapper
        return decorator

    @staticmethod
    def get_cached_matrix(cache_key):
        """
        Retrieve a cached distance matrix
        
        Args:
            cache_key: Unique identifier for the cached matrix
            
        Returns:
            The cached matrix or None if not found
        """
        try:
            from flask import current_app
            import os
            import numpy as np
            import pickle
            
            # Define cache directory
            cache_dir = os.path.join(current_app.root_path, 'static', 'cache', 'matrix')
            cache_file = os.path.join(cache_dir, f"{cache_key}.pkl")
            
            # Check if cache file exists
            if not os.path.exists(cache_file):
                return None
            
            # Load from cache
            with open(cache_file, 'rb') as f:
                matrix = pickle.load(f)
            
            return matrix
            
        except Exception as e:
            print(f"Error retrieving cached matrix: {str(e)}")
            return None

    @staticmethod
    def cache_matrix(cache_key, matrix):
        """
        Cache a distance matrix
        
        Args:
            cache_key: Unique identifier for the matrix
            matrix: The matrix to cache
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            from flask import current_app
            import os
            import pickle
            
            # Define cache directory
            cache_dir = os.path.join(current_app.root_path, 'static', 'cache', 'matrix')
            os.makedirs(cache_dir, exist_ok=True)
            
            cache_file = os.path.join(cache_dir, f"{cache_key}.pkl")
            
            # Save to cache
            with open(cache_file, 'wb') as f:
                pickle.dump(matrix, f)
            
            return True
            
        except Exception as e:
            print(f"Error caching matrix: {str(e)}")
            return False