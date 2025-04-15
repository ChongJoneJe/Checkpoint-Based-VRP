import sqlite3
import os
import shutil
from datetime import datetime

def create_database_snapshot():
    """Create a snapshot of the current database for VRP testing"""
    # Define source and destination paths
    source_db = os.path.join("static", "data", "locations.db")  # Fixed path
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_dir = "vrp_test_data"
    snapshot_name = f"db_snapshot_{timestamp}.sqlite"
    snapshot_path = os.path.join(snapshot_dir, snapshot_name)
    
    # Create directory if it doesn't exist
    os.makedirs(snapshot_dir, exist_ok=True)
    
    # Check if source DB exists
    if not os.path.exists(source_db):
        print(f"ERROR: Source database not found at {source_db}")
        return None
    
    # Copy the database file
    try:
        shutil.copy2(source_db, snapshot_path)
        print(f"Database snapshot created at: {snapshot_path}")
    except Exception as e:
        print(f"ERROR: Failed to create snapshot: {str(e)}")
        return None
    
    # Verify the snapshot
    try:
        conn = sqlite3.connect(snapshot_path)
        cursor = conn.cursor()
        
        # Check for required tables
        tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = [t[0] for t in tables]
        
        required_tables = ['locations', 'clusters', 'security_checkpoints']
        missing_tables = [t for t in required_tables if t not in table_names]
        
        if missing_tables:
            print(f"WARNING: Missing tables in snapshot: {missing_tables}")
        
        # Get some stats from the snapshot
        stats = {}
        for table in table_names:
            try:
                count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                stats[table] = count
            except:
                pass
        
        print(f"Snapshot stats: {stats}")
        conn.close()
        
        # Return snapshot info for API use
        return {
            "id": snapshot_name,
            "path": snapshot_path,
            "created_at": timestamp,
            "stats": stats
        }
    
    except Exception as e:
        print(f"ERROR: Failed to verify snapshot: {str(e)}")
        return None

if __name__ == "__main__":
    # Allow running as a standalone script
    result = create_database_snapshot()
    if result:
        print("Snapshot creation successful")
    else:
        print("Snapshot creation failed")