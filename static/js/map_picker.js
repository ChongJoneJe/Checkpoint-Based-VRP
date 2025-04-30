let map;
let locationMode = 'destination'; 
let warehouse = null;
let destinations = [];
let warehouseMarker = null;
let destinationMarkers = [];


function initMap(lat, lng) {
    map = Utils.createMap('map', [lat, lng], 13);
    if (!map) return;
    
    document.getElementById('warehouse-btn').addEventListener('click', () => setLocationMode('warehouse'));
    document.getElementById('destination-btn').addEventListener('click', () => setLocationMode('destination'));
    document.getElementById('clear-btn').addEventListener('click', clearSelections);
    document.getElementById('save-btn').addEventListener('click', function() {
        if (!warehouseMarker) {
            Utils.showNotification('Please select a warehouse location first', 'error');
            return;
        }
        
        if (destinationMarkers.length === 0) {
            Utils.showNotification('Please add at least one destination', 'error');
            return;
        }
        
        showNamePrompt();
    });
    
    map.on('click', handleMapClick);
    
    document.getElementById('save-preset-btn').addEventListener('click', savePreset);
    document.getElementById('apply-preset-btn').addEventListener('click', applySelectedPreset);
    document.getElementById('delete-preset-btn').addEventListener('click', deleteSelectedPreset);
    
    loadPresets();
}

function setLocationMode(mode) {
    locationMode = mode;
    
    document.getElementById('warehouse-btn').classList.toggle('active', mode === 'warehouse');
    document.getElementById('destination-btn').classList.toggle('active', mode === 'destination');
    
    // Update cursor to indicate active mode
    document.getElementById('map').style.cursor = 'crosshair';
}

function handleMapClick(e) {
    const lat = e.latlng.lat;
    const lng = e.latlng.lng;
    
    if (locationMode === 'warehouse') {
        setWarehouse(lat, lng);
    } else {
        addDestination(lat, lng);
    }
}


function verifyLocation(lat, lng, locationType) {
    Utils.showNotification('Verifying location...', 'info');
    
    return fetch(`/locations/verify_location?lat=${lat}&lng=${lng}`)
        .then(response => response.json())
        .then(data => {
            if (data.needs_user_input) {
                // Show the address modal when reverse geocoding failed
                return showAddressModal(lat, lng, locationType, data.suggested_values);
            } else {
                return Promise.resolve(data.address);
            }
        })
        .catch(error => {
            console.error('Error verifying location:', error);
            Utils.showNotification('Error verifying location address', 'error');
            return showAddressModal(lat, lng, locationType, {});
        });
}

function showAddressModal(lat, lng, locationType, suggestedValues) {
    return new Promise((resolve, reject) => {
        const modal = document.getElementById('address-modal');
        
        document.getElementById('address-lat').value = lat;
        document.getElementById('address-lng').value = lng;
        document.getElementById('address-type').value = locationType;
        
        // Fill in suggested values - only neighborhood, city and postcode
        if (suggestedValues) {
            if (suggestedValues.neighborhood) document.getElementById('address-neighborhood').value = suggestedValues.neighborhood;
            if (suggestedValues.city) document.getElementById('address-city').value = suggestedValues.city;
            if (suggestedValues.postcode) document.getElementById('address-postcode').value = suggestedValues.postcode;
        }
        
        modal.style.display = 'block';
        
        const previewMap = L.map('mini-map').setView([lat, lng], 17);
        
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap contributors'
        }).addTo(previewMap);
        
        L.marker([lat, lng]).addTo(previewMap);
        
        setTimeout(() => {
            previewMap.invalidateSize();
        }, 100);
        
        document.getElementById('address-street').focus();
        
        document.getElementById('address-form').onsubmit = function(e) {
            e.preventDefault();
            
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
            
            if (warehouseMarker) {
                const warehouseLatLng = warehouseMarker.getLatLng();
                addressData.warehouse_location = [warehouseLatLng.lat, warehouseLatLng.lng];
            }
            
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
                    Utils.showNotification(`Address saved successfully${data.cluster_name ? ` to cluster: ${data.cluster_name}` : ''}`, 'success');
                    
                    const addressObject = {
                        street: street,
                        neighborhood: neighborhood,
                        city: city,
                        postcode: postcode,
                        country: 'Malaysia'
                    };
                    
                    previewMap.remove();
                    resetAddressForm();

                    resolve(addressObject);
                } else {
                    Utils.showNotification('Error: ' + data.message, 'error');
                    previewMap.remove();
                    resetAddressForm();
                    reject(new Error(data.message));
                }
            })
            .catch(error => {
                console.error('Error:', error);
                Utils.showNotification('Error saving address: ' + error, 'error');
                previewMap.remove();
                resetAddressForm();
                reject(error);
            });
        };
        
        document.getElementById('cancel-address-btn').onclick = function() {
            modal.style.display = 'none';
            resetAddressForm();
            previewMap.remove();
            reject(new Error('Address input canceled'));
        };
        
        document.querySelector('.close-modal').onclick = function() {
            modal.style.display = 'none';
            resetAddressForm();
            previewMap.remove();
            reject(new Error('Address input canceled'));
        };
    });
}

function resetAddressForm() {
    document.getElementById('address-form').reset();
}

function setWarehouse(lat, lng) {
    verifyLocation(lat, lng, 'warehouse')
        .then(address => {
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
            
            const addressText = address.street ? `<br>${address.street}` : '';
            warehouseMarker.bindPopup(`Warehouse<br>${lat.toFixed(6)}, ${lng.toFixed(6)}${addressText}`);
            
            document.getElementById('warehouse-display').innerHTML = `
                <h3>Warehouse</h3>
                <p class="coords">${lat.toFixed(6)}, ${lng.toFixed(6)}</p>
                ${address.street ? `<p class="address">${address.street}</p>` : ''}
            `;
            
            setLocationMode('destination');
            
            Utils.showNotification('Warehouse location set!');
        })
        .catch(error => {
            console.error('Error setting warehouse:', error);
            Utils.showNotification('Failed to set warehouse location', 'error');
        });
}


function addDestination(lat, lng) {
    verifyLocation(lat, lng, 'destination')
        .then(address => {
            const index = destinations.length;
            destinations.push([lat, lng]);
            
            saveLocation(lat, lng);
            
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

            marker.on('contextmenu', function() {
                removeDestinationByMarker(marker);
            });
            
            destinationMarkers.push(marker);
            
            updateDestinationsList();
            
            Utils.showNotification('Destination added!');
        })
        .catch(error => {
            console.error('Error adding destination:', error);
            Utils.showNotification('Failed to add destination', 'error');
        });
}


function removeDestinationByMarker(marker) {
    const index = destinationMarkers.findIndex(m => m === marker);
    if (index !== -1) {
        removeDestination(index);
    }
}

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

function removeDestination(index) {
    map.removeLayer(destinationMarkers[index]);
    
    destinations.splice(index, 1);
    destinationMarkers.splice(index, 1);
    
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

    updateDestinationsList();
    
    Utils.showNotification('Destination removed');
}

function clearSelections() {
    if (confirm('Are you sure you want to clear all locations?')) {
        if (warehouseMarker) {
            map.removeLayer(warehouseMarker);
            warehouseMarker = null;
            warehouse = null;
        }
        
        destinationMarkers.forEach(marker => map.removeLayer(marker));
        destinationMarkers = [];
        destinations = [];
        
        document.getElementById('warehouse-display').innerHTML = '';
        updateDestinationsList();
        
        Utils.showNotification('All locations cleared');
    }
}

function clearSelectionsWithoutConfirm() {
    if (warehouseMarker) {
        map.removeLayer(warehouseMarker);
        warehouseMarker = null;
        warehouse = null;
    }
    
    destinationMarkers.forEach(marker => map.removeLayer(marker));
    destinationMarkers = [];
    destinations = [];
    
    document.getElementById('warehouse-display').innerHTML = '';
    updateDestinationsList();
}

function saveLocations(presetName) {
    // Prepare data
    const data = {
        name: presetName,
        warehouse: [warehouseMarker.getLatLng().lat, warehouseMarker.getLatLng().lng],
        destinations: destinationMarkers.map(marker => [marker.getLatLng().lat, marker.getLatLng().lng])
    };
    
    Utils.showNotification('Saving locations...');
    
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
            Utils.showNotification('Locations saved successfully!');
        } else {
            Utils.showNotification('Error: ' + data.message);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        Utils.showNotification('Failed to save locations');
    });
}

function loadSavedLocations() {
    fetch('/locations/get_locations')
        .then(response => response.json())
        .then(data => {
            if (data.warehouse) {
                const [lat, lng] = data.warehouse;
                setWarehouse(lat, lng);
            }
            
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

function savePreset() {
    if (!warehouse) {
        Utils.showNotification('Please set a warehouse location first', 'error');
        return;
    }
    
    if (destinations.length === 0) {
        Utils.showNotification('Please add at least one destination', 'error');
        return;
    }
    
    const presetNameInput = document.getElementById('preset-name');
    const presetName = presetNameInput.value.trim();
    
    if (!presetName) {
        Utils.showNotification('Please enter a name for this preset', 'error');
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
            Utils.showNotification(`Preset "${presetName}" saved successfully!`, 'success');
            presetNameInput.value = '';
            loadPresets();  
        } else {
            Utils.showNotification('Error: ' + data.message, 'error');
        }
    })
    .catch(error => {
        console.error('Error saving preset:', error);
        Utils.showNotification('Failed to save preset. Please try again.', 'error');
    });
}

function applySelectedPreset() {
    const presetsList = document.getElementById('presets-list');
    const selectedOption = presetsList.options[presetsList.selectedIndex];
    
    if (!selectedOption || selectedOption.disabled) {
        Utils.showNotification('Please select a valid preset', 'error');
        return;
    }
    
    const presetId = selectedOption.value;
    
    fetch(`/get_preset/${presetId}`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                clearSelectionsWithoutConfirm();
                
                if (data.preset.warehouse) {
                    const [lat, lng] = data.preset.warehouse;
                    setWarehouse(lat, lng);
                }
                
                if (data.preset.destinations && data.preset.destinations.length > 0) {
                    data.preset.destinations.forEach(coords => {
                        const [lat, lng] = coords;
                        addDestination(lat, lng);
                    });
                }
                
                Utils.showNotification(`Preset "${data.preset.name}" loaded successfully`, 'success');
            } else {
                Utils.showNotification('Error: ' + data.message, 'error');
            }
        })
        .catch(error => {
            console.error('Error applying preset:', error);
            Utils.showNotification('Failed to apply preset', 'error');
        });
}

function deleteSelectedPreset() {
    const presetsList = document.getElementById('presets-list');
    const selectedOption = presetsList.options[presetsList.selectedIndex];
    
    if (!selectedOption || selectedOption.disabled) {
        Utils.showNotification('Please select a valid preset', 'error');
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
                Utils.showNotification(`Preset "${presetName}" deleted successfully`, 'success');
                loadPresets();  
            } else {
                Utils.showNotification('Error: ' + data.message, 'error');
            }
        })
        .catch(error => {
            console.error('Error deleting preset:', error);
            Utils.showNotification('Failed to delete preset', 'error');
        });
    }
}

function showNotification(message, type = 'info') {
    Utils.showNotification(message, type);
}

function showNamePrompt() {
    // Show the notification with the name input
    const notification = document.getElementById('notification');
    const messageSpan = document.getElementById('notification-message');
    const nameContainer = document.getElementById('name-input-container');
    
    messageSpan.textContent = 'Please enter a name for your preset:';
    nameContainer.classList.remove('hidden');
    notification.classList.remove('hidden');
    
    document.getElementById('preset-name-prompt').focus();
    
    if (!document.getElementById('confirm-name-btn').hasClickHandler) {
        document.getElementById('confirm-name-btn').addEventListener('click', confirmSaveWithName);
        document.getElementById('confirm-name-btn').hasClickHandler = true;
    }
    
    if (!document.getElementById('cancel-name-btn').hasClickHandler) {
        document.getElementById('cancel-name-btn').addEventListener('click', cancelSave);
        document.getElementById('cancel-name-btn').hasClickHandler = true;
    }
    
    document.getElementById('preset-name-prompt').addEventListener('keyup', function(event) {
        if (event.key === 'Enter') {
            confirmSaveWithName();
        }
    });
}

function confirmSaveWithName() {
    const name = document.getElementById('preset-name-prompt').value.trim();
    
    if (!name) {
        document.getElementById('preset-name-prompt').style.borderColor = 'red';
        return;
    }
    
    hideNamePrompt();
    
    saveLocations(name);
}

function cancelSave() {
    hideNamePrompt();
    Utils.showNotification('Location saving canceled');
    setTimeout(hideNotification, 3000);
}

function hideNamePrompt() {
    document.getElementById('name-input-container').classList.add('hidden');
    document.getElementById('notification').classList.add('hidden');
    document.getElementById('preset-name-prompt').value = '';
    document.getElementById('preset-name-prompt').style.borderColor = '';
}

function hideNotification() {
    Utils.hideNotification();
}

function promptSaveLocations() {
    if (!warehouseMarker) {
        Utils.showNotification('Please select a warehouse location first', 'error');
        return;
    }
    
    if (destinationMarkers.length === 0) {
        Utils.showNotification('Please add at least one destination', 'error');
        return;
    }
    
    const presetName = prompt('Please enter a name for this preset:');
    
    if (!presetName || presetName.trim() === '') {
        Utils.showNotification('Preset name is required', 'error');
        return;
    }
    
    const data = {
        name: presetName,
        warehouse: [warehouseMarker.getLatLng().lat, warehouseMarker.getLatLng().lng],
        destinations: destinationMarkers.map(marker => [marker.getLatLng().lat, marker.getLatLng().lng])
    };
    
    showLoadingIndicator(destinationMarkers.length);
    
    fetch('/locations/save_locations', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(data => {

        hideLoadingIndicator();
        
        if (data.status === 'success') {
            Utils.showNotification('Locations saved successfully!', 'success');

            if (typeof loadPresets === 'function') {
                loadPresets();
            }
        } else {
            Utils.showNotification('Error: ' + data.message, 'error');
        }
    })
    .catch(error => {

        hideLoadingIndicator();
        
        console.error('Error:', error);
        Utils.showNotification('Failed to save locations', 'error');
    });
}

function showLoadingIndicator(totalLocations) {
    return Utils.showLoadingIndicator('Saving Locations', true);
}

function hideLoadingIndicator() {
    Utils.hideLoadingIndicator();
}

function saveLocation(lat, lon, isWarehouse = false) {
    if (isWarehouse) {
        sessionStorage.setItem('warehouseLocation', JSON.stringify({lat, lon}));
    } else {
        let locations = JSON.parse(sessionStorage.getItem('selectedLocations') || '[]');
        locations.push({lat, lon});
        sessionStorage.setItem('selectedLocations', JSON.stringify(locations));
    }
}

document.addEventListener('DOMContentLoaded', function() {

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
    
    document.getElementById('count-badge').textContent = '0';
    document.getElementById('destinations-list').innerHTML = '';
    document.getElementById('warehouse-display').innerHTML = '';
    
    document.getElementById('warehouse-btn').classList.remove('active');
    document.getElementById('destination-btn').classList.add('active');
    
    const storedLocations = JSON.parse(sessionStorage.getItem('selectedLocations') || '[]');
    const warehouseLocation = JSON.parse(sessionStorage.getItem('warehouseLocation') || 'null');
    

    if (typeof initMap === 'function' && typeof lat === 'undefined') {
        initMap(3.1390, 101.6869); 
    }
    
    document.getElementById('warehouse-btn').addEventListener('click', function() {
        setLocationMode('warehouse');
    });
    
    document.getElementById('destination-btn').addEventListener('click', function() {
        setLocationMode('destination');
    });
    
    document.getElementById('clear-btn').addEventListener('click', clearSelections);
    
    document.getElementById('save-btn').addEventListener('click', promptSaveLocations);

});