// Map and location management for the VRP application

let map;
let locationMode = 'destination';  // Default mode
let warehouse = null;
let destinations = [];
let warehouseMarker = null;
let destinationMarkers = [];

/**
 * Initialize the map with given center coordinates
 */
function initMap(lat, lng) {
    map = L.map('map').setView([lat, lng], 13);
    
    // Add OpenStreetMap tiles
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);
    
    // Add scale control
    L.control.scale().addTo(map);
    
    // Setup event listeners for buttons
    document.getElementById('warehouse-btn').addEventListener('click', () => setLocationMode('warehouse'));
    document.getElementById('destination-btn').addEventListener('click', () => setLocationMode('destination'));
    document.getElementById('clear-btn').addEventListener('click', clearSelections);
    document.getElementById('save-btn').addEventListener('click', saveLocations);
    
    // Add click handler to the map
    map.on('click', handleMapClick);
    
    // Add preset management event listeners
    document.getElementById('save-preset-btn').addEventListener('click', savePreset);
    document.getElementById('apply-preset-btn').addEventListener('click', applySelectedPreset);
    document.getElementById('delete-preset-btn').addEventListener('click', deleteSelectedPreset);
    
    // Load available presets
    loadPresets();
}

/**
 * Set the location selection mode (warehouse or destination)
 */
function setLocationMode(mode) {
    locationMode = mode;
    
    // Update button styling to show active mode
    document.getElementById('warehouse-btn').classList.toggle('active', mode === 'warehouse');
    document.getElementById('destination-btn').classList.toggle('active', mode === 'destination');
    
    // Update cursor to indicate active mode
    document.getElementById('map').style.cursor = 'crosshair';
}

/**
 * Handle clicks on the map
 */
function handleMapClick(e) {
    const lat = e.latlng.lat;
    const lng = e.latlng.lng;
    
    if (locationMode === 'warehouse') {
        setWarehouse(lat, lng);
    } else {
        addDestination(lat, lng);
    }
}

/**
 * Set the warehouse location
 */
function setWarehouse(lat, lng) {
    // Remove existing warehouse marker if any
    if (warehouseMarker) {
        map.removeLayer(warehouseMarker);
    }
    
    // Store new warehouse location
    warehouse = [lat, lng];
    
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
    
    // Update sidebar display
    document.getElementById('warehouse-display').innerHTML = `
        <h3>Warehouse</h3>
        <p class="coords">${lat.toFixed(6)}, ${lng.toFixed(6)}</p>
    `;
    
    // Switch to destination mode after setting warehouse
    setLocationMode('destination');
    
    showNotification('Warehouse location set!');
}

/**
 * Add a destination location
 */
function addDestination(lat, lng) {
    const index = destinations.length;
    destinations.push([lat, lng]);
    
    // Create marker for this destination
    const marker = L.marker([lat, lng], {
        icon: L.divIcon({
            className: 'destination-marker',
            html: `<div class="destination-icon">${index + 1}</div>`,
            iconSize: [22, 22],
            iconAnchor: [11, 11]
        }),
        contextmenu: true,
        contextmenuItems: [{
            text: 'Remove this destination',
            callback: function() {
                removeDestinationByMarker(marker);
            }
        }]
    }).addTo(map);
    
    // Add popup with information
    marker.bindPopup(`Destination ${index + 1}<br>${lat.toFixed(6)}, ${lng.toFixed(6)}`);
    
    // Add right-click handler for quick removal
    marker.on('contextmenu', function() {
        removeDestinationByMarker(marker);
    });
    
    destinationMarkers.push(marker);
    
    // Update destination list in sidebar
    updateDestinationsList();
    
    showNotification('Destination added!');
}

/**
 * Remove a destination by marker reference
 */
function removeDestinationByMarker(marker) {
    // Find index of marker
    const index = destinationMarkers.findIndex(m => m === marker);
    if (index !== -1) {
        removeDestination(index);
    }
}

/**
 * Update the list of destinations in the sidebar
 */
function updateDestinationsList() {
    const listElement = document.getElementById('destinations-list');
    const countBadge = document.getElementById('count-badge');
    
    countBadge.textContent = destinations.length;
    
    if (destinations.length === 0) {
        listElement.innerHTML = '<p class="empty-message">No destinations added yet</p>';
        return;
    }
    
    let html = '<ul class="destinations">';
    for (let i = 0; i < destinations.length; i++) {
        const [lat, lng] = destinations[i];
        html += `
            <li>
                <span class="destination-number">${i + 1}</span>
                <span class="destination-coords">${lat.toFixed(6)}, ${lng.toFixed(6)}</span>
                <button class="btn-remove" onclick="removeDestination(${i})">×</button>
            </li>
        `;
    }
    html += '</ul>';
    
    listElement.innerHTML = html;
}

/**
 * Remove a destination by index
 */
function removeDestination(index) {
    // Remove marker from map
    map.removeLayer(destinationMarkers[index]);
    
    // Remove from arrays
    destinations.splice(index, 1);
    destinationMarkers.splice(index, 1);
    
    // Redraw all destination markers (to update numbers)
    destinationMarkers.forEach(marker => map.removeLayer(marker));
    destinationMarkers = [];
    
    for (let i = 0; i < destinations.length; i++) {
        const [lat, lng] = destinations[i];
        const marker = L.marker([lat, lng], {
            icon: L.divIcon({
                className: 'destination-marker',
                html: `<div class="destination-icon">${i + 1}</div>`,
                iconSize: [22, 22],
                iconAnchor: [11, 11]
            })
        }).addTo(map);
        
        marker.bindPopup(`Destination ${i + 1}<br>${lat.toFixed(6)}, ${lng.toFixed(6)}`);
        destinationMarkers.push(marker);
    }
    
    // Update sidebar list
    updateDestinationsList();
    
    showNotification('Destination removed');
}

/**
 * Clear all selections (warehouse and destinations)
 */
function clearSelections() {
    if (confirm('Are you sure you want to clear all locations?')) {
        // Remove warehouse marker
        if (warehouseMarker) {
            map.removeLayer(warehouseMarker);
            warehouseMarker = null;
            warehouse = null;
        }
        
        // Remove all destination markers
        destinationMarkers.forEach(marker => map.removeLayer(marker));
        destinationMarkers = [];
        destinations = [];
        
        // Reset displays
        document.getElementById('warehouse-display').innerHTML = '';
        updateDestinationsList();
        
        showNotification('All locations cleared');
    }
}

/**
 * Clear selections without confirmation dialog
 * Used when loading presets
 */
function clearSelectionsWithoutConfirm() {
    // Remove warehouse marker
    if (warehouseMarker) {
        map.removeLayer(warehouseMarker);
        warehouseMarker = null;
        warehouse = null;
    }
    
    // Remove all destination markers
    destinationMarkers.forEach(marker => map.removeLayer(marker));
    destinationMarkers = [];
    destinations = [];
    
    // Reset displays
    document.getElementById('warehouse-display').innerHTML = '';
    updateDestinationsList();
}

/**
 * Save the current locations to the server
 */
function saveLocations() {
    if (!warehouse) {
        showNotification('Please set a warehouse location first', 'error');
        return;
    }
    
    if (destinations.length === 0) {
        showNotification('Please add at least one destination', 'error');
        return;
    }
    
    // Prompt for a preset name
    const presetName = prompt('Enter a name for this set of locations:');
    if (!presetName || presetName.trim() === '') {
        showNotification('Preset name is required', 'error');
        return;
    }
    
    const data = {
        name: presetName,
        warehouse: warehouse,
        destinations: destinations
    };
    
    // Send data to server
    fetch('/locations/save_locations', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            showNotification(`Locations saved as preset "${presetName}"!`, 'success');
            // Redirect to the VRP solver page
            window.location.href = '/index';
        } else {
            showNotification('Error: ' + data.message, 'error');
        }
    })
    .catch(error => {
        console.error('Error saving locations:', error);
        showNotification('Failed to save locations', 'error');
    });
}

/**
 * Load saved locations from server
 */
function loadSavedLocations() {
    fetch('/get_locations')
        .then(response => response.json())
        .then(data => {
            // If we have a warehouse location
            if (data.warehouse) {
                const [lat, lng] = data.warehouse;
                setWarehouse(lat, lng);
            }
            
            // If we have destinations
            if (data.destinations && data.destinations.length > 0) {
                data.destinations.forEach(coords => {
                    const [lat, lng] = coords;
                    addDestination(lat, lng);
                });
            }
        })
        .catch(error => {
            console.error('Error loading locations:', error);
        });
}

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
            } else {
                const option = document.createElement('option');
                option.disabled = true;
                option.textContent = 'No presets available';
                presetsList.appendChild(option);
            }
        })
        .catch(error => {
            console.error('Error loading presets:', error);
        });
}

/**
 * Save current locations as a new preset
 */
function savePreset() {
    if (!warehouse) {
        showNotification('Please set a warehouse location first', 'error');
        return;
    }
    
    if (destinations.length === 0) {
        showNotification('Please add at least one destination', 'error');
        return;
    }
    
    const presetNameInput = document.getElementById('preset-name');
    const presetName = presetNameInput.value.trim();
    
    if (!presetName) {
        showNotification('Please enter a name for this preset', 'error');
        return;
    }
    
    const data = {
        name: presetName,
        warehouse: warehouse,
        destinations: destinations
    };
    
    // Send data to server
    fetch('/save_preset', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            showNotification(`Preset "${presetName}" saved successfully!`, 'success');
            presetNameInput.value = '';
            loadPresets();  // Refresh the presets list
        } else {
            showNotification('Error: ' + data.message, 'error');
        }
    })
    .catch(error => {
        console.error('Error saving preset:', error);
        showNotification('Failed to save preset. Please try again.', 'error');
    });
}

/**
 * Apply the selected preset
 */
function applySelectedPreset() {
    const presetsList = document.getElementById('presets-list');
    const selectedOption = presetsList.options[presetsList.selectedIndex];
    
    if (!selectedOption || selectedOption.disabled) {
        showNotification('Please select a valid preset', 'error');
        return;
    }
    
    const presetId = selectedOption.value;
    
    fetch(`/get_preset/${presetId}`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                // Clear current selections
                clearSelectionsWithoutConfirm();
                
                // Set warehouse
                if (data.preset.warehouse) {
                    const [lat, lng] = data.preset.warehouse;
                    setWarehouse(lat, lng);
                }
                
                // Add destinations
                if (data.preset.destinations && data.preset.destinations.length > 0) {
                    data.preset.destinations.forEach(coords => {
                        const [lat, lng] = coords;
                        addDestination(lat, lng);
                    });
                }
                
                showNotification(`Preset "${data.preset.name}" loaded successfully`, 'success');
            } else {
                showNotification('Error: ' + data.message, 'error');
            }
        })
        .catch(error => {
            console.error('Error applying preset:', error);
            showNotification('Failed to apply preset', 'error');
        });
}

/**
 * Delete the selected preset
 */
function deleteSelectedPreset() {
    const presetsList = document.getElementById('presets-list');
    const selectedOption = presetsList.options[presetsList.selectedIndex];
    
    if (!selectedOption || selectedOption.disabled) {
        showNotification('Please select a valid preset', 'error');
        return;
    }
    
    const presetId = selectedOption.value;
    const presetName = selectedOption.textContent.split(' (')[0];
    
    if (confirm(`Are you sure you want to delete preset "${presetName}"?`)) {
        fetch(`/delete_preset/${presetId}`, {
            method: 'DELETE'
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                showNotification(`Preset "${presetName}" deleted successfully`, 'success');
                loadPresets();  // Refresh the presets list
            } else {
                showNotification('Error: ' + data.message, 'error');
            }
        })
        .catch(error => {
            console.error('Error deleting preset:', error);
            showNotification('Failed to delete preset', 'error');
        });
    }
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