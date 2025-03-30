import sqlite3
import os
from contextlib import contextmanager

# Ensure this path matches the one in app.py's SQLALCHEMY_DATABASE_URI
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'data', 'locations.db'))

def ensure_db_exists():
    """Make sure database file exists"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if not os.path.exists(DB_PATH):
        # Import and use the reset_db functionality instead of recreating schema here
        from reset_db import reset_database
        reset_database()

def get_db_connection():
    """Get a database connection with foreign keys enabled"""
    # Ensure directory exists
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

@contextmanager
def transaction():
    """Context manager for database transactions"""
    conn = None
    try:
        conn = get_db_connection()
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
        conn = get_db_connection()
        yield conn
    finally:
        if conn:
            conn.close()

def execute_write(query, params=None):
    """Execute a write query and return last row id"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

def execute_read(query, params=None, one=False):
    """Execute a read query and return results"""
    conn = get_db_connection()
    try:
        if params:
            results = conn.execute(query, params).fetchall() if not one else conn.execute(query, params).fetchone()
        else:
            results = conn.execute(query).fetchall() if not one else conn.execute(query).fetchone()
        return results
    finally:
        conn.close()

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