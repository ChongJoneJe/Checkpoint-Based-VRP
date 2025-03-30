import sqlite3
import os
from contextlib import contextmanager

# Ensure the database path is consistent
DB_PATH = 'static/data/locations.db'

def ensure_db_exists():
    """Make sure database file exists"""
    os.makedirs('static/data', exist_ok=True)
    if not os.path.exists(DB_PATH):
        # Import and use the reset_db functionality instead of recreating schema here
        from reset_db import reset_database
        reset_database()

@contextmanager
def transaction():
    """Context manager for database transactions"""
    conn = None
    try:
        conn = get_connection()
        yield conn
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if conn:
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
    """Execute a write operation on the database and return lastrowid"""
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        print(f"Executing SQL: {query}")
        print(f"With params: {params}")
        
        cursor.execute(query, params if params else ())
        last_id = cursor.lastrowid
        
        # Make sure to commit!
        conn.commit()
        print(f"Database commit successful. Last row ID: {last_id}")
        
        return last_id
    except Exception as e:
        print(f"Database write error: {str(e)}")
        if conn:
            conn.rollback()
        raise e
    finally:
        if conn:
            conn.close()

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

def execute_transaction(func):
    """Execute a function with multiple database operations in a transaction"""
    with transaction() as conn:
        return func(conn)