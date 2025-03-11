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
        })
    }).addTo(map);
    
    // Add popup with information
    marker.bindPopup(`Destination ${index + 1}<br>${lat.toFixed(6)}, ${lng.toFixed(6)}`);
    destinationMarkers.push(marker);
    
    // Update destination list in sidebar
    updateDestinationsList();
    
    showNotification('Destination added!');
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
    
    const data = {
        warehouse: warehouse,
        destinations: destinations
    };
    
    // Send data to server
    fetch('/save_locations', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data)
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            showNotification('Locations saved successfully!', 'success');
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