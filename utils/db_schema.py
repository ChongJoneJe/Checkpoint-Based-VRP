"""
Database schema definitions for the application
"""

SCHEMA_SQL = """
-- Locations table
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Clusters table (with checkpoint fields)
CREATE TABLE IF NOT EXISTS clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    centroid_lat REAL,
    centroid_lon REAL,
    checkpoint_lat FLOAT,
    checkpoint_lon FLOAT,
    checkpoint_description TEXT,
    road_transition_type TEXT,  -- Store the type of road transition (e.g., 'residential→secondary')
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Presets table
CREATE TABLE IF NOT EXISTS presets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Preset locations link table
CREATE TABLE IF NOT EXISTS preset_locations (
    preset_id TEXT,
    location_id INTEGER,
    is_warehouse BOOLEAN DEFAULT 0,
    PRIMARY KEY (preset_id, location_id),
    FOREIGN KEY (location_id) REFERENCES locations(id),
    FOREIGN KEY (preset_id) REFERENCES presets(id)
);

-- Location clusters link table
CREATE TABLE IF NOT EXISTS location_clusters (
    location_id INTEGER,
    cluster_id INTEGER,
    PRIMARY KEY (location_id, cluster_id),
    FOREIGN KEY (location_id) REFERENCES locations(id),
    FOREIGN KEY (cluster_id) REFERENCES clusters(id)
);

-- Warehouses table
CREATE TABLE IF NOT EXISTS warehouses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    preset_id TEXT,
    location_id INTEGER,
    FOREIGN KEY (preset_id) REFERENCES presets(id),
    FOREIGN KEY (location_id) REFERENCES locations(id)
);

-- Intersections table (for storing road transitions)
CREATE TABLE IF NOT EXISTS intersections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    from_road_type TEXT,
    to_road_type TEXT,
    description TEXT,
    is_checkpoint BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Location intersections link table
CREATE TABLE IF NOT EXISTS location_intersections (
    location_id INTEGER,
    intersection_id INTEGER,
    position INTEGER,
    PRIMARY KEY (location_id, intersection_id),
    FOREIGN KEY (location_id) REFERENCES locations(id),
    FOREIGN KEY (intersection_id) REFERENCES intersections(id)
);

CREATE TABLE IF NOT EXISTS security_checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id INTEGER,
    lat REAL NOT NULL,
    lon REAL NOT NULL,
    from_road_type TEXT,
    to_road_type TEXT,
    confidence REAL DEFAULT 1.0,
    FOREIGN KEY (cluster_id) REFERENCES clusters(id)
);

CREATE TABLE IF NOT EXISTS route_cache (
    cache_key TEXT PRIMARY KEY,
    route_data TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""