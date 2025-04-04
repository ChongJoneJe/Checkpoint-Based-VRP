let map;
let clusterMarkers = [];
let warehouseMarker = null;
let currentPreset = 'all';
let checkpointMarkers = [];
let clusterMap = null; // Added global variable for clusterMap

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

// Helper function to get cluster color
function getClusterColor(clusterId) {
    // Convert clusterId to a number for indexing into colors array
    const index = typeof clusterId === 'string' 
        ? clusterId.split('').reduce((a,b)=>a+b.charCodeAt(0), 0) % clusterColors.length
        : clusterId % clusterColors.length;
    
    return clusterColors[index];
}

// Initialize map
function initMap() {
    // Center on Malaysia by default
    map = initializeMap(); // Updated to use initializeMap function
    
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

    // Add toward the end of your initMap function
    document.getElementById('show-checkpoints').addEventListener('change', function() {
        const visible = this.checked;
        checkpointMarkers.forEach(marker => {
            if (visible) {
                marker.addTo(map);
            } else {
                marker.remove();
            }
        });
    });
}

// Modify your map initialization
function initializeMap() {
    const map = L.map('map').setView([3.1390, 101.6869], 13);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);
    
    // Make available globally
    clusterMap = map;
    
    return map;
}

// Update this function in clusters.js
function loadPresets() {
    console.log("Loading presets..."); // Debug line
    
    fetch('/clustering/get_presets_for_clustering')  // Changed from '/presets/get_presets'
        .then(response => {
            console.log("Got response:", response.status); // Debug line
            return response.json();
        })
        .then(data => {
            console.log("Presets data:", data); // Debug to see response data
            
            // Populate dropdown
            const presetSelect = document.getElementById('preset-select');
            // Clear existing options
            presetSelect.innerHTML = '';
            
            // Add default option
            const defaultOption = document.createElement('option');
            defaultOption.value = '';
            defaultOption.textContent = 'Select a preset...';
            defaultOption.selected = true;
            presetSelect.appendChild(defaultOption);
            
            if (data.presets && data.presets.length > 0) {
                console.log(`Found ${data.presets.length} presets`); // Debug line
                
                data.presets.forEach(preset => {
                    const option = document.createElement('option');
                    option.value = preset.id;
                    option.textContent = `${preset.name} (${preset.location_count || 0} locations)`;
                    presetSelect.appendChild(option);
                });
            } else {
                console.log("No presets found in response"); // Debug line
                
                const option = document.createElement('option');
                option.disabled = true;
                option.value = '';
                option.textContent = 'No saved presets found';
                presetSelect.appendChild(option);
            }
        })
        .catch(error => {
            console.error('Error loading presets:', error);
            
            // Add error handling to dropdown
            const presetSelect = document.getElementById('preset-select');
            presetSelect.innerHTML = '';
            const errorOption = document.createElement('option');
            errorOption.disabled = true;
            errorOption.selected = true;
            errorOption.textContent = 'Error loading presets';
            presetSelect.appendChild(errorOption);
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
    if (presetId && presetId !== 'all') {
        url += `?preset_id=${presetId}`;
    }
    
    console.log("Loading clusters from:", url); // Debug log
    
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
        
        // Simplified sidebar entry
        const clusterElement = document.createElement('div');
        clusterElement.className = 'cluster-info';
        
        // Simplified cluster listing in sidebar
        clusterElement.innerHTML = `
            <div class="cluster-header">
                <span class="color-sample" style="background-color: ${clusterColor}"></span>
                <strong>${displayName}</strong> (${cluster.locations.length} locations)
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

// Function to display checkpoints
function displayCheckpoints(clusters) {
    // Clear any existing checkpoint markers
    checkpointMarkers.forEach(marker => marker.remove());
    checkpointMarkers = [];
    
    // For each cluster with a checkpoint
    clusters.forEach(cluster => {
        if (cluster.checkpoint) {
            // Create marker for checkpoint
            const checkpoint = L.marker([cluster.checkpoint.lat, cluster.checkpoint.lon], {
                icon: createCheckpointIcon(cluster.id)
            }).addTo(map);
            
            // Add popup with information
            checkpoint.bindPopup(`
                <strong>Security Checkpoint</strong><br>
                <strong>Cluster:</strong> ${cluster.name}<br>
                <strong>Road Type:</strong> ${cluster.checkpoint.from_road_type} → ${cluster.checkpoint.to_road_type}<br>
                <strong>Coordinates:</strong> ${cluster.checkpoint.lat.toFixed(6)}, ${cluster.checkpoint.lon.toFixed(6)}<br>
                <button class="btn-small" onclick="navigateToCheckpoint(${cluster.checkpoint.lat}, ${cluster.checkpoint.lon})">Navigate Here</button>
            `);
            
            // Draw a line connecting checkpoint to cluster centroid
            if (cluster.centroid && cluster.centroid[0] && cluster.centroid[1]) {
                const line = L.polyline([
                    [cluster.checkpoint.lat, cluster.checkpoint.lon],
                    [cluster.centroid[0], cluster.centroid[1]]
                ], {
                    color: getClusterColor(cluster.id),
                    weight: 2,
                    opacity: 0.6,
                    dashArray: '5, 5'
                }).addTo(map);
                
                checkpointMarkers.push(line);
            }
            
            checkpointMarkers.push(checkpoint);
        }
    });
}

// Create custom icon for checkpoints
function createCheckpointIcon(clusterId) {
    return L.divIcon({
        className: 'checkpoint-marker',
        html: `<div class="checkpoint-icon">
                 <i class="fas fa-shield-alt" style="color: ${getClusterColor(clusterId)}"></i>
               </div>`,
        iconSize: [24, 24]
    });
}

// Add CSS for checkpoint markers
const style = document.createElement('style');
style.textContent = `
.checkpoint-icon {
    width: 16px;
    height: 16px;
    border: 3px solid white;
    border-radius: 50%;
    box-shadow: 0 0 5px rgba(0,0,0,0.5);
    position: relative;
}

.checkpoint-icon::before {
    content: '';
    position: absolute;
    top: -5px;
    left: -5px;
    right: -5px;
    bottom: -5px;
    border: 2px solid rgba(255,255,255,0.5);
    border-radius: 50%;
}
`;
document.head.appendChild(style);

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

// Make sure to update your selectCluster function to call the checkpoints module:
function selectCluster(clusterId) {
    // Your existing code...
    
    // Highlight the selected cluster
    document.querySelectorAll('.cluster-item').forEach(item => {
        item.classList.remove('active');
    });
    
    const selectedItem = document.querySelector(`.cluster-item[data-cluster-id="${clusterId}"]`);
    if (selectedItem) {
        selectedItem.classList.add('active');
    }
    
    // This triggers the checkpoint loading
    // The checkpoint module will listen for these clicks through event delegation
}

// Initialize the map when the page is loaded
document.addEventListener('DOMContentLoaded', initMap);