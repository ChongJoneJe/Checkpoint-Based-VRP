let map;
let currentPreset = null;
let warehouseMarker = null;
let destinationMarkers = [];
let routeLayer = null;

document.addEventListener('DOMContentLoaded', function() {
    // Set up event listeners
    document.getElementById('load-preset-btn').addEventListener('click', loadSelectedPreset);
    document.getElementById('solve-btn').addEventListener('click', solveVRP);
});

/**
 * Load the selected preset
 */
function loadSelectedPreset() {
    const presetSelect = document.getElementById('presets-dropdown');
    const presetId = presetSelect.value;
    
    if (!presetId) {
        alert('Please select a preset');
        return;
    }
    
    // Fetch the selected preset data
    fetch(`/get_preset/${presetId}`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                currentPreset = data.preset;
                
                // Show preset info
                document.getElementById('preset-name').textContent = currentPreset.name;
                document.getElementById('warehouse-coords').textContent = 
                    `${currentPreset.warehouse[0].toFixed(6)}, ${currentPreset.warehouse[1].toFixed(6)}`;
                document.getElementById('destination-count').textContent = currentPreset.destinations.length;
                document.getElementById('preset-info').classList.remove('hidden');
                
                // Enable solve button
                document.getElementById('solve-btn').disabled = false;
                
                // Initialize map if not already done
                if (!map) {
                    initializeMap();
                }
                
                // Update map with locations
                updateMapWithPreset();
                
                // Show map container
                document.getElementById('map-container').classList.remove('hidden');
            } else {
                alert('Error loading preset: ' + data.message);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Failed to load preset');
        });
}

/**
 * Initialize the map
 */
function initializeMap() {
    // Create map centered on warehouse if available, otherwise use default center
    const center = currentPreset && currentPreset.warehouse ? 
        currentPreset.warehouse : [3.1390, 101.6869];
    
    map = Utils.createMap('map', center, 13);
}

/**
 * Update the map with the current preset locations
 */
function updateMapWithPreset() {
    // Clear existing markers
    Utils.clearMapLayers(map);
    warehouseMarker = null;
    destinationMarkers = [];
    routeLayer = null;
    
    // Add warehouse marker
    const [wLat, wLng] = currentPreset.warehouse;
    warehouseMarker = L.marker([wLat, wLng], {
        icon: Utils.createMarkerIcon('warehouse')
    }).addTo(map);
    warehouseMarker.bindPopup(`Warehouse<br>${wLat.toFixed(6)}, ${wLng.toFixed(6)}`);
    
    // Add destination markers
    currentPreset.destinations.forEach((coords, index) => {
        const [lat, lng] = coords;
        const marker = L.marker([lat, lng], {
            icon: Utils.createMarkerIcon('destination', { number: index + 1 })
        }).addTo(map);
        
        marker.bindPopup(`Destination ${index + 1}<br>${lat.toFixed(6)}, ${lng.toFixed(6)}`);
        destinationMarkers.push(marker);
    });
    
    // Fit map to show all markers
    const group = new L.featureGroup([warehouseMarker, ...destinationMarkers]);
    map.fitBounds(group.getBounds().pad(0.1));
}

/**
 * Solve the VRP with the current preset
 */
function solveVRP() {
    // Get values from form
    const numVehicles = parseInt(document.getElementById('num-vehicles').value) || 1;
    const algorithm = document.getElementById('algorithm').value;
    const useCheckpoints = document.getElementById('use-checkpoints').checked;
    
    // Build request data
    const data = {
        preset_id: currentPreset.id,
        num_vehicles: numVehicles,
        algorithm: algorithm,
        use_checkpoints: useCheckpoints  // Send this parameter to backend
    };
    
    // Show loading state
    document.getElementById('results-container').innerHTML = '<p>Solving VRP...</p>';
    
    // Send to backend
    fetch('/vrp/solve', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            displayResults(data);
        } else {
            // Show error
        }
    })
    .catch(error => {
        // Handle error
    });
}

/**
 * Display the solver results
 */
function displayResults(data) {
    const resultsPanel = document.getElementById('results-panel');
    const resultsContent = document.getElementById('results-content');
    
    let html = `
        <div class="results-summary">
            <p><strong>Total Distance:</strong> ${data.total_distance.toFixed(2)} km</p>
            <p><strong>Computation Time:</strong> ${data.computation_time.toFixed(3)} seconds</p>
        </div>
        <h3>Routes:</h3>
        <div class="routes-list">
    `;
    
    data.routes.forEach((route, index) => {
        html += `
            <div class="route">
                <h4>Route ${index + 1}</h4>
                <p><strong>Distance:</strong> ${route.distance.toFixed(2)} km</p>
                <p><strong>Path:</strong> Warehouse → `;
        
        route.stops.forEach(stop => {
            html += `${stop} → `;
        });
        
        html += `Warehouse</p>
            </div>
        `;
    });
    
    html += `</div>`;
    
    resultsContent.innerHTML = html;
    resultsPanel.classList.remove('hidden');
}

/**
 * Draw the calculated routes on the map
 */
function drawRoutes(routes) {
    // Clear any existing routes
    if (routeLayer) {
        map.removeLayer(routeLayer);
    }
    
    // Create a feature group for all routes
    routeLayer = L.featureGroup().addTo(map);
    
    // Define colors for different routes
    const colors = ['#e41a1c', '#377eb8', '#4daf4a', '#984ea3', '#ff7f00', '#ffff33', '#a65628', '#f781bf'];
    
    // Draw each route
    routes.forEach((route, index) => {
        const color = colors[index % colors.length];
        
        // Convert stop indices to coordinates
        const coordinates = [];
        
        // Start at warehouse
        coordinates.push(currentPreset.warehouse);
        
        // Add each stop
        for (const stopIndex of route.stops) {
            coordinates.push(currentPreset.destinations[stopIndex]);
        }
        
        // End at warehouse
        coordinates.push(currentPreset.warehouse);
        
        // Create a polyline for this route
        L.polyline(coordinates, {
            color: color,
            weight: 4,
            opacity: 0.7
        }).addTo(routeLayer);
        
        // Add direction arrows
        for (let i = 0; i < coordinates.length - 1; i++) {
            const p1 = coordinates[i];
            const p2 = coordinates[i + 1];
            
            // Calculate midpoint
            const lat = (p1[0] + p2[0]) / 2;
            const lng = (p1[1] + p2[1]) / 2;
            
            // Add arrow marker
            L.marker([lat, lng], {
                icon: L.divIcon({
                    className: 'direction-arrow',
                    html: '→',
                    iconSize: [20, 20],
                    iconAnchor: [10, 10]
                })
            }).addTo(routeLayer);
        }
    });
}