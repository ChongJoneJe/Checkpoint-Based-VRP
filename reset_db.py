import os
import sqlite3
import shutil

# Define path to database
DB_PATH = 'static/data/locations.db'

def reset_database():
    """Completely reset the database by creating fresh tables"""
    # Ensure directory exists
    os.makedirs('static/data', exist_ok=True)
    
    # Delete existing database if it exists
    if os.path.exists(DB_PATH):
        print(f"Removing existing database: {DB_PATH}")
        try:
            os.remove(DB_PATH)
        except PermissionError:
            print("Permission error - will try to backup and recreate")
            # Try backing up and then deleting
            shutil.copy2(DB_PATH, f"{DB_PATH}.bak")
            os.remove(DB_PATH)
    
    # Create new database
    print("Creating new database...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create tables
    cursor.executescript('''
    -- Locations table
    CREATE TABLE locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lat REAL NOT NULL,
        lon REAL NOT NULL,
        street TEXT,
        neighborhood TEXT,
        town TEXT, 
        city TEXT,
        postcode TEXT,
        country TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        cluster_id INTEGER,
        FOREIGN KEY (cluster_id) REFERENCES clusters(id)
    );
    
    -- Clusters table
    CREATE TABLE clusters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        centroid_lat REAL,
        centroid_lon REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    -- Intersections table
    CREATE TABLE intersections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lat REAL NOT NULL,
        lon REAL NOT NULL,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    -- Location-Intersection join table
    CREATE TABLE location_intersections (
        location_id INTEGER,
        intersection_id INTEGER,
        position INTEGER NOT NULL,
        PRIMARY KEY (location_id, intersection_id),
        FOREIGN KEY (location_id) REFERENCES locations(id),
        FOREIGN KEY (intersection_id) REFERENCES intersections(id)
    );
    
    -- Presets table
    CREATE TABLE presets (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    -- Preset-Location join table
    CREATE TABLE preset_locations (
        preset_id TEXT,
        location_id INTEGER,
        is_warehouse BOOLEAN DEFAULT 0,
        PRIMARY KEY (preset_id, location_id),
        FOREIGN KEY (preset_id) REFERENCES presets(id),
        FOREIGN KEY (location_id) REFERENCES locations(id)
    );
    
    -- Warehouses table
    CREATE TABLE warehouses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        preset_id TEXT UNIQUE,
        location_id INTEGER UNIQUE,
        FOREIGN KEY (preset_id) REFERENCES presets(id),
        FOREIGN KEY (location_id) REFERENCES locations(id)
    );
    
    -- Set pragmas for better performance
    PRAGMA journal_mode = WAL;
    PRAGMA synchronous = NORMAL;
    PRAGMA foreign_keys = ON;
    ''')
    
    conn.commit()
    conn.close()
    
    print("Database created successfully!")

if __name__ == "__main__":
    reset_database()