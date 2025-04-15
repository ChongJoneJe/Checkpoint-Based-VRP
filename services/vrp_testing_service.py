import os
import sqlite3
import json
import traceback
from datetime import datetime
from flask import current_app
import numpy as np
from utils.json_helpers import NumpyEncoder, sanitize_for_json

class VRPTestingService:
    """Service for VRP testing functionality"""
    
    @staticmethod
    def get_snapshots():
        """Get all available database snapshots"""
        snapshot_dir = os.path.join(current_app.root_path, "vrp_test_data")
        os.makedirs(snapshot_dir, exist_ok=True)
        
        snapshots = []
        
        # List all .sqlite files in the directory
        for filename in os.listdir(snapshot_dir):
            if filename.endswith('.sqlite'):
                file_path = os.path.join(snapshot_dir, filename)
                
                # Get file creation time
                created_at = datetime.fromtimestamp(os.path.getctime(file_path)).strftime('%Y-%m-%d %H:%M:%S')
                
                # Get stats from the snapshot
                stats = VRPTestingService.get_snapshot_stats(file_path)
                
                snapshots.append({
                    'id': filename,
                    'path': file_path,
                    'created_at': created_at,
                    'stats': stats
                })
        
        # Sort snapshots by creation time (newest first)
        return sorted(snapshots, key=lambda x: x['created_at'], reverse=True)
    
    @staticmethod
    def get_snapshot_stats(db_path):
        """Get statistics about a database snapshot"""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            stats = {}
            
            # Get counts for key tables
            table_names = ['locations', 'clusters', 'security_checkpoints']
            for table in table_names:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    stats[table] = count
                except:
                    stats[table] = 0
            
            conn.close()
            return stats
        except Exception as e:
            return {}
    
    @staticmethod
    def delete_snapshot(snapshot_id):
        """Delete a database snapshot"""
        # Validate snapshot ID (prevent directory traversal)
        if '..' in snapshot_id or '/' in snapshot_id or '\\' in snapshot_id:
            return False, "Invalid snapshot ID"
        
        snapshot_path = os.path.join(current_app.root_path, "vrp_test_data", snapshot_id)
        
        if not os.path.exists(snapshot_path) or not snapshot_id.endswith('.sqlite'):
            return False, "Snapshot not found"
        
        # Delete the snapshot file
        try:
            os.remove(snapshot_path)
            return True, "Snapshot deleted successfully"
        except Exception as e:
            traceback.print_exc()
            return False, f"Error deleting snapshot: {str(e)}"
    
    @staticmethod
    def get_snapshot_presets(snapshot_id):
        """Get presets from a specific snapshot"""
        # Validate snapshot ID
        if '..' in snapshot_id or '/' in snapshot_id or '\\' in snapshot_id:
            return None, "Invalid snapshot ID"
        
        snapshot_path = os.path.join(current_app.root_path, "vrp_test_data", snapshot_id)
        
        if not os.path.exists(snapshot_path):
            return None, "Snapshot not found"
        
        try:
            # Connect to the snapshot database
            conn = sqlite3.connect(snapshot_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get all presets
            presets = []
            cursor.execute("""
                SELECT p.id, p.name, COUNT(pl.location_id) as location_count
                FROM presets p
                LEFT JOIN preset_locations pl ON p.id = pl.preset_id
                WHERE pl.is_warehouse = 0
                GROUP BY p.id
                ORDER BY p.name
            """)
            
            for row in cursor.fetchall():
                presets.append({
                    'id': row['id'],
                    'name': row['name'],
                    'location_count': row['location_count']
                })
            
            conn.close()
            
            return presets, None
        except Exception as e:
            traceback.print_exc()
            return None, f"Error getting presets: {str(e)}"
    
    @staticmethod
    def get_presets_from_snapshot(snapshot_path):
        """Get all presets from a snapshot database"""
        try:
            # Connect to the snapshot database
            conn = sqlite3.connect(snapshot_path)
            conn.row_factory = sqlite3.Row
            
            # Get all presets
            presets = []
            for row in conn.execute("SELECT id, name, created_at FROM presets ORDER BY created_at DESC"):
                presets.append({
                    'id': row['id'],
                    'name': row['name'],
                    'created_at': row['created_at']
                })
            
            conn.close()
            return presets
        except Exception as e:
            traceback.print_exc()
            return []
    
    @staticmethod
    def get_preset_from_snapshot(db_path, preset_id):
        """Get preset data from a snapshot database"""
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get warehouse
            warehouse_row = cursor.execute("""
                SELECT l.lat, l.lon, l.street, l.development, l.neighborhood
                FROM locations l
                JOIN preset_locations pl ON l.id = pl.location_id
                WHERE pl.preset_id = ? AND pl.is_warehouse = 1
            """, (preset_id,)).fetchone()
            
            if not warehouse_row:
                return None
            
            warehouse = [
                float(warehouse_row['lat']), 
                float(warehouse_row['lon'])
            ]
            
            # Get destinations
            destinations = []
            for row in cursor.execute("""
                SELECT l.id, l.lat, l.lon, l.street, l.development, l.neighborhood
                FROM locations l
                JOIN preset_locations pl ON l.id = pl.location_id
                WHERE pl.preset_id = ? AND pl.is_warehouse = 0
            """, (preset_id,)):
                destinations.append([
                    float(row['lat']),
                    float(row['lon'])
                ])
            
            conn.close()
            
            return {
                'warehouse': warehouse,
                'destinations': destinations
            }
        except Exception as e:
            traceback.print_exc()
            return None
    
    @staticmethod
    def save_test_result(result):
        """Save a test result to the database"""
        try:
            # Create results database if it doesn't exist
            db_path = os.path.join(current_app.root_path, 'static', 'data', 'vrp_tests.db')
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Check for test_type column
            cursor.execute("PRAGMA table_info(vrp_test_results)")
            columns = [col[1] for col in cursor.fetchall()]
            
            # Recreate table if test_type column is missing
            if 'test_type' not in columns and columns:
                cursor.execute("CREATE TABLE IF NOT EXISTS temp_vrp_results AS SELECT * FROM vrp_test_results")
                cursor.execute("DROP TABLE vrp_test_results")
                
            # Create table with updated schema
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS vrp_test_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_id TEXT,
                    preset_id TEXT,
                    algorithm TEXT,
                    num_vehicles INTEGER,
                    test_type TEXT,
                    total_distance REAL,
                    computation_time REAL,
                    result_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
                
            # Extract test_info from the result dictionary
            test_info = result.get('test_info', {})
            
            # Insert test result
            cursor.execute("""
                INSERT INTO vrp_test_results (
                    snapshot_id, preset_id, algorithm, num_vehicles,
                    test_type, total_distance, computation_time, result_data
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                test_info.get('snapshot_id'),
                test_info.get('preset_id'),
                test_info.get('algorithm'),
                test_info.get('num_vehicles'),
                test_info.get('test_type', 'static'),
                result.get('total_distance'),
                result.get('execution_time_ms', result.get('computation_time')), 
                json.dumps(result, cls=NumpyEncoder)
            ))
            
            test_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return test_id
        except Exception as e:
            traceback.print_exc()
            return None
    
    @staticmethod
    def get_test_history(limit=50):
        """Retrieve recent test history"""
        try:
            db_path = os.path.join(current_app.root_path, 'static', 'data', 'vrp_tests.db')
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, snapshot_id, preset_id, algorithm, num_vehicles, test_type,
                       total_distance, computation_time, result_data, created_at
                FROM vrp_test_results
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))

            tests_raw = cursor.fetchall()
            conn.close()

            tests = []
            for row in tests_raw:
                test_dict = dict(row)
                try:
                    # Attempt to parse result_data to get test_info if columns are missing
                    result_data = json.loads(test_dict.get('result_data', '{}'))
                    test_info = result_data.get('test_info', {})

                    # Populate top-level fields from test_info if they are null/missing in the main row
                    # (Handles older data before schema change and ensures consistency)
                    test_dict['algorithm'] = test_dict.get('algorithm') or test_info.get('algorithm')
                    test_dict['num_vehicles'] = test_dict.get('num_vehicles') or test_info.get('num_vehicles')
                    test_dict['test_type'] = test_dict.get('test_type') or test_info.get('test_type')
                    test_dict['total_distance'] = test_dict.get('total_distance') # Keep main value if exists
                    test_dict['computation_time'] = test_dict.get('computation_time') # Keep main value if exists

                    # Ensure test_info itself is included for the frontend
                    test_dict['test_info'] = test_info
                    # Remove raw result_data to avoid sending large JSON unless needed
                    # test_dict.pop('result_data', None)

                except json.JSONDecodeError:
                    test_dict['test_info'] = {} # Add empty dict if parsing fails
                except Exception as parse_error:
                     print(f"Error processing test history row {test_dict.get('id')}: {parse_error}")
                     test_dict['test_info'] = {}

                tests.append(test_dict)

            return tests
        except Exception as e:
            traceback.print_exc()
            return []
    
    @staticmethod
    def get_test_result(test_id):
        """Get a specific test result"""
        try:
            db_path = os.path.join(current_app.root_path, 'static', 'data', 'vrp_tests.db')
            
            if not os.path.exists(db_path):
                return None
            
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get test result
            row = cursor.execute("""
                SELECT result_data FROM vrp_test_results
                WHERE id = ?
            """, (test_id,)).fetchone()
            
            if not row:
                return None
            
            result = json.loads(row['result_data'])
            
            return result
        except Exception as e:
            traceback.print_exc()
            return None
    
    @staticmethod
    def compare_test_results(test_ids):
        """Compare multiple test results"""
        try:
            if not test_ids:
                return None
                
            db_path = os.path.join(current_app.root_path, 'static', 'data', 'vrp_tests.db')
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            results = []
            for test_id in test_ids:
                row = cursor.execute("""
                    SELECT result_data FROM vrp_test_results
                    WHERE id = ?
                """, (test_id,)).fetchone()
                
                if row:
                    result_data = json.loads(row['result_data'])
                    result_data['id'] = test_id
                    results.append(result_data)
            
            conn.close()
            
            if not results:
                return None
            
            # Prepare comparison data
            comparison = {
                'tests': results,
                'metrics': {
                    'distance': [r['total_distance'] for r in results],
                    'computation_time': [r['computation_time'] for r in results],
                    'is_dynamic': [r.get('test_info', {}).get('is_dynamic_test', False) for r in results],
                    'locations_count': [len(r.get('destinations', [])) for r in results],
                    'dynamic_locations_count': [r.get('test_info', {}).get('dynamic_locations_count', 0) for r in results],
                    'avg_route_length': [sum(route['distance'] for route in r['routes'])/len(r['routes']) if r['routes'] else 0 for r in results],
                    'max_route_length': [max((route['distance'] for route in r['routes']), default=0) for r in results]
                }
            }
            
            return comparison
        except Exception as e:
            traceback.print_exc()
            return None
    
    @staticmethod
    def delete_test(test_id):
        """
        Delete a test from the history
        
        Args:
            test_id: ID of the test to delete
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # FIX: Use the correct database path
            db_path = os.path.join(current_app.root_path, 'static', 'data', 'vrp_tests.db')
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # FIX: Delete from the correct table
            cursor.execute("DELETE FROM vrp_test_results WHERE id = ?", (test_id,))
            
            # Check if anything was deleted
            rows_deleted = cursor.rowcount
            
            conn.commit()
            conn.close()
            
            return rows_deleted > 0
        except Exception as e:
            print(f"Error deleting test: {str(e)}")
            traceback.print_exc() # Add traceback for better debugging
            return False