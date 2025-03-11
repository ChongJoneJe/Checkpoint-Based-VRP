# openrouteservice to display map with markers
import folium
import openrouteservice
from config import ORS_API_KEY, WAREHOUSE
from openrouteservice import convert

def initialize_map(center=WAREHOUSE, zoom_start=13):
    """
    Initialize a Folium map centered at the given coordinates.
    
    Args:
        center (tuple): The center of the map (lat, lon).
        zoom_start (int): Initial zoom level.
        
    Returns:
        folium.Map: The initialized map.
    """
    return folium.Map(location=center, zoom_start=zoom_start)

def add_marker(map_object, location, popup_text="Location", marker_color="blue"):
    """
    Add a marker to the map.
    
    Args:
        map_object (folium.Map): The map to add the marker to.
        location (tuple): Coordinates (lat, lon).
        popup_text (str): Popup text for the marker.
        marker_color (str): Marker color.
    """
    folium.Marker(location, popup=popup_text, icon=folium.Icon(color=marker_color)).add_to(map_object)

def add_route(map_object, route_geojson, color="green"):
    """
    Add a route (as a GeoJSON object) to the map.
    
    Args:
        map_object (folium.Map): The map to add the route to.
        route_geojson (dict): GeoJSON data for the route.
        color (str): Color for the route line.
    """
    folium.GeoJson(route_geojson, name="Route", style_function=lambda x: {"color": color}).add_to(map_object)

def get_route_from_ors(coordinates):
    """
    Call openrouteservice API to get a route for given coordinates.
    
    Args:
        coordinates (list): List of [lon, lat] pairs.
        
    Returns:
        dict: GeoJSON response of the route.
    """
    client = openrouteservice.Client(key=ORS_API_KEY)
    route = client.directions(coordinates=coordinates, profile='driving-car', format='geojson')
    return route

if __name__ == "__main__":
    # Example usage: visualize the warehouse and some drop-off points
    m = initialize_map()
    # Add warehouse marker
    add_marker(m, ORS_API_KEY and WAREHOUSE or (40.05, -73.95), "Warehouse", "black")
    
    # For demo, add some random markers (or load from environment.py)
    demo_locations = [(40.02, -73.98), (40.06, -73.96), (40.08, -73.94)]
    for loc in demo_locations:
        add_marker(m, loc, "Drop-off", "blue")
    
    # Save the map to an HTML file
    m.save("visualization_map.html")
    print("Map saved as visualization_map.html")
