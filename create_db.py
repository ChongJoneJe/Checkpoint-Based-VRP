import sqlite3
import os

def create_database():
    """Create the database tables manually"""
    # Ensure directory exists
    os.makedirs('static/data', exist_ok=True)
    
    # Connect to database
    conn = sqlite3.connect('static/data/locations.db')
    cursor = conn.cursor()
    
    # Create locations table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS locations (
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
    )
    ''')
    
    # Create intersections table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS intersections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lat REAL NOT NULL,
        lon REAL NOT NULL,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create location_intersections join table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS location_intersections (
        location_id INTEGER,
        intersection_id INTEGER,
        position INTEGER,
        PRIMARY KEY (location_id, intersection_id),
        FOREIGN KEY (location_id) REFERENCES locations(id),
        FOREIGN KEY (intersection_id) REFERENCES intersections(id)
    )
    ''')
    
    # Create clusters table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS clusters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        centroid_lat REAL,
        centroid_lon REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create presets table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS presets (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create preset_locations join table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS preset_locations (
        preset_id TEXT,
        location_id INTEGER,
        is_warehouse BOOLEAN DEFAULT 0,
        PRIMARY KEY (preset_id, location_id),
        FOREIGN KEY (preset_id) REFERENCES presets(id),
        FOREIGN KEY (location_id) REFERENCES locations(id)
    )
    ''')
    
    # Create warehouses table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS warehouses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        preset_id TEXT UNIQUE,
        location_id INTEGER UNIQUE,
        FOREIGN KEY (preset_id) REFERENCES presets(id),
        FOREIGN KEY (location_id) REFERENCES locations(id)
    )
    ''')
    
    # Commit changes
    conn.commit()
    conn.close()
    
    print("Database created successfully!")

if __name__ == "__main__":
    create_database()