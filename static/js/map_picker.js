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
    document.getElementById('save-btn').addEventListener('click', function() {
        // Validate locations first
        if (!warehouseMarker) {
            showNotification('Please select a warehouse location first');
            return;
        }
        
        if (destinationMarkers.length === 0) {
            showNotification('Please add at least one destination');
            return;
        }
        
        // Prompt for name
        showNamePrompt();
    });
    
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
 * Verify location address
 */
function verifyLocation(lat, lng, locationType) {
    showNotification('Verifying location...', 'info');
    
    return fetch(`/locations/verify_location?lat=${lat}&lng=${lng}`)
        .then(response => response.json())
        .then(data => {
            if (data.needs_user_input) {
                // Show the address modal when reverse geocoding failed
                return showAddressModal(lat, lng, locationType, data.suggested_values);
            } else {
                // No need for user input, return the address
                return Promise.resolve(data.address);
            }
        })
        .catch(error => {
            console.error('Error verifying location:', error);
            showNotification('Error verifying location address', 'error');
            // Show address form even in case of error
            return showAddressModal(lat, lng, locationType, {});
        });
}

/**
 * Show the address modal and return a Promise
 */
function showAddressModal(lat, lng, locationType, suggestedValues) {
    return new Promise((resolve, reject) => {
        const modal = document.getElementById('address-modal');
        
        // Set hidden values
        document.getElementById('address-lat').value = lat;
        document.getElementById('address-lng').value = lng;
        document.getElementById('address-type').value = locationType;
        
        // Fill in suggested values - only neighborhood, city and postcode
        if (suggestedValues) {
            if (suggestedValues.neighborhood) document.getElementById('address-neighborhood').value = suggestedValues.neighborhood;
            if (suggestedValues.city) document.getElementById('address-city').value = suggestedValues.city;
            if (suggestedValues.postcode) document.getElementById('address-postcode').value = suggestedValues.postcode;
        }
        
        // Show the modal
        modal.style.display = 'block';
        
        // Create a mini map showing the selected location
        const previewMap = L.map('mini-map').setView([lat, lng], 17);
        
        // Add base tile layer
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap contributors'
        }).addTo(previewMap);
        
        // Add marker for the selected location
        L.marker([lat, lng]).addTo(previewMap);
        
        // Fix the map after rendering (needed because the map is initially hidden)
        setTimeout(() => {
            previewMap.invalidateSize();
        }, 100);
        
        // Focus the street input
        document.getElementById('address-street').focus();
        
        // Handle form submission
        document.getElementById('address-form').onsubmit = function(e) {
            e.preventDefault();
            
            // Get form values - just use the street as entered (no section/subsection formatting)
            let street = document.getElementById('address-street').value.trim();
            let neighborhood = document.getElementById('address-neighborhood').value.trim();
            let city = document.getElementById('address-city').value.trim();
            let postcode = document.getElementById('address-postcode').value.trim();
            
            const addressData = {
                lat: document.getElementById('address-lat').value,
                lng: document.getElementById('address-lng').value,
                street: street,
                neighborhood: neighborhood,
                city: city,
                postcode: postcode,
                country: 'Malaysia'
            };
            
            // If warehouse exists, add it to the data for proper clustering
            if (warehouseMarker) {
                const warehouseLatLng = warehouseMarker.getLatLng();
                addressData.warehouse_location = [warehouseLatLng.lat, warehouseLatLng.lng];
            }
            
            // Close the modal
            modal.style.display = 'none';
            
            // Submit to server
            fetch('/locations/save_address', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(addressData)
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    showNotification(`Address saved successfully${data.cluster_name ? ` to cluster: ${data.cluster_name}` : ''}`, 'success');
                    
                    // Create a complete address object to resolve the promise
                    const addressObject = {
                        street: street,
                        neighborhood: neighborhood,
                        city: city,
                        postcode: postcode,
                        country: 'Malaysia'
                    };
                    
                    // Cleanup
                    previewMap.remove();
                    resetAddressForm();
                    
                    // Resolve with the full address object
                    resolve(addressObject);
                } else {
                    showNotification('Error: ' + data.message, 'error');
                    previewMap.remove();
                    resetAddressForm();
                    reject(new Error(data.message));
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showNotification('Error saving address: ' + error, 'error');
                previewMap.remove();
                resetAddressForm();
                reject(error);
            });
        };
        
        // Handle cancel button
        document.getElementById('cancel-address-btn').onclick = function() {
            modal.style.display = 'none';
            resetAddressForm();
            previewMap.remove();
            reject(new Error('Address input canceled'));
        };
        
        // Handle modal close button
        document.querySelector('.close-modal').onclick = function() {
            modal.style.display = 'none';
            resetAddressForm();
            previewMap.remove();
            reject(new Error('Address input canceled'));
        };
    });
}

/**
 * Reset the address form
 */
function resetAddressForm() {
    document.getElementById('address-form').reset();
}

/**
 * Set the warehouse location
 */
function setWarehouse(lat, lng) {
    // Verify location first
    verifyLocation(lat, lng, 'warehouse')
        .then(address => {
            // Remove existing warehouse marker if any
            if (warehouseMarker) {
                map.removeLayer(warehouseMarker);
            }
            
            // Store new warehouse location
            warehouse = [lat, lng];
            
            // Save warehouse location to session storage
            saveLocation(lat, lng, true);
            
            // Add warehouse marker
            warehouseMarker = L.marker([lat, lng], {
                icon: L.divIcon({
                    className: 'warehouse-marker',
                    html: '<div class="warehouse-icon"></div>',
                    iconSize: [24, 24],
                    iconAnchor: [12, 12]
                })
            }).addTo(map);
            
            // Add popup with coordinates and address
            const addressText = address.street ? `<br>${address.street}` : '';
            warehouseMarker.bindPopup(`Warehouse<br>${lat.toFixed(6)}, ${lng.toFixed(6)}${addressText}`);
            
            // Update sidebar display
            document.getElementById('warehouse-display').innerHTML = `
                <h3>Warehouse</h3>
                <p class="coords">${lat.toFixed(6)}, ${lng.toFixed(6)}</p>
                ${address.street ? `<p class="address">${address.street}</p>` : ''}
            `;
            
            // Switch to destination mode after setting warehouse
            setLocationMode('destination');
            
            showNotification('Warehouse location set!');
        })
        .catch(error => {
            console.error('Error setting warehouse:', error);
            showNotification('Failed to set warehouse location', 'error');
        });
}

/**
 * Add a destination location
 */
function addDestination(lat, lng) {
    // Verify location first
    verifyLocation(lat, lng, 'destination')
        .then(address => {
            const index = destinations.length;
            destinations.push([lat, lng]);
            
            // Save destination location to session storage
            saveLocation(lat, lng);
            
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
            
            // Add popup with information and address
            const addressText = address.street ? `<br>${address.street}` : '';
            marker.bindPopup(`Destination ${index + 1}<br>${lat.toFixed(6)}, ${lng.toFixed(6)}${addressText}`);
            
            // Add right-click handler for quick removal
            marker.on('contextmenu', function() {
                removeDestinationByMarker(marker);
            });
            
            destinationMarkers.push(marker);
            
            // Update destination list in sidebar
            updateDestinationsList();
            
            showNotification('Destination added!');
        })
        .catch(error => {
            console.error('Error adding destination:', error);
            showNotification('Failed to add destination', 'error');
        });
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
function saveLocations(presetName) {
    // Prepare data
    const data = {
        name: presetName,
        warehouse: [warehouseMarker.getLatLng().lat, warehouseMarker.getLatLng().lng],
        destinations: destinationMarkers.map(marker => [marker.getLatLng().lat, marker.getLatLng().lng])
    };
    
    // Show saving notification
    showNotification('Saving locations...');
    
    // Send to backend
    fetch('/locations/save_locations', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            showNotification('Locations saved successfully!');
        } else {
            showNotification('Error: ' + data.message);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showNotification('Failed to save locations');
    });
}

/**
 * Load saved locations from server
 */
function loadSavedLocations() {
    fetch('/locations/get_locations')
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
    fetch('/presets/get_presets')
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

function showNamePrompt() {
    // Show the notification with the name input
    const notification = document.getElementById('notification');
    const messageSpan = document.getElementById('notification-message');
    const nameContainer = document.getElementById('name-input-container');
    
    messageSpan.textContent = 'Please enter a name for your preset:';
    nameContainer.classList.remove('hidden');
    notification.classList.remove('hidden');
    
    // Focus the input
    document.getElementById('preset-name-prompt').focus();
    
    // Set up button handlers if they don't exist yet
    if (!document.getElementById('confirm-name-btn').hasClickHandler) {
        document.getElementById('confirm-name-btn').addEventListener('click', confirmSaveWithName);
        document.getElementById('confirm-name-btn').hasClickHandler = true;
    }
    
    if (!document.getElementById('cancel-name-btn').hasClickHandler) {
        document.getElementById('cancel-name-btn').addEventListener('click', cancelSave);
        document.getElementById('cancel-name-btn').hasClickHandler = true;
    }
    
    // Also allow Enter key to confirm
    document.getElementById('preset-name-prompt').addEventListener('keyup', function(event) {
        if (event.key === 'Enter') {
            confirmSaveWithName();
        }
    });
}

function confirmSaveWithName() {
    const name = document.getElementById('preset-name-prompt').value.trim();
    
    if (!name) {
        // Highlight the input if empty
        document.getElementById('preset-name-prompt').style.borderColor = 'red';
        return;
    }
    
    // Hide the name prompt
    hideNamePrompt();
    
    // Proceed with saving
    saveLocations(name);
}

function cancelSave() {
    hideNamePrompt();
    showNotification('Location saving canceled');
    setTimeout(hideNotification, 3000);
}

function hideNamePrompt() {
    document.getElementById('name-input-container').classList.add('hidden');
    document.getElementById('notification').classList.add('hidden');
    document.getElementById('preset-name-prompt').value = '';
    document.getElementById('preset-name-prompt').style.borderColor = '';
}

function hideNotification() {
    document.getElementById('notification').classList.add('hidden');
}

/**
 * Prompt user for preset name and save locations
 */
function promptSaveLocations() {
    if (!warehouseMarker) {
        showNotification('Please select a warehouse location first', 'error');
        return;
    }
    
    if (destinationMarkers.length === 0) {
        showNotification('Please add at least one destination', 'error');
        return;
    }
    
    // Prompt for name with a simple dialog
    const presetName = prompt('Please enter a name for this preset:');
    
    if (!presetName || presetName.trim() === '') {
        showNotification('Preset name is required', 'error');
        return;
    }
    
    const data = {
        name: presetName,
        warehouse: [warehouseMarker.getLatLng().lat, warehouseMarker.getLatLng().lng],
        destinations: destinationMarkers.map(marker => [marker.getLatLng().lat, marker.getLatLng().lng])
    };
    
    // Show loading indicator
    showLoadingIndicator(destinationMarkers.length);
    
    // Send to backend
    fetch('/locations/save_locations', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(data => {
        // Hide loading indicator
        hideLoadingIndicator();
        
        if (data.status === 'success') {
            showNotification('Locations saved successfully!', 'success');
            // Reload presets if you have a presets list
            if (typeof loadPresets === 'function') {
                loadPresets();
            }
        } else {
            showNotification('Error: ' + data.message, 'error');
        }
    })
    .catch(error => {
        // Hide loading indicator on error
        hideLoadingIndicator();
        
        console.error('Error:', error);
        showNotification('Failed to save locations', 'error');
    });
}

/**
 * Show loading indicator with progress
 */
function showLoadingIndicator(totalLocations) {
    // Create loading overlay if it doesn't exist
    let loadingOverlay = document.getElementById('loading-overlay');
    if (!loadingOverlay) {
        loadingOverlay = document.createElement('div');
        loadingOverlay.id = 'loading-overlay';
        loadingOverlay.innerHTML = `
            <div class="loading-container">
                <div class="loading-spinner"></div>
                <h3>Saving Locations</h3>
                <div class="progress-container">
                    <div id="loading-progress-bar" class="progress-bar"></div>
                </div>
                <div id="loading-message">Preparing to save...</div>
            </div>
        `;
        document.body.appendChild(loadingOverlay);
    }
    
    // Show the overlay
    loadingOverlay.style.display = 'flex';
    
    // Reset progress bar
    const progressBar = document.getElementById('loading-progress-bar');
    progressBar.style.width = '0%';
    
    // Simulate progress based on number of locations
    const loadingMessage = document.getElementById('loading-message');
    const steps = [
        { percent: 10, message: 'Initializing...' },
        { percent: 20, message: 'Validating warehouse location...' },
        { percent: 30, message: 'Processing destinations...' },
        { percent: 50, message: 'Geocoding addresses...' },
        { percent: 70, message: 'Identifying clusters...' },
        { percent: 85, message: 'Finalizing...' },
        { percent: 95, message: 'Saving to database...' }
    ];
    
    // Add some randomness to make it feel more natural
    const timePerStep = 300 + Math.random() * 200;
    const totalTime = timePerStep * steps.length;
    
    // Update progress bar and message
    steps.forEach((step, index) => {
        setTimeout(() => {
            if (loadingOverlay.style.display !== 'none') {
                progressBar.style.width = step.percent + '%';
                loadingMessage.textContent = step.message;
            }
        }, timePerStep * index);
    });
}

/**
 * Hide loading indicator
 */
function hideLoadingIndicator() {
    const loadingOverlay = document.getElementById('loading-overlay');
    if (loadingOverlay) {
        // Complete the progress bar animation first
        const progressBar = document.getElementById('loading-progress-bar');
        const loadingMessage = document.getElementById('loading-message');
        
        progressBar.style.width = '100%';
        loadingMessage.textContent = 'Complete!';
        
        // Hide after a short delay to show completion
        setTimeout(() => {
            loadingOverlay.style.display = 'none';
        }, 500);
    }
}

/**
 * Save location to session storage
 */
function saveLocation(lat, lon, isWarehouse = false) {
    if (isWarehouse) {
        sessionStorage.setItem('warehouseLocation', JSON.stringify({lat, lon}));
    } else {
        let locations = JSON.parse(sessionStorage.getItem('selectedLocations') || '[]');
        locations.push({lat, lon});
        sessionStorage.setItem('selectedLocations', JSON.stringify(locations));
    }
}

// Clean up the event listeners at the bottom of your file
document.addEventListener('DOMContentLoaded', function() {
    // Clear any stored location data
    sessionStorage.removeItem('selectedLocations');
    sessionStorage.removeItem('warehouseLocation');
    localStorage.removeItem('selectedLocations');
    localStorage.removeItem('warehouseLocation');
    
    // Reset any existing markers
    if (typeof markers !== 'undefined') {
        markers.forEach(marker => {
            if (marker) marker.remove();
        });
    }
    markers = [];
    
    // Reset counters and displays
    document.getElementById('count-badge').textContent = '0';
    document.getElementById('destinations-list').innerHTML = '';
    document.getElementById('warehouse-display').innerHTML = '';
    
    // Reset buttons to initial state
    document.getElementById('warehouse-btn').classList.remove('active');
    document.getElementById('destination-btn').classList.add('active');
    
    // Load any stored locations
    const storedLocations = JSON.parse(sessionStorage.getItem('selectedLocations') || '[]');
    const warehouseLocation = JSON.parse(sessionStorage.getItem('warehouseLocation') || 'null');
    
    // Initialize map with default center if not provided
    if (typeof initMap === 'function' && typeof lat === 'undefined') {
        initMap(3.1390, 101.6869); // Default to Malaysia
    }
    
    // Set up button event listeners
    document.getElementById('warehouse-btn').addEventListener('click', function() {
        setLocationMode('warehouse');
    });
    
    document.getElementById('destination-btn').addEventListener('click', function() {
        setLocationMode('destination');
    });
    
    document.getElementById('clear-btn').addEventListener('click', clearSelections);
    
    // Set up the save button with direct prompt
    document.getElementById('save-btn').addEventListener('click', promptSaveLocations);

});