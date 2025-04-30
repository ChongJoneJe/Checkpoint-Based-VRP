import uuid
from models import db
from models.location import Location, Intersection
from models.cluster import Cluster
from models.preset import Preset, Warehouse
from sqlalchemy import desc
from utils.database import execute_read, execute_write  

class PresetService:
    @staticmethod
    def get_all_presets():
        """Get all presets with their locations"""
        presets = Preset.query.order_by(desc(Preset.created_at)).all()
        presets_data = []
        
        for preset in presets:
            # Get all locations for this preset
            locations = db.session.query(Location).\
                join(db.Table('preset_locations')).\
                filter(db.Table('preset_locations').c.preset_id == preset.id).all()
            
            # Get warehouse location
            warehouse = Warehouse.query.filter_by(preset_id=preset.id).first()
            warehouse_coords = None
            
            if warehouse:
                warehouse_location = Location.query.get(warehouse.location_id)
                if warehouse_location:
                    warehouse_coords = [warehouse_location.lat, warehouse_location.lon]
            
            # Get all destination locations (excluding warehouse)
            destinations = []
            for location in locations:
                # Check if this is not the warehouse location
                if not warehouse or location.id != warehouse.location_id:
                    destinations.append([location.lat, location.lon])
            
            presets_data.append({
                'id': preset.id,
                'name': preset.name,
                'warehouse': warehouse_coords,
                'destinations': destinations,
                'created_at': preset.created_at.isoformat() if preset.created_at else None
            })
        
        return presets_data
    
    @staticmethod
    def save_preset(name, warehouse, destinations):
        """Save a new preset with warehouse and destinations"""
        preset_id = str(uuid.uuid4())
        
        with db.session.begin():
            # Create preset
            preset = Preset(id=preset_id, name=name)
            db.session.add(preset)
            
            # Process warehouse
            warehouse_lat, warehouse_lon = warehouse
            warehouse_location = Location.query.filter_by(
                lat=warehouse_lat, lon=warehouse_lon
            ).first()
            
            if not warehouse_location:
                warehouse_location = Location(lat=warehouse_lat, lon=warehouse_lon)
                db.session.add(warehouse_location)
                db.session.flush()
            
            # Create warehouse entry
            db.session.add(Warehouse(
                preset_id=preset_id,
                location_id=warehouse_location.id
            ))
            
            # Link in preset_locations
            db.session.execute(
                db.Table('preset_locations').insert().values(
                    preset_id=preset_id,
                    location_id=warehouse_location.id,
                    is_warehouse=True
                )
            )
            
            # Process destinations
            for dest_lat, dest_lon in destinations:
                dest_location = Location.query.filter_by(lat=dest_lat, lon=dest_lon).first()
                
                if not dest_location:
                    dest_location = Location(lat=dest_lat, lon=dest_lon)
                    db.session.add(dest_location)
                    db.session.flush()
                
                dest_loc_id = dest_location.id
                
                # Add to preset_locations with is_warehouse=0
                execute_write(
                    "INSERT INTO preset_locations (preset_id, location_id, is_warehouse) VALUES (?, ?, 0)",
                    (preset_id, dest_loc_id)
                )
        
        return preset_id
    
    @staticmethod
    def get_preset_by_id(preset_id):
        """Get a specific preset by ID from the database"""
        preset = Preset.query.get(preset_id)
        
        if not preset:
            return None
        
        # Get warehouse location
        warehouse = Warehouse.query.filter_by(preset_id=preset_id).first()
        warehouse_coords = None
        
        if warehouse:
            warehouse_location = Location.query.get(warehouse.location_id)
            if warehouse_location:
                warehouse_coords = [warehouse_location.lat, warehouse_location.lon]
        
        # Get all destinations (excluding warehouse)
        destinations = []
        
        locations = db.session.query(Location).\
            join(db.Table('preset_locations')).\
            filter(db.Table('preset_locations').c.preset_id == preset_id).\
            filter(db.Table('preset_locations').c.is_warehouse == False).all()
            
        for location in locations:
            destinations.append([location.lat, location.lon])
        
        return {
            'id': preset.id,
            'name': preset.name,
            'warehouse': warehouse_coords,
            'destinations': destinations,
            'created_at': preset.created_at.isoformat() if preset.created_at else None
        }
    
    @staticmethod
    def delete_preset(preset_id):
        """Delete a preset by ID from the database"""
        preset = Preset.query.get(preset_id)
        
        if not preset:
            return False
        
        try:
            # Delete warehouse entry
            warehouse = Warehouse.query.filter_by(preset_id=preset_id).first()
            if warehouse:
                db.session.delete(warehouse)
            
            # Delete preset associations from preset_locations table
            db.session.execute(
                db.Table('preset_locations').delete().where(
                    db.Table('preset_locations').c.preset_id == preset_id
                )
            )
            
            # Delete the preset itself
            db.session.delete(preset)
            
            # Commit all changes
            db.session.commit()
            return True
            
        except Exception as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def get_all_presets_basic():
        """Get basic preset information with location counts using raw SQL"""
        try:
            # Use raw SQL query instead of ORM
            presets_query = """
                SELECT p.id, p.name, p.created_at,
                      (SELECT COUNT(*) FROM preset_locations pl 
                       WHERE pl.preset_id = p.id) as location_count
                FROM presets p
                ORDER BY p.created_at DESC
            """
            
            # Execute raw query
            presets_rows = execute_read(presets_query)
            
            # Convert sqlite3.Row objects to dictionaries
            presets_data = []
            for row in presets_rows:
                presets_data.append({
                    'id': row['id'],
                    'name': row['name'],
                    'location_count': row['location_count'],
                    'created_at': row['created_at']
                })
                
            return presets_data
        except Exception as e:
            print(f"Error in get_all_presets_basic: {str(e)}")
            return [] 