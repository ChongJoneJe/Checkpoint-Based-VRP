/**
 * Cluster Management Module
 * Handles all cluster-related functionality
 */
const ClusterManager = (function() {
    // Private module variables
    let map;
    let clusterMarkers = [];
    let warehouseMarker = null;
    let currentPreset = null;
    
    // Colors for clusters
    const clusterColors = [
        '#FF5733', '#33A8FF', '#45FF33', '#F033FF', '#FFE033', 
        '#33FFF6', '#FF33A8', '#8C33FF', '#FF8C33', '#33FF8C', 
        '#FF3333', '#3361FF', '#33FF61', '#DA33FF', '#FFDA33', 
        '#33FFE0', '#FF3380', '#8CFF33', '#FF6E33', '#338CFF'
    ];
    
    // Helper function to get cluster color
    function getClusterColor(clusterId) {
        const index = typeof clusterId === 'string' 
            ? clusterId.split('').reduce((a,b)=>a+b.charCodeAt(0), 0) % clusterColors.length
            : clusterId % clusterColors.length;
        
        return clusterColors[index];
    }

    // Initialize the map - refactored to use Utils
    function initializeMap() {
        // Create map with global name "clusterMap" for checkpoint use
        try {
            map = Utils.createMap('map', [3.1390, 101.6869], 13, { 
                globalName: 'clusterMap' 
            });
            
            if (!map) {
                console.error("Failed to initialize map");
                return null;
            }
            
            // Ensure global reference is set
            window.clusterMap = map;
            return map;
        } catch (e) {
            console.error("Error initializing map:", e);
            // Fallback to original implementation if Utils.createMap fails
            map = L.map('map').setView([3.1390, 101.6869], 13);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            }).addTo(map);
            window.clusterMap = map;
            return map;
        }
    }

    // Load clusters for a preset
    function loadClusters(presetId = 'all') {
        Utils.debugLog(`Loading clusters for preset: ${presetId}`);
        
        // Clear existing markers
        clusterMarkers.forEach(marker => marker.remove());
        clusterMarkers = [];
        
        if (warehouseMarker) {
            warehouseMarker.remove();
            warehouseMarker = null;
        }
        
        currentPreset = presetId;
        
        // Show loading indicator
        document.getElementById('cluster-list').innerHTML = 
            '<div class="loading"><i class="fas fa-spinner fa-spin"></i> Loading clusters...</div>';
        
        // Build URL with preset parameter if not 'all'
        const url = presetId === 'all' ? 
            '/clustering/get_clusters' : 
            `/clustering/get_clusters?preset_id=${encodeURIComponent(presetId)}`;
        
        fetch(url)
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    displayClusters(data.clusters);
                    
                    // Display warehouse if any
                    if (data.warehouse) {
                        displayWarehouse(data.warehouse);
                    }
                    
                    // Update stats if available
                    if (data.stats) {
                        updateClusterStats(data.stats);
                    }
                } else {
                    Utils.debugLog(`Error loading clusters: ${data.message}`);
                    document.getElementById('cluster-list').innerHTML = 
                        '<p class="error">Error loading clusters: ' + data.message + '</p>';
                }
            })
            .catch(error => {
                console.error('Error loading clusters:', error);
                Utils.debugLog(`Error fetching clusters: ${error.message}`);
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
            const clusterColor = getClusterColor(clusterId);
            
            // Use the cluster name directly
            const displayName = cluster.name || `Cluster ${clusterId}`;
            
            // Create clickable cluster item
            const clusterElement = document.createElement('div');
            clusterElement.className = 'cluster-item';
            clusterElement.setAttribute('data-cluster-id', clusterId);
            
            // Add click handler to select this cluster
            clusterElement.addEventListener('click', () => selectCluster(clusterId));
            
            // Simplified cluster listing in sidebar
            clusterElement.innerHTML = `
                <div class="cluster-header">
                    <span class="color-sample" style="background-color: ${clusterColor}"></span>
                    <strong>${displayName}</strong> (${cluster.locations.length} locations)
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
                    Cluster: ${displayName}<br>
                    ${displayLocationInfo(location)}
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

    // Helper function for displaying location info
    function displayLocationInfo(location) {
        return `
            <div class="location-details">
                ${location.street ? `<p>Street: ${location.street}</p>` : ''}
                ${location.development ? `<p>Development: ${location.development}</p>` : ''}
                ${location.neighborhood ? `<p>Neighborhood: ${location.neighborhood}</p>` : ''}
                <p>Coordinates: ${location.lat.toFixed(5)}, ${location.lon.toFixed(5)}</p>
            </div>
        `;
    }

    // Select a cluster and trigger checkpoint loading
    function selectCluster(clusterId) {
        Utils.debugLog(`Selecting cluster ${clusterId}`);
        
        // Highlight the selected cluster
        document.querySelectorAll('.cluster-item').forEach(item => {
            item.classList.remove('active');
        });
        
        const selectedItem = document.querySelector(`.cluster-item[data-cluster-id="${clusterId}"]`);
        if (selectedItem) {
            selectedItem.classList.add('active');
        }
        
        // Get the name of the selected cluster for display
        const clusterName = selectedItem ? 
            selectedItem.querySelector('.cluster-header strong').textContent : 
            `Cluster ${clusterId}`;
            
        // FIX: CheckpointManager access
        if (window.CheckpointManager) {
            Utils.debugLog(`Calling CheckpointManager.loadCheckpoints for cluster ${clusterId}`);
            window.CheckpointManager.loadCheckpoints(clusterId, clusterName);
        } else {
            console.error("CheckpointManager not available");
            Utils.debugLog("ERROR: CheckpointManager not available");
        }
    }

    // Display warehouse on the map
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
                ${warehouse.development ? `<p>Development: ${warehouse.development}</p>` : ''}
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
    function updateClusterStats(stats) {
        if (stats) {
            document.getElementById('total-locations').textContent = stats.total_locations || 0;
            document.getElementById('num-clusters').textContent = stats.num_clusters || 0;
            document.getElementById('noise-points').textContent = stats.noise_points || 0;
        }
    }

    // FIX: Update the loadPresets function to properly handle errors
    function loadPresets() {
        Utils.debugLog("Loading presets");
        
        // Always use the correct URL
        fetch('/presets/get_presets')
            .then(response => {
                Utils.debugLog(`Presets response status: ${response.status}`);
                if (!response.ok) {
                    throw new Error(`HTTP error ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                Utils.debugLog(`Raw presets data: ${JSON.stringify(data).substring(0, 100)}...`);
                
                // Check for expected response format
                if (!data || !data.presets || !Array.isArray(data.presets)) {
                    Utils.debugLog(`Invalid presets data format: ${JSON.stringify(data).substring(0, 100)}`);
                    return;
                }
                
                Utils.debugLog(`Loaded ${data.presets.length} presets`);
                
                const presetSelect = document.getElementById('preset-select');
                if (!presetSelect) {
                    Utils.debugLog("Preset select element not found");
                    return;
                }
                
                // Keep the "All Locations" option
                presetSelect.innerHTML = '<option value="all">All Locations</option>';
                
                // Add preset options
                if (data.presets.length > 0) {
                    data.presets.forEach(preset => {
                        const option = document.createElement('option');
                        option.value = preset.id;
                        option.textContent = preset.name;
                        presetSelect.appendChild(option);
                        Utils.debugLog(`Added preset: ${preset.name} (ID: ${preset.id})`);
                    });
                }
            })
            .catch(error => {
                Utils.debugLog(`Failed to load presets: ${error.message}`);
            });
    }

    // Initialize everything
    function initialize() {
        // Set up the map first
        map = initializeMap();
        if (!map) {
            Utils.debugLog("Failed to initialize map");
            return false;
        }
        
        // Set up preset selector
        const presetSelect = document.getElementById('preset-select');
        if (presetSelect) {
            presetSelect.addEventListener('change', function() {
                loadClusters(this.value);
            });
        }
        
        // FIX: Load presets immediately
        loadPresets();
        
        // Load initial clusters
        loadClusters();
        
        // Return success
        return true;
    }
    
    // Public API
    return {
        initialize: initialize,
        map: () => map,
        selectCluster: selectCluster,
        loadClusters: loadClusters,
        getClusterColor: getClusterColor,
        loadPresets: loadPresets 
    };
})();