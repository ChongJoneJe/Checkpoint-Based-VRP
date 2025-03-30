from algorithms.dbscan import GeoDBSCAN
from repositories.location_repository import LocationRepository
from repositories.cluster_repository import ClusterRepository
from utils.database import execute_read
import os

def test_street_based_clustering():
    """Test that locations with the same street are assigned to the same cluster"""
    print("=== Starting street-based clustering test with improved naming ===")
    
    # Initialize the clustering algorithm
    geocoder = GeoDBSCAN()
    
    # Define test locations with known streets including complex patterns
    test_locations = [
        # Jalan Setia Nusantara area
        {"lat": 3.1472, "lon": 101.7094, "street": "Jalan Setia Nusantara U13/22T", "neighborhood": "Setia Eco Park"},
        {"lat": 3.1475, "lon": 101.7080, "street": "Jalan Setia Nusantara U13/19D", "neighborhood": "Setia Eco Park"},
        {"lat": 3.1468, "lon": 101.7110, "street": "Jalan Setia Nusantara U13/25", "neighborhood": "Setia Eco Park"},
        
        # Jalan Mawar area
        {"lat": 3.1590, "lon": 101.7174, "street": "Jalan Mawar 1", "neighborhood": "Taman Mawar"},
        {"lat": 3.1595, "lon": 101.7190, "street": "Jalan Mawar 2", "neighborhood": "Taman Mawar"},
    ]
    
    # Mock warehouse location
    warehouse = {"lat": 3.1412, "lon": 101.6840}
    
    # Override geocode_location to return our predefined values
    original_geocode = geocoder.geocode_location
    
    def mock_geocode(lat, lon, max_retries=3):
        for loc in test_locations:
            if abs(loc["lat"] - lat) < 0.001 and abs(loc["lon"] - lon) < 0.001:
                return {
                    'street': loc['street'],
                    'neighborhood': loc['neighborhood'],
                    'town': 'Shah Alam',
                    'city': 'Shah Alam',
                    'postcode': '40170',
                    'country': 'Malaysia'
                }
        return original_geocode(lat, lon, max_retries)
    
    # Replace geocode_location with our mock
    geocoder.geocode_location = mock_geocode
    
    # Process each location
    for i, loc in enumerate(test_locations):
        print(f"\nProcessing location {i+1}: {loc['lat']}, {loc['lon']} (Street: {loc['street']})")
        
        result = geocoder.add_location_with_smart_clustering(
            loc["lat"], loc["lon"], warehouse["lat"], warehouse["lon"]
        )
        
        if len(result) == 4:
            location_id, cluster_id, is_new_cluster, checkpoint = result
            checkpoint_info = f", checkpoint: {checkpoint['lat']}, {checkpoint['lon']}" if checkpoint else ", no checkpoint"
        else:
            location_id, cluster_id, is_new_cluster = result
            checkpoint_info = ""
            
        print(f"  → Added as location_id: {location_id}, cluster_id: {cluster_id}, is_new: {is_new_cluster}{checkpoint_info}")
    
    # Verify results
    print("\n=== Verifying clustering results with new naming ===")
    
    # Get all clusters
    clusters = execute_read("SELECT id, name FROM clusters")
    print(f"\nFound {len(clusters)} clusters:")
    
    for cluster in clusters:
        cluster_id = cluster['id']
        
        # Get locations in this cluster
        locations = execute_read(
            """SELECT l.id, l.lat, l.lon, l.street
               FROM locations l
               JOIN location_clusters lc ON l.id = lc.location_id
               WHERE lc.cluster_id = ?""",
            (cluster_id,)
        )
        
        print(f"\nCluster {cluster_id} - {cluster['name']} has {len(locations)} locations:")
        for loc in locations:
            print(f"  → Location {loc['id']}: {loc['lat']}, {loc['lon']} (Street: {loc['street']})")
        
        # Check if cluster name is derived from street pattern or neighborhood
        streets = [loc['street'] for loc in locations]
        print(f"  Cluster name: {cluster['name']}")
        print(f"  Streets in cluster: {', '.join(streets)}")
    
    print("\n=== Street-based clustering test with improved naming completed ===")

def test_neighborhood_based_clustering():
    """Test that locations with the same neighborhood are assigned to the same cluster"""
    print("=== Starting neighborhood-based clustering test ===")
    
    # Initialize the clustering algorithm
    geocoder = GeoDBSCAN()
    
    # Define test locations with known neighborhoods but different streets
    test_locations = [
        # Bukit Bintang neighborhood, different streets
        {"lat": 3.1472, "lon": 101.7094, "street": "Jalan Alor", "neighborhood": "Bukit Bintang"},
        {"lat": 3.1475, "lon": 101.7080, "street": "Jalan Changkat", "neighborhood": "Bukit Bintang"},
        {"lat": 3.1468, "lon": 101.7110, "street": "Jalan Imbi", "neighborhood": "Bukit Bintang"},
        
        # KLCC neighborhood, different streets
        {"lat": 3.1590, "lon": 101.7174, "street": "Jalan P Ramlee", "neighborhood": "KLCC"},
        {"lat": 3.1595, "lon": 101.7190, "street": "Jalan Ampang", "neighborhood": "KLCC"},
        
        # Mont Kiara neighborhood
        {"lat": 3.1710, "lon": 101.7310, "street": "Jalan Kiara", "neighborhood": "Mont Kiara"},
    ]
    
    # Mock warehouse location
    warehouse = {"lat": 3.1412, "lon": 101.6840}
    
    # Override geocode_location to return our predefined values
    original_geocode = geocoder.geocode_location
    
    def mock_geocode(lat, lon, max_retries=3):
        for loc in test_locations:
            if abs(loc["lat"] - lat) < 0.001 and abs(loc["lon"] - lon) < 0.001:
                return {
                    'street': loc['street'],
                    'neighborhood': loc['neighborhood'],
                    'town': 'Kuala Lumpur',
                    'city': 'Kuala Lumpur',
                    'postcode': '50000',
                    'country': 'Malaysia'
                }
        return original_geocode(lat, lon, max_retries)
    
    # Replace geocode_location with our mock
    geocoder.geocode_location = mock_geocode
    
    # Process each location
    for i, loc in enumerate(test_locations):
        print(f"\nProcessing location {i+1}: {loc['lat']}, {loc['lon']} (Street: {loc['street']}, Neighborhood: {loc['neighborhood']})")
        
        location_id, cluster_id, is_new_cluster = geocoder.add_location_with_smart_clustering(
            loc["lat"], loc["lon"], warehouse["lat"], warehouse["lon"]
        )
        
        print(f"  → Added as location_id: {location_id}, cluster_id: {cluster_id}, is_new: {is_new_cluster}")
    
    # Verify results - perform checks from original test code
    # ...

def test_security_checkpoint_detection():
    """Test detection of security checkpoints using road classification transitions"""
    print("=== Starting security checkpoint detection test ===")
    
    # Skip test if no API key available
    api_key = os.environ.get('ORS_API_KEY')
    if not api_key:
        print("Skipping test: No OpenRouteService API key found in environment variables")
        return
    
    # Initialize with API key for OpenRouteService
    geocoder = GeoDBSCAN(api_key=api_key)
    
    # Test with actual locations in residential areas with known security checkpoints
    test_locations = [
        # Bangsar area (high-end residential with guard posts)
        {"lat": 3.1320, "lon": 101.6688, "description": "Bangsar residential"},
        
        # Damansara Heights (gated community)
        {"lat": 3.1459, "lon": 101.6566, "description": "Damansara Heights residential"}
    ]
    
    # Warehouse in industrial area
    warehouse = {"lat": 3.0471, "lon": 101.5834, "description": "Shah Alam industrial"}
    
    # Process each location and check for road transitions
    for i, loc in enumerate(test_locations):
        print(f"\nProcessing location {i+1}: {loc['lat']}, {loc['lon']} ({loc['description']})")
        
        # Try to identify the security checkpoint
        transitions = geocoder.identify_road_transitions(
            loc["lat"], loc["lon"], warehouse["lat"], warehouse["lon"]
        )
        
        # Print all transitions found
        print(f"Found {len(transitions)} road transitions:")
        for t in transitions:
            checkpoint_flag = "✓ CHECKPOINT" if t.get('is_potential_checkpoint') else ""
            print(f"  {t['from_type']} → {t['to_type']} at [{t['lat']}, {t['lon']}] {checkpoint_flag}")
        
        # Check if any checkpoint was identified
        checkpoints = [t for t in transitions if t.get('is_potential_checkpoint')]
        if checkpoints:
            print(f"  → Identified {len(checkpoints)} potential security checkpoints")
            best_checkpoint = checkpoints[0]
            print(f"  → Best checkpoint: {best_checkpoint['from_type']} → {best_checkpoint['to_type']} " 
                  f"at [{best_checkpoint['lat']}, {best_checkpoint['lon']}]")
    
    print("\n=== Security checkpoint detection test completed ===")

def test_pattern_based_clustering():
    """Test clustering based on street name patterns"""
    print("=== Starting pattern-based clustering test ===")
    
    # Initialize the clustering algorithm
    geocoder = GeoDBSCAN()
    
    # Define test locations with different street patterns
    test_locations = [
        # Setia Nusantara development, different sections
        {"lat": 3.1472, "lon": 101.7094, "street": "Jalan Setia Nusantara U13/22T", "neighborhood": ""},
        {"lat": 3.1475, "lon": 101.7080, "street": "Jalan Setia Nusantara U13/19D", "neighborhood": ""},
        {"lat": 3.1468, "lon": 101.7110, "street": "Jalan Setia Nusantara U13/25", "neighborhood": ""},
        
        # Mawar development, numbered streets
        {"lat": 3.1590, "lon": 101.7174, "street": "Jalan Mawar 1", "neighborhood": ""},
        {"lat": 3.1595, "lon": 101.7190, "street": "Jalan Mawar 2", "neighborhood": ""},
        {"lat": 3.1592, "lon": 101.7185, "street": "Jalan Mawar 3", "neighborhood": ""},
        
        # Taman Sri Muda with section numbers
        {"lat": 3.0451, "lon": 101.5312, "street": "Jalan Taman Sri Muda 25/3", "neighborhood": ""},
        {"lat": 3.0455, "lon": 101.5320, "street": "Jalan Taman Sri Muda 25/4", "neighborhood": ""},
        
        # Different developments that shouldn't be clustered together
        {"lat": 3.0350, "lon": 101.5450, "street": "Jalan Puchong Perdana 1", "neighborhood": ""},
        {"lat": 3.1750, "lon": 101.6950, "street": "Jalan Mont Kiara 5", "neighborhood": ""}
    ]
    
    # Mock warehouse location
    warehouse = {"lat": 3.1412, "lon": 101.6840}
    
    # Override geocode_location similar to other tests
    original_geocode = geocoder.geocode_location
    
    def mock_geocode(lat, lon, max_retries=3):
        for loc in test_locations:
            if abs(loc["lat"] - lat) < 0.001 and abs(loc["lon"] - lon) < 0.001:
                return {
                    'street': loc['street'],
                    'neighborhood': loc['neighborhood'],
                    'town': 'Shah Alam',
                    'city': 'Shah Alam',
                    'postcode': '40170',
                    'country': 'Malaysia'
                }
        return original_geocode(lat, lon, max_retries)
    
    # Replace geocode_location with our mock
    geocoder.geocode_location = mock_geocode
    
    # Process each location
    for i, loc in enumerate(test_locations):
        print(f"\nProcessing location {i+1}: {loc['lat']}, {loc['lon']} (Street: {loc['street']})")
        
        result = geocoder.add_location_with_smart_clustering(
            loc["lat"], loc["lon"], warehouse["lat"], warehouse["lon"]
        )
        
        if len(result) == 4:
            location_id, cluster_id, is_new_cluster, checkpoint = result
            checkpoint_info = f", checkpoint: {checkpoint['lat']}, {checkpoint['lon']}" if checkpoint else ", no checkpoint"
        else:
            location_id, cluster_id, is_new_cluster = result
            checkpoint_info = ""
            
        print(f"  → Added as location_id: {location_id}, cluster_id: {cluster_id}, is_new: {is_new_cluster}{checkpoint_info}")
    
    # Verify results
    print("\n=== Verifying pattern-based clustering results ===")
    
    # Get all clusters
    clusters = execute_read("SELECT id, name FROM clusters")
    print(f"\nFound {len(clusters)} clusters:")
    
    for cluster in clusters:
        cluster_id = cluster['id']
        
        # Get locations in this cluster
        locations = execute_read(
            """SELECT l.id, l.lat, l.lon, l.street
               FROM locations l
               JOIN location_clusters lc ON l.id = lc.location_id
               WHERE lc.cluster_id = ?""",
            (cluster_id,)
        )
        
        print(f"\nCluster {cluster_id} - {cluster['name']} has {len(locations)} locations:")
        for loc in locations:
            print(f"  → Location {loc['id']}: {loc['lat']}, {loc['lon']} (Street: {loc['street']})")
        
        print(f"  Cluster name: {cluster['name']}")
        print(f"  Streets in cluster: {', '.join([loc['street'] for loc in locations])}")
    
    print("\n=== Pattern-based clustering test completed ===")

if __name__ == "__main__":
    # Clear the database before testing
    from reset_db import reset_database
    reset_database()
    
    # Run the pattern-based test only
    test_pattern_based_clustering()
    print("\n" + "="*80 + "\n")
    test_security_checkpoint_detection()