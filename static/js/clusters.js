let map;
let clusterMarkers = [];
let warehouseMarker = null;
let currentPreset = 'all';

// More color options for visualizing clusters
const clusterColors = [
    '#FF5733', // Red-Orange
    '#33A8FF', // Blue
    '#45FF33', // Green
    '#F033FF', // Purple
    '#FFE033', // Yellow
    '#33FFF6', // Cyan
    '#FF33A8', // Pink
    '#8C33FF', // Violet
    '#FF8C33', // Orange
    '#33FF8C', // Mint
    '#FF3333', // Red
    '#3361FF', // Royal Blue
    '#33FF61', // Light Green
    '#DA33FF', // Magenta
    '#FFDA33', // Gold
    '#33FFE0', // Turquoise
    '#FF3380', // Rose
    '#8CFF33', // Lime
    '#FF6E33', // Coral
    '#338CFF', // Cobalt
    '#B6FF33', // Yellow-Green
    '#FF33DA', // Hot Pink
    '#5733FF', // Indigo
    '#33FFB6', // Aquamarine
    '#FF5733', // Vermilion
    '#33D4FF', // Sky Blue
    '#57FF33', // Chartreuse
    '#FF33D4', // Fuchsia
    '#FF8C33', // Amber
    '#338CFF'  // Azure
];

// Initialize map
function initMap() {
    // Center on Malaysia by default
    map = L.map('map').setView([3.1390, 101.6869], 12);
    
    // Add OpenStreetMap tiles
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);
    
    // Add scale control
    L.control.scale().addTo(map);
    
    // Load presets for dropdown
    loadPresets();
    
    // Initial load of all clusters
    loadClusters();
    
    // Set up event listener for preset selection
    document.getElementById('preset-select').addEventListener('change', function() {
        currentPreset = this.value;
        loadClusters(currentPreset);
    });
}

// Load presets for the dropdown
function loadPresets() {
    console.log("Loading presets...");
    
    fetch('/clustering/get_presets_for_clustering')
        .then(response => {
            console.log("Preset API response status:", response.status);
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log("Preset data:", data);
            
            // Clear any existing options except "All Locations"
            const selectElement = document.getElementById('preset-select');
            while (selectElement.options.length > 1) {
                selectElement.remove(1);
            }
            
            // Add presets
            if (data.presets && data.presets.length > 0) {
                data.presets.forEach(preset => {
                    const option = document.createElement('option');
                    option.value = preset.id;
                    option.textContent = `${preset.name} (${preset.location_count || 0} locations)`;
                    selectElement.appendChild(option);
                });
                console.log(`Added ${data.presets.length} presets to dropdown`);
            } else {
                console.log("No presets found in response");
                // Add message when no presets exist
                const emptyOption = document.createElement('option');
                emptyOption.disabled = true;
                emptyOption.textContent = "No saved presets found";
                selectElement.appendChild(emptyOption);
            }
        })
        .catch(error => {
            console.error('Error loading presets:', error);
            const selectElement = document.getElementById('preset-select');
            const errorOption = document.createElement('option');
            errorOption.disabled = true;
            errorOption.textContent = "Error loading presets";
            selectElement.appendChild(errorOption);
        });
}

// Load clusters from the backend
function loadClusters(presetId = 'all') {
    // Clear existing markers
    clearClusterMarkers();
    
    // Show loading state
    document.getElementById('cluster-list').innerHTML = '<p>Loading clusters...</p>';
    
    // Build URL with optional preset filter
    let url = '/clustering/get_clusters';
    if (presetId !== 'all') {
        url += `?preset_id=${presetId}`;
    }
    
    fetch(url)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                displayClusters(data.clusters);
                displayWarehouse(data.warehouse);
                updateStats(data.stats);
            } else {
                document.getElementById('cluster-list').innerHTML = 
                    `<p class="error">Error: ${data.message || 'Could not load clusters'}</p>`;
            }
        })
        .catch(error => {
            console.error('Error loading clusters:', error);
            document.getElementById('cluster-list').innerHTML = 
                '<p class="error">Error loading clusters. Please try again.</p>';
        });
}

// Display clusters on the map and in the sidebar
function displayClusters(clusters) {
    const clusterListElement = document.getElementById('cluster-list');
    clusterListElement.innerHTML = '';
    
    if (!clusters || clusters.length === 0) {
        clusterListElement.innerHTML = '<p>No clusters found. Try running clustering first.</p>';
        return;
    }
    
    // Calculate bounds to fit all markers
    const bounds = L.latLngBounds([]);
    
    // Process clusters
    clusters.forEach((cluster, index) => {
        const clusterId = cluster.id || index;
        const clusterColor = clusterColors[index % clusterColors.length];
        
        // No need for city prefix anymore - use the cluster name directly
        const displayName = cluster.name || `Cluster ${clusterId}`;
        
        // Find common streets and neighborhoods safely
        let commonStreet = findCommonValue(cluster.locations, 'street');
        let commonNeighborhood = findCommonValue(cluster.locations, 'neighborhood');
        
        // Add cluster info to sidebar
        const clusterElement = document.createElement('div');
        clusterElement.className = 'cluster-item';
        
        clusterElement.innerHTML = `
            <h4>
                <span class="color-sample" style="background-color: ${clusterColor}"></span>
                ${displayName}
                <span class="location-count">(${cluster.locations.length} locations)</span>
            </h4>
            <div class="cluster-details">
                <p>Centroid: ${cluster.centroid[0].toFixed(4)}, ${cluster.centroid[1].toFixed(4)}</p>
                ${commonStreet ? `<p><strong>Common Street:</strong> ${commonStreet}</p>` : ''}
                ${commonNeighborhood ? `<p><strong>Neighborhood:</strong> ${commonNeighborhood}</p>` : ''}
            </div>
        `;
        clusterListElement.appendChild(clusterElement);
        
        // Add markers for this cluster - unchanged
        cluster.locations.forEach(location => {
            // Create marker with custom icon
            const marker = L.circleMarker([location.lat, location.lon], {
                radius: 8,
                fillColor: clusterColor,
                color: '#fff',
                weight: 1,
                opacity: 1,
                fillOpacity: 0.8
            }).addTo(map);
            
            // Add popup with location details
            const popupContent = `
                <strong>Location ID: ${location.id}</strong><br>
                Cluster: ${displayName}<br>
                ${location.street ? `Street: ${location.street}<br>` : ''}
                ${location.neighborhood ? `Neighborhood: ${location.neighborhood}<br>` : ''}
                ${location.city ? `City: ${location.city}<br>` : ''}
                Coordinates: ${location.lat.toFixed(5)}, ${location.lon.toFixed(5)}
            `;
            marker.bindPopup(popupContent);
            
            // Add to list for later cleanup
            clusterMarkers.push(marker);
            
            // Extend bounds to include this marker
            bounds.extend([location.lat, location.lon]);
        });
    });
    
    // Fit map to bounds of all markers if any exist
    if (clusterMarkers.length > 0) {
        map.fitBounds(bounds, { padding: [50, 50] });
    }
    
    // At the end, add:
    displayCheckpoints(clusters);
}

// Helper function to find the most common value
function findCommonValue(items, propertyName) {
    if (!items || !items.length) return null;
    
    // Count occurrences of each value
    const counts = {};
    let maxCount = 0;
    let maxValue = null;
    
    items.forEach(item => {
        const value = item[propertyName];
        if (!value) return;
        
        counts[value] = (counts[value] || 0) + 1;
        
        if (counts[value] > maxCount) {
            maxCount = counts[value];
            maxValue = value;
        }
    });
    
    return maxValue;
}

// Add this function to display checkpoints on the map
function displayCheckpoints(clusters) {
    clusters.forEach((cluster, index) => {
        if (cluster.checkpoint_lat && cluster.checkpoint_lon) {
            // Create a special marker for checkpoints
            const checkpoint = L.marker([cluster.checkpoint_lat, cluster.checkpoint_lon], {
                icon: L.divIcon({
                    className: 'checkpoint-marker',
                    html: '<div class="checkpoint-icon">✓</div>',
                    iconSize: [24, 24],
                    iconAnchor: [12, 12]
                })
            }).addTo(map);
            
            const clusterColor = clusterColors[index % clusterColors.length];
            
            // Determine the best name to display (for consistency)
            let displayName = cluster.name || `Cluster ${cluster.id || index}`;
            
            // Add popup with checkpoint details
            checkpoint.bindPopup(`
                <div class="checkpoint-popup">
                    <h4>Security Checkpoint</h4>
                    <p>For Cluster: ${displayName}</p>
                    <p>Coordinates: ${cluster.checkpoint_lat.toFixed(5)}, ${cluster.checkpoint_lon.toFixed(5)}</p>
                </div>
            `);
            
            // Draw a line from checkpoint to warehouse if warehouse exists
            if (warehouseMarker) {
                const warehouselatlng = warehouseMarker.getLatLng();
                const checkpointLine = L.polyline([
                    [cluster.checkpoint_lat, cluster.checkpoint_lon],
                    [warehouselatlng.lat, warehouselatlng.lng]
                ], {
                    color: clusterColor,
                    weight: 3,
                    opacity: 0.6,
                    dashArray: '10, 10'
                }).addTo(map);
                
                // Store for later removal
                clusterMarkers.push(checkpointLine);
            }
            
            // Store for later removal
            clusterMarkers.push(checkpoint);
        }
    });
}

// Display warehouse on the map if available
function displayWarehouse(warehouse) {
    // Remove existing warehouse marker
    if (warehouseMarker) {
        map.removeLayer(warehouseMarker);
        warehouseMarker = null;
    }
    
    // If no warehouse, hide the warehouse info section
    const warehouseInfoElement = document.getElementById('warehouse-info');
    if (!warehouse) {
        if (warehouseInfoElement) {
            warehouseInfoElement.style.display = 'none';
        }
        return;
    }
    
    // Create warehouse marker with custom icon
    warehouseMarker = L.marker([warehouse.lat, warehouse.lon], {
        icon: L.divIcon({
            className: 'warehouse-marker',
            html: '<div class="warehouse-icon"><i class="fas fa-warehouse"></i></div>',
            iconSize: [30, 30],
            iconAnchor: [15, 15]
        })
    }).addTo(map);
    
    // Add popup with warehouse details
    const popupContent = `
        <div class="warehouse-popup">
            <h4>Warehouse</h4>
            ${warehouse.street ? `<p>Street: ${warehouse.street}</p>` : ''}
            ${warehouse.neighborhood ? `<p>Neighborhood: ${warehouse.neighborhood}</p>` : ''}
            ${warehouse.town ? `<p>Town: ${warehouse.town}</p>` : ''}
            ${warehouse.city ? `<p>City: ${warehouse.city}</p>` : ''}
            <p>Coordinates: ${warehouse.lat.toFixed(5)}, ${warehouse.lon.toFixed(5)}</p>
        </div>
    `;
    warehouseMarker.bindPopup(popupContent);
    
    // Display warehouse info in sidebar if the element exists
    if (warehouseInfoElement) {
        warehouseInfoElement.style.display = 'block';
        warehouseInfoElement.innerHTML = `
            <h3>Warehouse</h3>
            <div class="warehouse-details">
                ${warehouse.street ? `<p>Street: ${warehouse.street}</p>` : ''}
                ${warehouse.neighborhood ? `<p>Neighborhood: ${warehouse.neighborhood}</p>` : ''}
                <p>Coordinates: ${warehouse.lat.toFixed(5)}, ${warehouse.lon.toFixed(5)}</p>
            </div>
        `;
    }
    
    // Only adjust bounds to include warehouse when it's the only marker
    if (clusterMarkers.length === 0) {
        map.setView([warehouse.lat, warehouse.lon], 14);
    }
}

// Update the clustering statistics
function updateStats(stats) {
    if (stats) {
        document.getElementById('total-locations').textContent = stats.total_locations || 0;
        document.getElementById('num-clusters').textContent = stats.num_clusters || 0;
        document.getElementById('noise-points').textContent = stats.noise_points || 0;
    }
}

// Clear all markers from the map
function clearClusterMarkers() {
    clusterMarkers.forEach(marker => {
        map.removeLayer(marker);
    });
    clusterMarkers = [];
    
    if (warehouseMarker) {
        map.removeLayer(warehouseMarker);
        warehouseMarker = null;
    }
}

// Initialize the map when the page is loaded
document.addEventListener('DOMContentLoaded', initMap);