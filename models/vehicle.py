class Vehicle:
    def __init__(self, id, capacity=1000, speed=50, working_hours=8, cost_per_km=0.5):
        """
        Initialize a vehicle.
        
        Args:
            id: Unique identifier
            capacity: Maximum capacity in kg
            speed: Average speed in km/h
            working_hours: Maximum working hours
            cost_per_km: Cost per kilometer
        """
        self.id = id
        self.capacity = capacity
        self.speed = speed
        self.working_hours = working_hours
        self.cost_per_km = cost_per_km
        
        # Dynamic state
        self.current_location = None
        self.current_load = 0
        self.current_route = []
        self.completed_stops = []
        
    def travel_time(self, from_loc, to_loc):
        """Calculate travel time between locations in minutes."""
        distance = from_loc.distance_to(to_loc)  # in km
        return (distance / self.speed) * 60  # convert to minutes
    
    def to_dict(self):
        """Convert to dictionary for serialization."""
        return {
            'id': self.id,
            'capacity': self.capacity,
            'speed': self.speed,
            'working_hours': self.working_hours,
            'cost_per_km': self.cost_per_km,
        }