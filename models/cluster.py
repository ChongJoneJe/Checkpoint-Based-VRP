from models import db
from datetime import datetime

class Cluster(db.Model):
    """A cluster of locations"""
    __tablename__ = 'clusters'
    __table_args__ = {'extend_existing': True} 
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))
    centroid_lat = db.Column(db.Float)
    centroid_lon = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    locations = db.relationship('Location', backref='cluster')
    
    def __repr__(self):
        return f"<Cluster {self.id}: {self.name}>"