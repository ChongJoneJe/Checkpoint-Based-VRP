import os
import unittest
import time
from algorithms.dbscan import GeoDBSCAN
from openrouteservice.exceptions import ApiError

class IntegrationTestGeoDBSCAN(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Provide your actual OpenRouteService API key here or via an environment variable.
        ors_api_key = '5b3ce3597851110001cf62481caff684775f4567ac619c56d44d6f05'
        cls.dbscan = GeoDBSCAN(api_key=ors_api_key)
    
    def test_real_get_road_tags(self):
        """
        Test the actual extraction of OSM tags using the Nominatim API.
        """
        # Pick a coordinate (example)
        lat, lon = 3.1089778, 101.4753327
        tags = self.dbscan.get_road_tags(lat, lon)
        print("OSM extraction result:", tags)
        self.assertIsInstance(tags, dict)
        # If a highway tag is present, verify that a 'type' key is also returned.
        if "highway" in tags:
            self.assertIn("type", tags, "Expected 'type' key in OSM tags when highway is present")
    
    def test_real_identify_access_points_with_verification(self):
        """
        Enhanced test for access point identification that verifies the first access point
        is correctly identified and aligns with the criteria: the first occurrence
        of a road whose highway type is either 'secondary' or 'primary'.
        """
        # These coordinates correspond to a real-world route.
        # Modify these if needed so that the route is within acceptable limits.
        src_lat, src_lon = 3.1089778, 101.4753327         # Destination in residential area
        dest_lat, dest_lon = 3.127689184181483, 101.46796921545267  # Warehouse
        
        print("\n=== Testing Road Type Detection Along Route ===")
        print(f"Route: ({src_lat}, {src_lon}) → ({dest_lat}, {dest_lon})")
        
        # Ensure the OpenRouteService client is available
        if self.dbscan.client is None:
            self.fail("No OpenRouteService client available")
            
        try:
            # Use proper coordinate order: [lon, lat]
            coords = [[src_lon, src_lat], [dest_lon, dest_lat]]
            route = self.dbscan.client.directions(
                coordinates=coords,
                profile='driving-car',
                format='geojson'
            )
        except ApiError as e:
            # If the error indicates the route distance is too long, skip the test.
            if "exceed" in str(e):
                self.skipTest("Route distance exceeds server limits; choose a shorter route for testing.")
            else:
                self.fail(f"ApiError during route request: {e}")
        except Exception as e:
            self.fail(f"Exception during route request: {e}")
            
        # Extract route coordinates for inspection
        route_coords = route['features'][0]['geometry']['coordinates']
        print(f"Route has {len(route_coords)} coordinate points")
        
        # Log OSM tags for selected sample points
        print("\n--- Logging Sample Points Along Route ---")
        sample_indices = []
        if len(route_coords) > 10:
            step = len(route_coords) // 5  # Divide route into 5 parts
            sample_indices = [step, step*2, step*3, step*4]
        for idx in sample_indices:
            time.sleep(1)  # Respect Nominatim rate limits
            point = route_coords[idx]
            tags = self.dbscan.get_road_tags(point[1], point[0])
            print(f"Point {idx}: ({point[1]}, {point[0]}) → Tags: {tags}")
            highway = tags.get("highway", "none")
            if highway in ("secondary", "primary"):
                print(f"*** FOUND TARGET ROAD TYPE: {highway} at point {idx} ***")
        
        # Run the full access point detection function
        print("\n--- Running Full Access Point Detection ---")
        access_points = self.dbscan.identify_access_points(src_lat, src_lon, dest_lat, dest_lon)
        print("Access points identified:", access_points)
        
        # Assertions on the returned access points list
        self.assertIsInstance(access_points, list)
        
        if access_points:
            first_ap = access_points[0]
            print(f"\nFirst access point: {first_ap}")
            # Verify the checkpoint has the necessary attributes.
            for ap in access_points:
                self.assertIn('lat', ap)
                self.assertIn('lon', ap)
                self.assertIn('position', ap)
                self.assertIn('from_type', ap)
                self.assertIn('to_type', ap)
            # Verify the road type is either secondary or primary.
            self.assertIn(first_ap['from_type'], ("secondary", "primary"))
            
            # Verify that no earlier coordinate (before first checkpoint) had the target road type.
            pos = first_ap['position']
            for i in range(0, pos):
                if i % 10 == 0 and i > 0:  # check every 10th point to limit API calls
                    time.sleep(1)
                    pt = route_coords[i]
                    tags = self.dbscan.get_road_tags(pt[1], pt[0])
                    highway = tags.get("highway", "")
                    self.assertNotIn(highway, ("secondary", "primary"),
                        f"Found {highway} at position {i}, before checkpoint at position {pos}")
        else:
            print("No access points found - this may be normal depending on the selected route.")

if __name__ == '__main__':
    unittest.main()