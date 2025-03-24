import sqlite3
import os
from contextlib import contextmanager

# Ensure the database path is consistent
DB_PATH = 'static/data/locations.db'

def ensure_db_exists():
    """Make sure database file exists"""
    os.makedirs('static/data', exist_ok=True)
    if not os.path.exists(DB_PATH):
        # Initialize empty database with schema
        conn = get_connection()
        conn.close()

@contextmanager
def get_db():
    """Context manager for database operations"""
    conn = None
    try:
        conn = get_connection()
        yield conn
    finally:
        if conn:
            conn.close()

def get_connection():
    """Get a SQLite connection with proper settings"""
    # Create connection with long timeout
    conn = sqlite3.connect(DB_PATH, timeout=60)
    
    # Configure connection
    conn.row_factory = sqlite3.Row  # Return rows as dict-like objects
    
    # Set pragmas for better performance
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA cache_size = 10000")
    conn.execute("PRAGMA foreign_keys = ON")
    
    return conn

def execute_write(query, params=None):
    """Execute write operation with proper transaction handling"""
    with get_db() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN IMMEDIATE")  # Get exclusive lock immediately
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            conn.rollback()
            raise e

def execute_read(query, params=None, one=False):
    """Execute read operation"""
    with get_db() as conn:
        cursor = conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        if one:
            return cursor.fetchone()
        return cursor.fetchall()

def execute_many(query, params_list):
    """Execute many operations in one transaction"""
    with get_db() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN IMMEDIATE")
            cursor.executemany(query, params_list)
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e