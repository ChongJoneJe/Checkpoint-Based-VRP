let map;
let clusterMarkers = [];
let warehouseMarker = null;
let currentPreset = 'all';

// Colors for clusters (add more as needed)
const clusterColors = [
    '#3388ff', '#ff3333', '#33cc33', '#ff9900', '#9966ff',
    '#ff66cc', '#99cc00', '#00ccff', '#ff6600', '#9933ff',
    '#33cc99', '#ff9966', '#6699ff', '#cc66ff', '#ffcc00'
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
            console.log("Response status:", response.status);
            return response.json();
        })
        .then(data => {
            console.log("Response data:", data);
            
            // Does data.presets exist?
            console.log("Presets array:", data.presets);
            
            // If it exists, iterate through presets
            if (data.presets && data.presets.length > 0) {
                data.presets.forEach(preset => {
                    console.log("Processing preset:", preset);
                    // Rest of your code...
                });
            }
        })
        .catch(error => console.error("Error loading presets:", error));
}

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
        
        // Add cluster info to sidebar
        const clusterElement = document.createElement('div');
        clusterElement.className = 'cluster-item';
        clusterElement.innerHTML = `
            <h4>
                <span class="color-sample" style="background-color: ${clusterColor}"></span>
                Cluster ${clusterId}
                <span class="location-count">(${cluster.locations.length} locations)</span>
            </h4>
            <div class="cluster-details">
                <p>Centroid: ${cluster.centroid[0].toFixed(4)}, ${cluster.centroid[1].toFixed(4)}</p>
                ${cluster.name ? `<p>Region: ${cluster.name}</p>` : ''}
            </div>
        `;
        clusterListElement.appendChild(clusterElement);
        
        // Add markers for this cluster
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
                Cluster: ${clusterId}<br>
                ${location.street ? `Street: ${location.street}<br>` : ''}
                ${location.neighborhood ? `Neighborhood: ${location.neighborhood}<br>` : ''}
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