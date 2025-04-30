import os
import sqlite3
from utils.db_schema import SCHEMA_SQL

DB_PATH = os.path.join('static', 'data', 'locations.db')

def reset_database():

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if os.path.exists(DB_PATH):
        print(f"Removing existing database at {DB_PATH}")
        os.remove(DB_PATH)
    
    print(f"Creating new database at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    
    conn.execute("PRAGMA foreign_keys = ON")
    
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()
    
    print("Database created successfully!")

if __name__ == "__main__":
    reset_database()