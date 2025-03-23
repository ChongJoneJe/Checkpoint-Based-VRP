// Clustering analysis functionality

let map;
let warehouse = null;
let destinations = [];
let warehouseMarker = null;
let destinationMarkers = [];
let clusterMarkers = [];
let legendControl = null;
let currentPresetId = null;

// Cluster colors (for visualization)
const clusterColors = [
    '#FF5733', '#33FF57', '#3357FF', '#FF33A8', '#33FFF5', 
    '#FFD633', '#8C33FF', '#FF8C33', '#33FFAA', '#FF3333',
    '#33FFFF', '#FFFF33', '#FF33FF', '#9933FF', '#FF9933'
];

/**
 * Initialize the clustering page
 */
document.addEventListener('DOMContentLoaded', function() {
    // Initialize map
    map = L.map('map').setView([3.127993, 101.466972], 13);
    
    // Add OpenStreetMap tiles
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);
    
    // Add scale control
    L.control.scale().addTo(map);
    
    // Add event listeners
    document.getElementById('load-preset-btn').addEventListener('click', loadSelectedPreset);
    document.getElementById('run-clustering-btn').addEventListener('click', runClustering);
    
    // Load available presets
    loadPresets();
});

/**
 * Load available presets from the server
 */
function loadPresets() {
    fetch('/get_presets')
        .then(response => response.json())
        .then(data => {
            const presetsList = document.getElementById('presets-list');
            presetsList.innerHTML = '';
            
            if (data.presets && data.presets.length > 0) {
                data.presets.forEach(preset => {
                    const option = document.createElement('option');
                    option.value = preset.id;
                    option.textContent = `${preset.name} (${preset.destinations.length} destinations)`;
                    presetsList.appendChild(option);
                });
                
                // Enable the load button
                document.getElementById('load-preset-btn').disabled = false;
            } else {
                const option = document.createElement('option');
                option.disabled = true;
                option.textContent = 'No presets available';
                presetsList.appendChild(option);
                
                // Disable the load button
                document.getElementById('load-preset-btn').disabled = true;
            }
        })
        .catch(error => {
            console.error('Error loading presets:', error);
            showNotification('Failed to load presets', 'error');
        });
}

/**
 * Load the selected preset
 */
function loadSelectedPreset() {
    const presetsList = document.getElementById('presets-list');
    const selectedOption = presetsList.options[presetsList.selectedIndex];
    
    if (!selectedOption || selectedOption.disabled) {
        showNotification('Please select a valid preset', 'error');
        return;
    }
    
    const presetId = selectedOption.value;
    currentPresetId = presetId;
    
    fetch(`/get_preset/${presetId}`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                // Clear current markers
                clearMap();
                
                // Store the locations
                warehouse = data.preset.warehouse;
                destinations = data.preset.destinations;
                
                // Display the warehouse
                displayWarehouse(warehouse[0], warehouse[1]);
                
                // Display the destinations
                destinations.forEach((dest, index) => {
                    displayDestination(dest[0], dest[1], index);
                });
                
                // Fit map to show all markers
                fitMapToMarkers();
                
                showNotification(`Preset "${data.preset.name}" loaded with ${destinations.length} destinations`, 'success');
                
                // Update stats section
                document.getElementById('cluster-stats').innerHTML = `
                    <h3>Preset Information</h3>
                    <p><strong>Name:</strong> ${data.preset.name}</p>
                    <p><strong>Total Locations:</strong> ${destinations.length + 1} (1 warehouse + ${destinations.length} destinations)</p>
                    <p>Click "Run Clustering" to analyze this data.</p>
                `;
            } else {
                showNotification('Error: ' + data.message, 'error');
            }
        })
        .catch(error => {
            console.error('Error applying preset:', error);
            showNotification('Failed to load preset', 'error');
        });
}

/**
 * Display warehouse on map
 */
function displayWarehouse(lat, lng) {
    // Remove existing warehouse marker if any
    if (warehouseMarker) {
        map.removeLayer(warehouseMarker);
    }
    
    // Add warehouse marker
    warehouseMarker = L.marker([lat, lng], {
        icon: L.divIcon({
            className: 'warehouse-marker',
            html: '<div class="warehouse-icon"></div>',
            iconSize: [24, 24],
            iconAnchor: [12, 12]
        })
    }).addTo(map);
    
    // Add popup with coordinates
    warehouseMarker.bindPopup(`Warehouse<br>${lat.toFixed(6)}, ${lng.toFixed(6)}`);
}

/**
 * Display destination on map
 */
function displayDestination(lat, lng, index) {
    // Create marker for this destination
    const marker = L.marker([lat, lng], {
        icon: L.divIcon({
            className: 'destination-marker',
            html: `<div class="destination-icon">${index + 1}</div>`,
            iconSize: [22, 22],
            iconAnchor: [11, 11]
        })
    }).addTo(map);
    
    // Add popup with information
    marker.bindPopup(`Destination ${index + 1}<br>${lat.toFixed(6)}, ${lng.toFixed(6)}`);
    
    destinationMarkers.push(marker);
}

/**
 * Fit map view to show all markers
 */
function fitMapToMarkers() {
    const allMarkers = [warehouseMarker, ...destinationMarkers].filter(m => m !== null);
    
    if (allMarkers.length > 0) {
        const group = L.featureGroup(allMarkers);
        map.fitBounds(group.getBounds().pad(0.1));
    }
}

/**
 * Clear all markers from map
 */
function clearMap() {
    // Clear warehouse
    if (warehouseMarker) {
        map.removeLayer(warehouseMarker);
        warehouseMarker = null;
    }
    
    // Clear destinations
    destinationMarkers.forEach(marker => map.removeLayer(marker));
    destinationMarkers = [];
    
    // Clear clusters
    clearClusters();
    
    // Clear data arrays
    warehouse = null;
    destinations = [];
}

/**
 * Clear cluster visualizations
 */
function clearClusters() {
    // Remove all cluster markers
    clusterMarkers.forEach(marker => map.removeLayer(marker));
    clusterMarkers = [];
    
    // Remove legend if it exists
    if (legendControl) {
        map.removeControl(legendControl);
        legendControl = null;
    }
}

/**
 * Run clustering on the loaded preset
 */
function runClustering() {
    if (!warehouse || destinations.length < 2) {
        showNotification('Need a warehouse and at least 2 destinations for clustering', 'error');
        return;
    }
    
    // Get clustering parameters
    const eps = parseFloat(document.getElementById('eps-input').value);
    const minSamples = parseInt(document.getElementById('min-samples-input').value);
    
    if (isNaN(eps) || isNaN(minSamples) || eps <= 0 || minSamples < 1) {
        showNotification('Invalid clustering parameters', 'error');
        return;
    }
    
    // Combine all locations (warehouse + destinations) for clustering
    const allLocations = [warehouse, ...destinations];
    
    // Send data to server for clustering
    fetch('/run_clustering', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            locations: allLocations,
            eps: eps,
            min_samples: minSamples
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            // Clear previous clusters
            clearClusters();
            
            // Display the clusters
            visualizeClusters(data.result, allLocations);
            
            // Show clustering stats
            displayClusteringStats(data.result);
            
            showNotification('Clustering completed successfully', 'success');
        } else {
            showNotification('Error: ' + data.message, 'error');
        }
    })
    .catch(error => {
        console.error('Error running clustering:', error);
        showNotification('Failed to perform clustering', 'error');
    });
}

/**
 * Visualize the clustering results on the map
 */
function visualizeClusters(clusteringResult, allLocations) {
    // Get cluster labels
    const labels = clusteringResult.labels;
    
    // Get unique cluster labels (excluding noise points with -1)
    const uniqueClusters = [...new Set(labels.filter(l => l >= 0))];
    
    // Add circle markers for each location based on its cluster
    for (let i = 0; i < allLocations.length; i++) {
        const cluster = labels[i];
        const location = allLocations[i];
        
        // Choose marker style based on cluster
        let markerOptions;
        
        if (cluster === -1) {
            // Noise point (no cluster)
            markerOptions = {
                radius: 8,
                fillColor: '#999999',
                color: '#666666',
                weight: 1,
                opacity: 0.8,
                fillOpacity: 0.5
            };
        } else {
            // Clustered point
            const colorIndex = cluster % clusterColors.length;
            markerOptions = {
                radius: 10,
                fillColor: clusterColors[colorIndex],
                color: '#000',
                weight: 1,
                opacity: 1,
                fillOpacity: 0.7
            };
        }
        
        // Create the marker
        const marker = L.circleMarker(location, markerOptions).addTo(map);
        
        // Add popup information
        const pointType = (i === 0) ? 'Warehouse' : `Destination ${i}`;
        const clusterName = (cluster === -1) ? 'Noise (No Cluster)' : `Cluster ${cluster + 1}`;
        marker.bindTooltip(`${pointType}<br>Cluster: ${clusterName}`);
        
        clusterMarkers.push(marker);
    }
    
    // Add intersection points if available
    if (clusteringResult.intersections && clusteringResult.intersections.length > 0) {
        clusteringResult.intersections.forEach(intersection => {
            const marker = L.circleMarker(intersection.coords, {
                radius: 5,
                fillColor: '#000000',
                color: '#FFFFFF',
                weight: 1.5,
                opacity: 1,
                fillOpacity: 1
            }).addTo(map);
            
            marker.bindTooltip(`Intersection Point`);
            clusterMarkers.push(marker);
        });
    }
    
    // Add a legend to the map
    addClusterLegend(uniqueClusters);
}

/**
 * Add a legend showing cluster colors
 */
function addClusterLegend(uniqueClusters) {
    // Create legend control
    legendControl = L.control({position: 'bottomright'});
    
    legendControl.onAdd = function (map) {
        const div = L.DomUtil.create('div', 'legend');
        div.innerHTML = '<h4>Clusters</h4>';
        
        // Add entry for each cluster
        uniqueClusters.forEach(cluster => {
            const colorIndex = cluster % clusterColors.length;
            div.innerHTML += `
                <div class="legend-item">
                    <div class="legend-color" style="background-color: ${clusterColors[colorIndex]}"></div>
                    <div>Cluster ${cluster + 1}</div>
                </div>
            `;
        });
        
        // Add noise entry
        div.innerHTML += `
            <div class="legend-item">
                <div class="legend-color" style="background-color: #999999"></div>
                <div>Noise (No Cluster)</div>
            </div>
        `;
        
        return div;
    };
    
    legendControl.addTo(map);
}

/**
 * Display statistics about the clustering results
 */
function displayClusteringStats(clusteringResult) {
    const labels = clusteringResult.labels;
    
    // Get unique cluster labels (excluding noise)
    const uniqueClusters = [...new Set(labels.filter(l => l >= 0))];
    
    // Count points in each cluster
    const clusterCounts = {};
    labels.forEach(label => {
        if (label >= 0) {
            clusterCounts[label] = (clusterCounts[label] || 0) + 1;
        }
    });
    
    // Count noise points
    const noiseCount = labels.filter(l => l === -1).length;
    
    // Calculate percentage of points in clusters vs. noise
    const totalPoints = labels.length;
    const clusteredPoints = totalPoints - noiseCount;
    const clusteredPercentage = ((clusteredPoints / totalPoints) * 100).toFixed(1);
    
    // Generate stats HTML
    let statsHtml = `
        <h3>Clustering Results</h3>
        <p><strong>Total Locations:</strong> ${totalPoints}</p>
        <p><strong>Number of Clusters:</strong> ${uniqueClusters.length}</p>
        <p><strong>Clustered Points:</strong> ${clusteredPoints} (${clusteredPercentage}%)</p>
        <p><strong>Noise Points:</strong> ${noiseCount} (${(100 - parseFloat(clusteredPercentage)).toFixed(1)}%)</p>
        
        <h4>Cluster Details:</h4>
        <ul>
    `;
    
    // Add details for each cluster
    uniqueClusters.sort((a, b) => a - b);
    uniqueClusters.forEach(cluster => {
        statsHtml += `<li><strong>Cluster ${cluster + 1}:</strong> ${clusterCounts[cluster]} points</li>`;
    });
    
    statsHtml += '</ul>';
    
    // If there are intersections, list them
    if (clusteringResult.intersections && clusteringResult.intersections.length > 0) {
        statsHtml += `
            <h4>Intersection Points:</h4>
            <p>${clusteringResult.intersections.length} intersection points identified</p>
        `;
    }
    
    // Update the stats div
    document.getElementById('cluster-stats').innerHTML = statsHtml;
}

/**
 * Show notification message
 */
function showNotification(message, type = 'info') {
    const notification = document.getElementById('notification');
    const messageElement = document.getElementById('notification-message');
    
    // Set message and type
    messageElement.textContent = message;
    notification.className = `notification ${type}`;
    
    // Show notification
    notification.classList.remove('hidden');
    
    // Hide after 3 seconds
    setTimeout(() => {
        notification.classList.add('hidden');
    }, 3000);
}