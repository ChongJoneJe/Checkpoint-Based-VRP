import numpy as np

class Location:
    def __init__(self, id, lat, lon, type='destination', name=None, time_window=None):
        """
        Initialize a location.
        
        Args:
            id: Unique identifier
            lat: Latitude
            lon: Longitude
            type: Location type ('warehouse', 'destination', 'pickup')
            name: Optional location name
            time_window: Optional tuple of (start_time, end_time) in minutes
        """
        self.id = id
        self.lat = lat
        self.lon = lon
        self.coordinates = np.array([lat, lon])
        self.type = type
        self.name = name or f"Location {id}"
        self.time_window = time_window
        
    def distance_to(self, other):
        """Calculate haversine distance to another location."""
        from utils.distance import haversine_distance
        return haversine_distance(self.coordinates, other.coordinates)
    
    def to_dict(self):
        """Convert to dictionary for serialization."""
        return {
            'id': self.id,
            'lat': self.lat,
            'lon': self.lon,
            'type': self.type,
            'name': self.name,
            'time_window': self.time_window
        }
    
    @classmethod
    def from_dict(cls, data):
        """Create location from dictionary."""
        return cls(
            id=data['id'],
            lat=data['lat'],
            lon=data['lon'],
            type=data.get('type', 'destination'),
            name=data.get('name'),
            time_window=data.get('time_window')
        )