const CheckpointManager = (function() {
    let _map = null;
    let _checkpointMarkers = [];
    let _selectedClusterId = null;
    let _selectedClusterName = null;
    let _editMode = false;
    let _currentClusterData = null;
    
    /**
     * Initialize the checkpoint manager
     * @returns {Object} Public API
     */
    function initialize() {
        if (!window.clusterMap) {
            Utils.debugLog("Map not available for checkpoint initialization");
            return false;
        }
        
        Utils.debugLog("CheckpointManager initializing with map from window.clusterMap");
        _map = window.clusterMap;

        const showCheckpointsToggle = document.getElementById('show-checkpoints');
        const generateBtn = document.getElementById('generate-checkpoints-btn');
        const editBtn = document.getElementById('toggle-edit-checkpoints-btn');
        const saveBtn = document.getElementById('save-checkpoints-btn');
        
        if (showCheckpointsToggle) {
            showCheckpointsToggle.addEventListener('change', function() {
                toggleVisibility(this.checked);
            });
        }
        
        if (generateBtn) {
            // Remove duplicates
            generateBtn.removeEventListener('click', handleGenerateClick);
            
            generateBtn.addEventListener('click', handleGenerateClick);
            Utils.debugLog('Generate checkpoints button handler attached');
        } else {
            Utils.debugLog('ERROR: Generate checkpoints button not found');
        }
        
        if (editBtn) {
            editBtn.addEventListener('click', function() {
                Utils.debugLog('Edit checkpoints button clicked');
                if (!_selectedClusterId) {
                    Utils.debugLog('ERROR: No cluster selected');
                    alert('Please select a cluster first');
                    return;
                }
                toggleEditMode();
            });
        }
        
        if (saveBtn) {
            saveBtn.addEventListener('click', function() {
                Utils.debugLog('Save checkpoints button clicked');
                saveCheckpoints();
            });
        }
        
        Utils.debugLog("Checkpoint manager initialized successfully");
        return true;
    }

    function toggleVisibility(visible) {
        if (!_map) {
            Utils.debugLog("ERROR: Map not available for toggling visibility");
            return;
        }
        
        _checkpointMarkers.forEach(marker => {
            if (marker) {
                if (visible) {
                    marker.addTo(_map);
                } else {
                    marker.remove();
                }
            }
        });
    }
    
    function loadCheckpoints(clusterId, clusterName) {
        Utils.debugLog(`Loading checkpoints for cluster ${clusterId}`);
        
        _selectedClusterId = clusterId;
        _selectedClusterName = clusterName || `Cluster ${clusterId}`;
        
        const url = `/checkpoint/cluster/${clusterId}/checkpoints`;
        
        Utils.debugLog(`Sending request to load checkpoints for cluster ${clusterId}`);
        
        fetch(url)
            .then(response => {
                Utils.debugLog(`Load checkpoints response status: ${response.status}`);
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                Utils.debugLog(`Checkpoint data received: ${JSON.stringify(data).substring(0, 100)}...`);
                
                if (!data.checkpoints || !Array.isArray(data.checkpoints)) {
                    Utils.debugLog(`No checkpoints found for this cluster`);
                    displayCheckpoints([]);
                    return;
                }
                
                Utils.debugLog(`Found ${data.checkpoints.length} checkpoints`);
                displayCheckpoints(data.checkpoints);
            })
            .catch(error => {
                Utils.debugLog(`Error loading checkpoints: ${error.message}`);
                displayCheckpoints([]);
            });
    }
    
    function toggleEditMode(forceState) {
        const editBtn = document.getElementById('toggle-edit-checkpoints-btn');
        const saveBtn = document.getElementById('save-checkpoints-btn');
        
        if (!editBtn || !saveBtn) {
            Utils.debugLog("ERROR: Edit or Save button not found");
            return;
        }
        e
        if (!_map && window.clusterMap) {
            _map = window.clusterMap;
            Utils.debugLog("Retrieved map from window.clusterMap in toggleEditMode");
        }
        
        if (!_map) {
            Utils.debugLog("ERROR: Map not available for toggling edit mode");
            return;
        }

        const turnOn = forceState !== undefined ? forceState : !_editMode;
        _editMode = turnOn;
        
        Utils.debugLog(`Setting edit mode to: ${_editMode}`);
        
        if (turnOn) {

            editBtn.classList.add('active');
            editBtn.innerHTML = '<i class="fas fa-times mr-1"></i> Cancel Edit';
            saveBtn.style.display = 'inline-block';
            document.body.classList.add('edit-mode');
            
            _checkpointMarkers.forEach(marker => {
                if (marker && marker.dragging) {
                    marker.options.draggable = true;
                    marker.dragging.enable();
                }
            });
            
            if (_map && _map.on) {
                _map.on('click', handleMapClick);
            }
            
            Utils.debugLog('Edit mode ON');
            Utils.showNotification('Checkpoint edit mode activated. Drag checkpoints to relocate them, click Save Changes when done.', 'info');
        } else {
            editBtn.classList.remove('active');
            editBtn.innerHTML = '<i class="fas fa-edit mr-1"></i> Edit Mode';
            saveBtn.style.display = 'none';
            
            document.body.classList.remove('edit-mode');
            
            if (_map && typeof _map.off === 'function') {
                _map.off('click', handleMapClick);
            }
            
            _checkpointMarkers.forEach(marker => {
                if (marker && marker.dragging) {
                    marker.options.draggable = false;
                    marker.dragging.disable();
                }
            });
            
            document.querySelectorAll('.checkpoint-item').forEach(item => {
                item.classList.remove('active-edit');
            });
            
            Utils.debugLog('Edit mode OFF');
        }
    }
    
    function handleMapClick(e) {
        if (!_editMode || !_selectedClusterId) return;
        
        Utils.debugLog(`Map clicked at ${e.latlng.lat.toFixed(6)}, ${e.latlng.lng.toFixed(6)}`);
        
        const newCheckpoint = {
            lat: e.latlng.lat,
            lon: e.latlng.lng,
            from_type: 'unclassified',
            to_type: 'residential',
            confidence: 0.7,
            id: `temp-${Date.now()}`, 
            source: 'manual'
        };
        
        const checkpoints = _checkpointMarkers
            .filter(m => m && m.checkpoint)
            .map(m => m.checkpoint);
        
        checkpoints.push(newCheckpoint);
        
        displayCheckpoints(checkpoints);

        Utils.showNotification('New checkpoint added. Click "Save Changes" to keep your changes.', 'info');
    }
    
    let initialized = false;
    function ensureInitialized() {
        if (!initialized && window.clusterMap) {
            initialized = initialize();
            return initialized;
        }
        return initialized;
    }
    
    // Initialize DOM 
    document.addEventListener('DOMContentLoaded', function() {
        Utils.debugLog("DOM loaded, waiting for map");
        
        const checkMapInterval = setInterval(() => {
            if (window.clusterMap) {
                Utils.debugLog("Map detected, initializing CheckpointManager");
                clearInterval(checkMapInterval);
                if (ensureInitialized()) {
                    Utils.debugLog("CheckpointManager initialized successfully");
                } else {
                    Utils.debugLog("Failed to initialize CheckpointManager");
                }
            }
        }, 500);
    });
    
    // API
    window.CheckpointManager = {
        loadCheckpoints: function(clusterId, clusterName) {
            if (ensureInitialized()) {
                loadCheckpoints(clusterId, clusterName);
            } else {
                Utils.debugLog("ERROR: Cannot load checkpoints, CheckpointManager not initialized");
            }
        },
        toggleVisibility: function(visible) {
            if (ensureInitialized()) {
                toggleVisibility(visible);
            } else {
                Utils.debugLog("ERROR: Cannot toggle visibility, CheckpointManager not initialized");
            }
        },
        generateCheckpoints: function() {
            if (ensureInitialized()) {
                generateCheckpoints();
            }
        },
        toggleEditMode: function(forceState) {
            if (ensureInitialized()) {
                toggleEditMode(forceState);
            }
        }
    };
    
    function displayCheckpoints(checkpoints) {
        Utils.debugLog(`Displaying ${checkpoints ? checkpoints.length : 0} checkpoints`);
        
        try {
            if (!checkpoints || !Array.isArray(checkpoints)) {
                Utils.debugLog("ERROR: Invalid checkpoints data received");
                return;
            }
            
            _checkpointMarkers.forEach(marker => marker.remove());
            _checkpointMarkers = [];
            
            const container = document.querySelector('#checkpoint-list .checkpoint-items');
            if (!container) {
                Utils.debugLog("ERROR: Checkpoint list container not found!");
                return;
            }
            
            container.innerHTML = '';
            Utils.debugLog("Cleared checkpoint container");

            checkpoints.forEach((cp, index) => {
                const checkpointNumber = index + 1;
                Utils.debugLog(`Processing checkpoint ${checkpointNumber}: ${cp.lat}, ${cp.lon}`);
                
                const cpItem = document.createElement('div');
                cpItem.className = 'checkpoint-item';
                cpItem.innerHTML = `
                    <h6>Checkpoint #${checkpointNumber}</h6>
                    <p>
                        <small>Coordinates: ${cp.lat.toFixed(6)}, ${cp.lon.toFixed(6)}</small><br>
                        <small>Road Types: ${cp.from_type || 'unknown'} → ${cp.to_type || 'residential'}</small><br>
                        <small>Confidence: ${Math.round((cp.confidence || 0.7) * 100)}%</small>
                    </p>
                    <div class="btn-group btn-group-sm">
                        <button class="btn btn-outline-primary btn-sm edit-checkpoint-btn" 
                                data-checkpoint-id="${cp.id}">
                            <i class="fas fa-edit"></i> Edit
                        </button>
                        <button class="btn btn-outline-danger btn-sm delete-checkpoint-btn" 
                                data-checkpoint-id="${cp.id}">
                            <i class="fas fa-trash"></i> Delete
                        </button>
                    </div>
                `;
                container.appendChild(cpItem);
                Utils.debugLog(`Added checkpoint ${checkpointNumber} to sidebar`);
                
                if (!_map) {
                    Utils.debugLog("ERROR: Map not available for adding checkpoint markers");
                    return;
                }
                
                const confidence = cp.confidence || 0.7;

                const r = Math.floor(255 * (1 - confidence));
                const g = Math.floor(200 * confidence);
                const color = `rgb(${r}, ${g}, 0)`;
                
                try {
                    const marker = L.marker([cp.lat, cp.lon], {
                        icon: Utils.createMarkerIcon('checkpoint', {
                            number: checkpointNumber,
                            color: color
                        }),
                        draggable: _editMode
                    }).addTo(_map);
                    
                    marker.bindPopup(`
                        <strong>Checkpoint #${checkpointNumber}</strong><br>
                        <strong>Road transition:</strong> ${cp.from_type || 'unknown'} → ${cp.to_type || 'residential'}<br>
                        <strong>Confidence:</strong> ${Math.round(confidence * 100)}%
                    `, {
                        autoPan: false
                    });
                    
                    marker.checkpoint = cp;
                    marker.checkpointNumber = checkpointNumber;
                    
                    _checkpointMarkers.push(marker);
                    
                    Utils.debugLog(`Added checkpoint marker #${checkpointNumber} at ${cp.lat.toFixed(6)}, ${cp.lon.toFixed(6)}`);
                } catch (mapError) {
                    Utils.debugLog(`ERROR creating marker: ${mapError.message}`);
                }
            });
            
            addCheckpointButtonHandlers();
            Utils.debugLog(`Successfully displayed ${checkpoints.length} checkpoints`);
        } catch (error) {
            Utils.debugLog(`CRITICAL ERROR in displayCheckpoints: ${error.message}`);
            console.error("Error displaying checkpoints:", error);
            
            const container = document.querySelector('#checkpoint-list .checkpoint-items');
            if (container) {
                container.innerHTML = `
                    <p class="text-danger">Error displaying checkpoints: ${error.message}</p>
                    <p class="text-muted">Try refreshing the page</p>
                `;
            }
        }
    }

    function addCheckpointButtonHandlers() {
        try {
            document.querySelectorAll('.edit-checkpoint-btn').forEach(btn => {
                btn.addEventListener('click', function() {
                    const checkpointId = this.dataset.checkpointId;
                    editCheckpoint(checkpointId);
                });
            });
            
            document.querySelectorAll('.delete-checkpoint-btn').forEach(btn => {
                btn.addEventListener('click', function() {
                    const checkpointId = this.dataset.checkpointId;
                    deleteCheckpoint(checkpointId);
                });
            });
            
            const saveBtn = document.getElementById('save-checkpoints-btn');
            if (saveBtn) {
                saveBtn.removeEventListener('click', saveCheckpoints);
                saveBtn.addEventListener('click', saveCheckpoints);
            }
            
            Utils.debugLog("Added event handlers to checkpoint buttons");
        } catch (error) {
            Utils.debugLog(`ERROR adding button handlers: ${error.message}`);
        }
    }

    // edit a specific checkpoint
    function editCheckpoint(checkpointId) {
        Utils.debugLog(`Edit checkpoint ${checkpointId} clicked`);
        
        const marker = _checkpointMarkers.find(m => 
            m && m.checkpoint && m.checkpoint.id == checkpointId);
        
        if (marker) {
            toggleEditMode(true);
            
            marker.options.draggable = true;
            if (marker.dragging) marker.dragging.enable();
            
            const icon = marker._icon;
            if (icon) {
                icon.style.transition = 'transform 0.3s';
                icon.style.transform = 'scale(1.5)';
                setTimeout(() => { 
                    if (icon.style) icon.style.transform = 'scale(1)'; 
                }, 300);
            }

            document.querySelectorAll('.checkpoint-item').forEach(item => {
                item.classList.remove('active-edit');
            });
            
            const checkpointItem = document.querySelector(`.checkpoint-item:nth-child(${marker.checkpointNumber})`);
            if (checkpointItem) {
                checkpointItem.classList.add('active-edit');
                checkpointItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
            
            Utils.showNotification('Drag the checkpoint to adjust its position, then click Save Changes', 'info');
        } else {
            Utils.debugLog(`ERROR: Could not find marker for checkpoint ${checkpointId}`);
        }
    }

    function deleteCheckpoint(checkpointId) {
        Utils.debugLog(`Delete checkpoint ${checkpointId} clicked`);
        
        if (!confirm('Are you sure you want to delete this checkpoint?')) {
            return;
        }
        
        const btnElement = document.querySelector(`.delete-checkpoint-btn[data-checkpoint-id="${checkpointId}"]`);
        if (btnElement) {
            const originalHtml = btnElement.innerHTML;
            btnElement.disabled = true;
            btnElement.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        }

        fetch(`/checkpoint/checkpoint/delete_checkpoint/${checkpointId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        })
        .then(response => {
            Utils.debugLog(`Delete checkpoint response status: ${response.status}`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            Utils.debugLog(`Delete checkpoint response: ${JSON.stringify(data)}`);
            
            if (data.status === 'success') {
                const markerIndex = _checkpointMarkers.findIndex(m => 
                    m && m.checkpoint && m.checkpoint.id == checkpointId);
                    
                if (markerIndex >= 0) {
                    _checkpointMarkers[markerIndex].remove();
                    _checkpointMarkers.splice(markerIndex, 1);
                }
                
                const checkpointItem = document.querySelector(`.checkpoint-item:has(.delete-checkpoint-btn[data-checkpoint-id="${checkpointId}"])`);
                if (checkpointItem) {
                    checkpointItem.remove();
                }
                
                Utils.showNotification('Checkpoint deleted successfully', 'success');
                
                loadCheckpoints(_selectedClusterId, _selectedClusterName);
            } else {
                Utils.showNotification(`Error: ${data.message}`, 'error');
                
                if (btnElement) {
                    btnElement.disabled = false;
                    btnElement.innerHTML = originalHtml;
                }
            }
        })
        .catch(error => {
            Utils.debugLog(`ERROR deleting checkpoint: ${error.message}`);
            Utils.showNotification('Error deleting checkpoint', 'error');
            
            if (btnElement) {
                btnElement.disabled = false;
                btnElement.innerHTML = originalHtml;
            }
        });
    }

    function saveCheckpoints() {
        Utils.debugLog('Save checkpoints button clicked');
        
        if (!_selectedClusterId) {
            Utils.showNotification('No cluster selected', 'error');
            return;
        }
        
        const checkpoints = _checkpointMarkers
            .filter(marker => marker && marker.getLatLng && marker.checkpoint)
            .map(marker => {
                const position = marker.getLatLng();
                const cp = marker.checkpoint || {};
                
                return {
                    id: cp.id,
                    lat: position.lat,
                    lon: position.lng,
                    from_type: cp.from_type || 'unclassified',
                    to_type: cp.to_type || 'residential',
                    confidence: cp.confidence || 0.7,
                };
            });
        
        if (checkpoints.length === 0) {
            Utils.showNotification('No checkpoints to save', 'warning');
            return;
        }
        
        Utils.debugLog(`Saving ${checkpoints.length} checkpoints for cluster ${_selectedClusterId}`);
        
        const saveBtn = document.getElementById('save-checkpoints-btn');
        if (saveBtn) {
            saveBtn.disabled = true;
            saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i> Saving...';
        }

        fetch(`/checkpoint/checkpoint/save_checkpoints/${_selectedClusterId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ checkpoints: checkpoints })
        })
        .then(response => {
            Utils.debugLog(`Save checkpoints response status: ${response.status}`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            Utils.debugLog(`Save checkpoints response: ${JSON.stringify(data)}`);
            
            if (data.status === 'success') {
                Utils.showNotification('Checkpoints saved successfully', 'success');
                
                // Turn off edit mode
                toggleEditMode(false);
                
                loadCheckpoints(_selectedClusterId, _selectedClusterName);
            } else {
                Utils.showNotification(`Error: ${data.message}`, 'error');
            }
        })
        .catch(error => {
            console.error('Error saving checkpoints:', error);
            Utils.debugLog(`ERROR saving checkpoints: ${error.message}`);
            Utils.showNotification('Error saving checkpoints', 'error');
        })
        .finally(() => {
            if (saveBtn) {
                saveBtn.disabled = false;
                saveBtn.innerHTML = '<i class="fas fa-save mr-1"></i> Save Changes';
            }
        });
    }

    function generateCheckpoints() {
        if (!_selectedClusterId) {
            Utils.showNotification('Please select a cluster first', 'warning');
            Utils.debugLog('ERROR: No cluster selected for checkpoint generation');
            return;
        }
        
        // Show loading state
        const btn = document.getElementById('generate-checkpoints-btn');
        const originalText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i> Generating...';
        
        const checkpointItems = document.querySelector('#checkpoint-list .checkpoint-items');
        if (checkpointItems) {
            checkpointItems.innerHTML = '<p class="text-muted"><i class="fas fa-spinner fa-spin"></i> Generating checkpoints...</p>';
        }
        
        Utils.debugLog(`Sending request to generate checkpoints for cluster ${_selectedClusterId}`);
        
        fetch(`/clustering/generate_checkpoints/${_selectedClusterId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => {
            Utils.debugLog(`Generate checkpoints response status: ${response.status}`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            Utils.debugLog(`Generate checkpoints response data: ${JSON.stringify(data).substring(0, 100)}...`);
            
            if (data.status === 'success') {
                Utils.showNotification('Checkpoints generated successfully', 'success');
                Utils.debugLog('Checkpoint generation successful, reloading checkpoints');
                
                loadCheckpoints(_selectedClusterId, _selectedClusterName);
            } else {
                Utils.debugLog(`ERROR: Checkpoint generation failed: ${data.message || 'Unknown error'}`);
                Utils.showNotification(data.message || 'Error generating checkpoints', 'error');
                
                if (checkpointItems) {
                    checkpointItems.innerHTML = 
                        `<p class="text-danger">Error generating checkpoints: ${data.message || 'Unknown error'}</p>`;
                }
            }
        })
        .catch(error => {
            Utils.debugLog(`CRITICAL ERROR: Checkpoint generation request failed: ${error.message}`);
            console.error('Error generating checkpoints:', error);
            
            Utils.showNotification(`Failed to generate checkpoints: ${error.message}`, 'error');
            
            if (checkpointItems) {
                checkpointItems.innerHTML = 
                    `<p class="text-danger">Error generating checkpoints: ${error.message}</p>`;
            }
        })
        .finally(() => {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        });
    }

    function handleGenerateClick() {
        Utils.debugLog('Generate checkpoints button clicked');
        if (!_selectedClusterId) {
            Utils.debugLog('ERROR: No cluster selected');
            Utils.showNotification('Please select a cluster first', 'warning');
            return;
        }
        generateCheckpoints();
    }
})();