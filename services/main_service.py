from models import db
from models.location import Location
from models.cluster import Cluster
from models.preset import Preset, Warehouse
from sqlalchemy import desc

class MainService:
    @staticmethod
    def get_default_map_center():
        """Get default map center coordinates, preferring the most recent warehouse"""
        # Default coordinates (Malaysia)
        center_lat = 3.127993
        center_lng = 101.466972
        
        try:
            # Find the most recent preset
            latest_preset = Preset.query.order_by(desc(Preset.created_at)).first()
            
            if latest_preset:
                # Try to get warehouse for this preset
                warehouse = Warehouse.query.filter_by(preset_id=latest_preset.id).first()
                
                if warehouse:
                    # Get location details
                    location = Location.query.get(warehouse.location_id)
                    if location:
                        center_lat = location.lat
                        center_lng = location.lon
        except Exception:
            # Fall back to default coordinates on error
            pass
            
        return center_lat, center_lng