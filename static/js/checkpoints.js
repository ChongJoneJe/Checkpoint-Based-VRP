// Global variables
let checkpointMarkers = [];
let editMode = false;
let selectedClusterId = null;
let currentClusterData = null;

// Initialize checkpoints functionality
function initCheckpoints(map) {
    // Set up event listeners for the checkpoint controls
    document.getElementById('show-checkpoints').addEventListener('change', function() {
        toggleCheckpointVisibility(this.checked);
    });
    
    document.getElementById('generate-checkpoints-btn').addEventListener('click', function() {
        generateCheckpoints();
    });
    
    document.getElementById('toggle-edit-checkpoints-btn').addEventListener('click', function() {
        toggleEditMode();
    });
    
    document.getElementById('save-checkpoints-btn').addEventListener('click', function() {
        saveCheckpoints();
    });
    
    // Function definitions
    function toggleCheckpointVisibility(visible) {
        checkpointMarkers.forEach(marker => {
            if (visible) {
                marker.addTo(map);
            } else {
                marker.remove();
            }
        });
    }
    
    function loadCheckpoints(clusterId) {
        // Clear existing checkpoints
        checkpointMarkers.forEach(marker => marker.remove());
        checkpointMarkers = [];
        
        selectedClusterId = clusterId;
        
        if (!clusterId) {
            document.querySelector('#checkpoint-list .checkpoint-items').innerHTML = 
                '<p class="text-muted">Select a cluster to view checkpoints</p>';
            return;
        }
        
        // Show loading indicator
        document.querySelector('#checkpoint-list .checkpoint-items').innerHTML = 
            '<p class="text-muted"><i class="fas fa-spinner fa-spin"></i> Loading checkpoints...</p>';
        
        // Fetch checkpoints for the selected cluster
        fetch(`/clustering/checkpoints/${clusterId}`)
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    currentClusterData = data;
                    
                    // Check if we have checkpoints
                    if (data.checkpoints && data.checkpoints.length > 0) {
                        displayCheckpoints(data.cluster, data.checkpoints);
                        updateCheckpointList(data.checkpoints);
                    } else {
                        document.querySelector('#checkpoint-list .checkpoint-items').innerHTML = 
                            '<p class="text-muted">No checkpoints detected. Click "Auto-Generate" to detect access points.</p>';
                    }
                } else {
                    showNotification(data.message, 'error');
                    document.querySelector('#checkpoint-list .checkpoint-items').innerHTML = 
                        '<p class="text-danger">Error loading checkpoints</p>';
                }
            })
            .catch(error => {
                console.error('Error loading checkpoints:', error);
                showNotification('Failed to load checkpoints', 'error');
                document.querySelector('#checkpoint-list .checkpoint-items').innerHTML = 
                    '<p class="text-danger">Error loading checkpoints</p>';
            });
    }
    
    function displayCheckpoints(cluster, checkpoints) {
        const showCheckpoints = document.getElementById('show-checkpoints').checked;
        if (!showCheckpoints) return;
        
        checkpoints.forEach(cp => {
            const marker = createCheckpointMarker(cp, cluster);
            checkpointMarkers.push(marker);
        });
    }
    
    function createCheckpointMarker(checkpoint, cluster) {
        // Default confidence value if not provided
        const confidence = checkpoint.confidence || 0.7;
        
        // Color is based on confidence (red → yellow → green)
        const color = getColorFromConfidence(confidence);
        
        // Label shows the source of this checkpoint
        const sourceLabel = getSourceLabel(checkpoint.source);
        
        // Create a custom marker
        const marker = L.marker([checkpoint.lat, checkpoint.lon], {
            icon: L.divIcon({
                className: 'checkpoint-marker',
                html: `<div class="checkpoint-icon" style="background-color: ${color};">
                        <i class="fas fa-shield-alt"></i>
                      </div>`,
                iconSize: [24, 24],
                iconAnchor: [12, 12]
            }),
            draggable: editMode
        }).addTo(map);
        
        // Add popup with checkpoint info
        marker.bindPopup(`
            <strong>Security Checkpoint</strong><br>
            <strong>Road transition:</strong> ${checkpoint.from_road_type || 'unknown'} → ${checkpoint.to_road_type || 'residential'}<br>
            <strong>Confidence:</strong> ${Math.round(confidence * 100)}%<br>
            <strong>Source:</strong> ${sourceLabel}<br>
            ${editMode ? '<button class="btn btn-sm btn-danger remove-checkpoint">Remove</button>' : ''}
        `);
        
        // Add reference to the checkpoint data
        marker.checkpoint = checkpoint;
        
        // Connect to cluster center with a dashed line
        if (cluster && cluster.centroid_lat && cluster.centroid_lon) {
            const line = L.polyline([
                [checkpoint.lat, checkpoint.lon],
                [cluster.centroid_lat, cluster.centroid_lon]
            ], {
                color: color,
                weight: 2,
                opacity: 0.6,
                dashArray: '5, 5'
            }).addTo(map);
            
            // Add to markers array so we can remove it later
            checkpointMarkers.push(line);
        }
        
        // Add event listeners for edit mode
        if (editMode) {
            marker.on('dragend', function() {
                const pos = marker.getLatLng();
                checkpoint.lat = pos.lat;
                checkpoint.lon = pos.lng;
                updateCheckpointList(checkpointMarkers.filter(m => m instanceof L.Marker).map(m => m.checkpoint));
            });
            
            marker.on('popupopen', function() {
                const btn = document.querySelector('.remove-checkpoint');
                if (btn) {
                    btn.addEventListener('click', function() {
                        removeCheckpoint(marker);
                    });
                }
            });
        }
        
        return marker;
    }
    
    function getColorFromConfidence(confidence) {
        // Linear gradient from red (0) to green (1)
        const r = Math.floor(255 * (1 - confidence));
        const g = Math.floor(200 * confidence);
        return `rgb(${r}, ${g}, 0)`;
    }
    
    function getSourceLabel(source) {
        // Translate source code to human-readable label
        switch(source) {
            case 'topology_bottleneck': 
                return 'Road Network Bottleneck';
            case 'betweenness_centrality': 
                return 'Network Centrality Analysis';
            case 'osm_barrier': 
                return 'OpenStreetMap Barrier Tag';
            case 'fallback_direction': 
                return 'Directional Fallback';
            case 'manual': 
                return 'Manually Placed';
            default: 
                return source || 'Unknown';
        }
    }
    
    function updateCheckpointList(checkpoints) {
        const container = document.querySelector('#checkpoint-list .checkpoint-items');
        
        if (!checkpoints || checkpoints.length === 0) {
            container.innerHTML = '<p class="text-muted">No checkpoints detected for this cluster</p>';
            return;
        }
        
        let html = '';
        checkpoints.forEach((cp, index) => {
            const confidence = cp.confidence || 0.7;
            const color = getColorFromConfidence(confidence);
            const sourceLabel = getSourceLabel(cp.source);
            
            html += `
                <div class="checkpoint-item" data-index="${index}">
                    <div class="checkpoint-color-sample" style="background-color: ${color};"></div>
                    <div class="checkpoint-details">
                        <span class="checkpoint-name">Checkpoint ${index + 1}</span>
                        <span class="checkpoint-source">${sourceLabel}</span>
                    </div>
                    <span class="badge badge-${confidence > 0.8 ? 'success' : confidence > 0.5 ? 'warning' : 'danger'} ml-auto">
                        ${Math.round(confidence * 100)}%
                    </span>
                </div>
            `;
        });
        
        container.innerHTML = html;
    }
    
    function toggleEditMode() {
        editMode = !editMode;
        
        // Update UI
        document.getElementById('toggle-edit-checkpoints-btn').innerHTML = 
            editMode ? '<i class="fas fa-times mr-1"></i> Cancel' : '<i class="fas fa-edit mr-1"></i> Edit Mode';
        
        document.getElementById('save-checkpoints-btn').style.display = 
            editMode ? 'inline-block' : 'none';
        
        // Update markers
        checkpointMarkers.forEach(marker => {
            if (marker instanceof L.Marker) {
                marker.setDraggable(editMode);
                // Refresh popup content
                const content = marker.getPopup().getContent();
                if (editMode && !content.includes('Remove')) {
                    marker.setPopupContent(content.replace('</div>', '</div><button class="btn btn-sm btn-danger remove-checkpoint">Remove</button>'));
                } else if (!editMode && content.includes('Remove')) {
                    marker.setPopupContent(content.replace('<button class="btn btn-sm btn-danger remove-checkpoint">Remove</button>', ''));
                }
            }
        });
        
        // Show instruction if in edit mode
        if (editMode) {
            showNotification('Click on the map to add checkpoints, drag to move them', 'info');
            
            // Add click handler for adding new checkpoints
            map.on('click', addNewCheckpoint);
        } else {
            // Remove click handler
            map.off('click', addNewCheckpoint);
        }
    }
    
    function addNewCheckpoint(e) {
        if (!editMode || !selectedClusterId) return;
        
        // Create a new checkpoint object
        const checkpoint = {
            lat: e.latlng.lat,
            lon: e.latlng.lng,
            from_type: 'unclassified', 
            to_type: 'residential',
            confidence: 0.7,
            source: 'manual'
        };
        
        // Create marker
        const marker = createCheckpointMarker(checkpoint, currentClusterData.cluster);
        checkpointMarkers.push(marker);
        
        // Update the list
        updateCheckpointList(checkpointMarkers.filter(m => m instanceof L.Marker).map(m => m.checkpoint));
    }
    
    function removeCheckpoint(marker) {
        // Remove from map
        marker.remove();
        
        // Remove from array
        const index = checkpointMarkers.indexOf(marker);
        if (index > -1) {
            checkpointMarkers.splice(index, 1);
        }
        
        // Remove any connecting lines too
        checkpointMarkers = checkpointMarkers.filter(m => {
            if (m instanceof L.Polyline) {
                const points = m.getLatLngs();
                if (points.length === 2) {
                    // Check if this line connects to the marker we're removing
                    if ((points[0].lat === marker.getLatLng().lat && points[0].lng === marker.getLatLng().lng) ||
                        (points[1].lat === marker.getLatLng().lat && points[1].lng === marker.getLatLng().lng)) {
                        m.remove();
                        return false;
                    }
                }
            }
            return true;
        });
        
        // Update the list
        updateCheckpointList(checkpointMarkers.filter(m => m instanceof L.Marker).map(m => m.checkpoint));
    }
    
    function saveCheckpoints() {
        if (!selectedClusterId) {
            showNotification('No cluster selected', 'warning');
            return;
        }
        
        // Get checkpoint data from markers
        const checkpoints = checkpointMarkers
            .filter(m => m instanceof L.Marker)
            .map(marker => {
                const cp = marker.checkpoint;
                return {
                    lat: cp.lat,
                    lon: cp.lon,
                    from_type: cp.from_type || 'unknown',
                    to_type: cp.to_type || 'residential',
                    confidence: cp.confidence || 0.7,
                    source: cp.source || 'manual'
                };
            });
        
        // Show loading state
        const saveBtn = document.getElementById('save-checkpoints-btn');
        const originalSaveText = saveBtn.innerHTML;
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i> Saving...';
        
        // Send to server
        fetch(`/clustering/checkpoints/${selectedClusterId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                checkpoints: checkpoints
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                showNotification(data.message, 'success');
                toggleEditMode(); // Exit edit mode
            } else {
                showNotification(data.message, 'error');
            }
        })
        .catch(error => {
            console.error('Error saving checkpoints:', error);
            showNotification('Failed to save checkpoints', 'error');
        })
        .finally(() => {
            // Restore button state
            saveBtn.disabled = false;
            saveBtn.innerHTML = originalSaveText;
        });
    }
    
    function generateCheckpoints() {
        if (!selectedClusterId) {
            showNotification('Please select a cluster first', 'warning');
            return;
        }
        
        // Show loading state
        const btn = document.getElementById('generate-checkpoints-btn');
        const originalText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i> Generating...';
        
        // Clear existing checkpoints
        checkpointMarkers.forEach(marker => marker.remove());
        checkpointMarkers = [];
        
        fetch('/clustering/generate_checkpoints', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                cluster_id: selectedClusterId
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                showNotification(data.message, 'success');
                
                // Refresh checkpoints
                loadCheckpoints(selectedClusterId);
            } else {
                showNotification(data.message, 'error');
                document.querySelector('#checkpoint-list .checkpoint-items').innerHTML = 
                    '<p class="text-danger">Error generating checkpoints</p>';
            }
        })
        .catch(error => {
            console.error('Error generating checkpoints:', error);
            showNotification('Failed to generate checkpoints', 'error');
            document.querySelector('#checkpoint-list .checkpoint-items').innerHTML = 
                '<p class="text-danger">Error generating checkpoints</p>';
        })
        .finally(() => {
            // Restore button state
            btn.disabled = false;
            btn.innerHTML = originalText;
        });
    }
    
    // Return public methods
    return {
        loadCheckpoints: loadCheckpoints
    };
}

// Set up the checkpoint functionality when the document is ready
document.addEventListener('DOMContentLoaded', function() {
    // Check if we're on the clusters page with a map
    const mapElement = document.getElementById('map');
    if (!mapElement) return;
    
    // Wait for the map to be initialized
    const waitForMap = setInterval(function() {
        if (window.clusterMap) {
            clearInterval(waitForMap);
            
            // Initialize checkpoints module
            window.checkpointsModule = initCheckpoints(window.clusterMap);
            
            // Set up cluster selection to load checkpoints
            const observer = new MutationObserver(function(mutations) {
                setupClusterClickHandlers();
            });
            
            const clusterList = document.getElementById('cluster-list');
            if (clusterList) {
                observer.observe(clusterList, { childList: true, subtree: true });
                setupClusterClickHandlers();
            }
        }
    }, 100);
    
    function setupClusterClickHandlers() {
        document.querySelectorAll('.cluster-item').forEach(item => {
            item.addEventListener('click', function() {
                const clusterId = this.dataset.clusterId;
                if (clusterId && window.checkpointsModule) {
                    window.checkpointsModule.loadCheckpoints(parseInt(clusterId));
                }
            });
        });
    }
});