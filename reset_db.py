import os
import sqlite3
from utils.db_schema import SCHEMA_SQL

# Define path to database
DB_PATH = os.path.join('static', 'data', 'locations.db')

def reset_database():
    """Completely reset the database by creating fresh tables"""
    # Ensure directory exists
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    # Remove existing database if it exists
    if os.path.exists(DB_PATH):
        print(f"Removing existing database at {DB_PATH}")
        os.remove(DB_PATH)
    
    # Create new database using schema from separate file
    print(f"Creating new database at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    
    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON")
    
    # Execute schema creation script
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()
    
    print("Database created successfully!")

if __name__ == "__main__":
    reset_database()