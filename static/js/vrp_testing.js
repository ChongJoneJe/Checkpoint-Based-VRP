console.log("VRP Testing JS loading...");

// Update loadSnapshots function to handle array responses
function loadSnapshots() {
    const container = document.getElementById('snapshots-container');
    if (!container) {
        console.error('Snapshots container not found!');
        return;
    }
    
    // Show loading indicator
    container.innerHTML = `
        <div class="text-center py-3">
            <div class="spinner-border text-primary" role="status"></div>
            <p class="mt-2">Loading snapshots...</p>
        </div>
    `;
    
    console.log('Fetching snapshots...');
    
    fetch('/vrp_testing/snapshots')
        .then(response => {
            console.log('Snapshots response status:', response.status);
            return response.json();
        })
        .then(data => {
            console.log('Snapshots data:', data);
            
            // Handle if data is array (direct snapshots)
            const snapshots = Array.isArray(data) ? data : 
                           (data.status === 'success' ? data.snapshots : null);
            
            if (snapshots && snapshots.length > 0) {
                let html = `
                    <table class="table table-hover">
                        <thead>
                            <tr>
                                <th>Created</th>
                                <th>ID</th>
                                <th>Locations</th>
                                <th>Clusters</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                `;
                
                snapshots.forEach(snapshot => {
                    html += `
                        <tr>
                            <td>${snapshot.created_at}</td>
                            <td>${snapshot.id}</td>
                            <td>${snapshot.stats?.locations || 0}</td>
                            <td>${snapshot.stats?.clusters || 0}</td>
                            <td>
                                <button class="btn btn-sm btn-primary run-test-btn" data-snapshot-id="${snapshot.id}">
                                    <i class="fas fa-play"></i> Use
                                </button>
                                <button class="btn btn-sm btn-danger delete-snapshot-btn" data-snapshot-id="${snapshot.id}">
                                    <i class="fas fa-trash"></i>
                                </button>
                            </td>
                        </tr>
                    `;
                });
                
                html += `</tbody></table>`;
                container.innerHTML = html;
                
                // Add event listeners for buttons
                document.querySelectorAll('.run-test-btn').forEach(button => {
                    button.addEventListener('click', function() {
                        const snapshotId = this.getAttribute('data-snapshot-id');
                        showTestForm(snapshotId);
                    });
                });
                
                document.querySelectorAll('.delete-snapshot-btn').forEach(button => {
                    button.addEventListener('click', function() {
                        const snapshotId = this.getAttribute('data-snapshot-id');
                        deleteSnapshot(snapshotId);
                    });
                });
            } else {
                container.innerHTML = `
                    <div class="alert alert-warning">
                        <i class="fas fa-exclamation-triangle"></i> No snapshots available. 
                        Create a new snapshot to start testing.
                    </div>
                `;
            }
        })
        .catch(error => {
            console.error('Error loading snapshots:', error);
            container.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-circle"></i> 
                    Error: ${error.message || 'Failed to load snapshots'}
                    <button onclick="loadSnapshots()" class="btn btn-sm btn-primary mt-2">Retry</button>
                </div>
            `;
        });
}

// Add at the beginning of your DOMContentLoaded event handler:
function checkRequiredElements() {
    const requiredElements = [
        'snapshots-container',
        'test-history-content',
        'test-configuration'
    ];
    
    const missingElements = [];
    
    requiredElements.forEach(id => {
        if (!document.getElementById(id)) {
            missingElements.push(id);
        }
    });
    
    if (missingElements.length > 0) {
        console.error('Missing required DOM elements:', missingElements);
        const mainContainer = document.querySelector('main') || document.body;
        mainContainer.innerHTML = `
            <div class="alert alert-danger">
                <h4>VRP Testing Dashboard Error</h4>
                <p>The following required elements are missing from the HTML:</p>
                <ul>${missingElements.map(id => `<li>${id}</li>`).join('')}</ul>
                <p>Please check your HTML template.</p>
                <button onclick="location.reload()" class="btn btn-primary">Reload Page</button>
            </div>
        `;
        return false;
    }
    
    return true;
}

document.addEventListener('DOMContentLoaded', function() {
    console.log("DOM fully loaded");
    try {
        // Check if all required elements exist
        if (!checkRequiredElements()) {
            return; // Stop initialization if elements are missing
        }

        // Check if Utils is available
        if (typeof Utils === 'undefined') {
            console.error("Utils is not defined! Check script loading order.");
            // Create fallback Utils object with minimal functionality
            window.Utils = {
                createMap: function(elementId, initialCoords, zoom) {
                    console.log("Using fallback map creation");
                    const map = L.map(elementId).setView(initialCoords, zoom);
                    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                    }).addTo(map);
                    return map;
                },
                clearMapLayers: function(map) {
                    map.eachLayer(layer => {
                        if (!(layer instanceof L.TileLayer)) {
                            map.removeLayer(layer);
                        }
                    });
                },
                debugLog: function(msg) {
                    console.log(msg);
                }
            };
        }
        
        // Load snapshots
        loadSnapshots();
        
        // Load test history
        loadTestHistory();
        
        // Setup event listeners after ensuring elements exist
        const createSnapshotBtn = document.getElementById('create-snapshot-btn');
        if (createSnapshotBtn) {
            createSnapshotBtn.addEventListener('click', createSnapshot);
        }

        // Set up delegate event listeners for dynamic elements
        document.addEventListener('click', function(e) {
            // Run test button
            if (e.target.classList.contains('run-test-btn') || 
                e.target.closest('.run-test-btn')) {
                const btn = e.target.closest('.run-test-btn');
                const snapshotId = btn.dataset.snapshotId;
                showTestForm(snapshotId);
            }
            
            // Delete snapshot button
            if (e.target.classList.contains('delete-snapshot-btn') || 
                e.target.closest('.delete-snapshot-btn')) {
                const btn = e.target.closest('.delete-snapshot-btn');
                const snapshotId = btn.dataset.snapshotId;
                deleteSnapshot(snapshotId);
            }
            
            // Select test checkbox
            if (e.target.classList.contains('select-test-cb')) {
                updateCompareButtonState();
            }
        });
        
        // Run test submit button
        const runTestSubmit = document.getElementById('run-test-submit');
        if (runTestSubmit) {
            runTestSubmit.addEventListener('click', runTest);
        }
        
        // Compare tests button
        const compareTestsBtn = document.getElementById('compare-tests-btn');
        if (compareTestsBtn) {
            compareTestsBtn.addEventListener('click', compareTests);
        }
        
        // Add the dynamic insertion handlers
        const enableDynamicInsertionCheckbox = document.getElementById('enable-dynamic-insertion');
        if (enableDynamicInsertionCheckbox) {
            enableDynamicInsertionCheckbox.addEventListener('change', function() {
                const dynamicControls = document.getElementById('dynamic-controls');
                const dynamicStats = document.getElementById('dynamic-stats');
                
                if (this.checked) {
                    dynamicControls.style.display = 'block';
                    dynamicStats.style.display = 'block';
                    enableDynamicInsertion();
                } else {
                    dynamicControls.style.display = 'none';
                    dynamicStats.style.display = 'none';
                    disableDynamicInsertion();
                }
            });
        }
        
        const addRandomLocationBtn = document.getElementById('add-random-location');
        if (addRandomLocationBtn) {
            addRandomLocationBtn.addEventListener('click', addRandomLocation);
        }
        
        const recalculateRoutesBtn = document.getElementById('recalculate-routes');
        if (recalculateRoutesBtn) {
            recalculateRoutesBtn.addEventListener('click', recalculateRoutes);
        }

        // Event listener for test type dropdown
        const testTypeSelect = document.getElementById('test-type');
        if (testTypeSelect) {
            testTypeSelect.addEventListener('change', handleTestTypeChange);
        }

        // Initial check in case the default is 'dynamic' (though it's 'static' now)
        handleTestTypeChange();
        
    } catch (e) {
        console.error("Error initializing VRP Testing page:", e);
        const container = document.getElementById('snapshots-container');
        if (container) {
            container.innerHTML = `<div class="alert alert-danger">
               Error initializing page: ${e.message}
               <br><br>
               <button onclick="location.reload()" class="btn btn-primary">Reload Page</button>
             </div>`;
        }
    }
});

// Add defensive checks to handleTestTypeChange
function handleTestTypeChange() {
    const testTypeElement = document.getElementById('test-type');
    if (!testTypeElement) return; // Early exit if element doesn't exist

    const testType = testTypeElement.value;
    const dynamicInputsDiv = document.getElementById('dynamic-inputs');
    if (dynamicInputsDiv) {
        if (testType === 'dynamic') {
            dynamicInputsDiv.classList.remove('hidden');
        } else {
            dynamicInputsDiv.classList.add('hidden');
            // Clear dynamic inputs when switching away
            const dynamicLocationsInput = document.getElementById('dynamic-locations-input');
            if (dynamicLocationsInput) dynamicLocationsInput.value = '';
            
            const dynamicInsertionControls = document.getElementById('dynamic-insertion-controls');
            if (dynamicInsertionControls) dynamicInsertionControls.innerHTML = '';
        }
    }
}

function createSnapshot() {
    // Show loading state
    const btn = document.getElementById('create-snapshot-btn');
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Creating Snapshot...';
    
    // Call API to create snapshot
    const url = '/vrp_testing/create_snapshot';
    const requestData = {};
    console.log('Sending request to:', url, 'with data:', requestData);
    fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        console.log('Response from server:', data);
        if (data.status === 'success') {
            alert('Snapshot created successfully');
            // Reload snapshots
            location.reload();
        } else {
            alert('Error: ' + data.message);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Failed to create snapshot');
    })
    .finally(() => {
        // Restore button state
        btn.disabled = false;
        btn.innerHTML = originalText;
    });
}

// Delete a snapshot
function deleteSnapshot(snapshotId) {
    if (confirm(`Are you sure you want to delete snapshot ${snapshotId}?`)) {
        const url = `/vrp_testing/delete_snapshot/${snapshotId}`;
        const requestData = {};
        console.log('Sending request to:', url, 'with data:', requestData);
        fetch(url, {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            console.log('Response from server:', data);
            if (data.status === 'success') {
                loadSnapshots(); // Reload the snapshots list
            } else {
                alert(`Error: ${data.message || 'Failed to delete snapshot'}`);
            }
        })
        .catch(error => {
            console.error('Error deleting snapshot:', error);
            alert('Failed to delete snapshot');
        });
    }
}

// Delete a test from history
function deleteTest(testId) {
    if (confirm(`Are you sure you want to delete test ${testId}?`)) {
        const url = `/vrp_testing/delete_test`;
        const requestData = { test_id: testId };
        
        console.log('Sending request to:', url, 'with data:', requestData);
        fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestData)
        })
        .then(response => response.json())
        .then(data => {
            console.log('Response from server:', data);
            if (data.status === 'success') {
                loadTestHistory();
            } else {
                alert(`Error: ${data.message || 'Failed to delete test'}`);
            }
        })
        .catch(error => {
            console.error('Error deleting test:', error);
            alert('Failed to delete test');
        });
    }
}

// Add defensive checks to showTestForm
function showTestForm(snapshotId) {
    const selectedSnapshotElement = document.getElementById('selected-snapshot');
    const selectedSnapshotBadge = document.getElementById('selected-snapshot-badge');
    const testForm = document.getElementById('test-form');
    const infoAlert = document.querySelector('#test-configuration .alert-info');
    
    if (selectedSnapshotElement) selectedSnapshotElement.value = snapshotId;
    if (selectedSnapshotBadge) selectedSnapshotBadge.textContent = `Snapshot: ${snapshotId}`;
    
    // Show the test form and hide the info message
    if (testForm) testForm.classList.remove('hidden');
    if (infoAlert) infoAlert.classList.add('hidden');
    
    // Load presets for this snapshot
    loadSnapshotPresets(snapshotId);
}

// Load presets for a selected snapshot
function loadSnapshotPresets(snapshotId) {
    const url = `/vrp_testing/presets/${snapshotId}`;
    const requestData = {};
    console.log('Sending request to:', url, 'with data:', requestData);
    fetch(url)
        .then(response => response.json())
        .then(data => {
            console.log('Response from server:', data);
            const presetSelect = document.getElementById('preset-select');
            presetSelect.innerHTML = '<option value="" disabled selected>-- Select preset --</option>';
            
            if (data.presets && data.presets.length > 0) {
                data.presets.forEach(preset => {
                    const option = document.createElement('option');
                    option.value = preset.id;
                    option.textContent = preset.name || `Preset ${preset.id}`;
                    presetSelect.appendChild(option);
                });
            } else {
                const option = document.createElement('option');
                option.value = "";
                option.textContent = "No presets available";
                option.disabled = true;
                presetSelect.appendChild(option);
            }
        })
        .catch(error => {
            console.error('Error loading presets:', error);
        });
}

// View a specific test
function viewTest(testId) {
    // Show loading state in results panel
    const resultsPanel = document.getElementById('results-panel');
    const resultsContent = document.getElementById('results-content');
    
    resultsPanel.classList.remove('hidden');
    resultsContent.innerHTML = '<div class="loading"><i class="fas fa-spinner fa-spin"></i> Loading test...</div>';
    
    // Fetch test data with the correct endpoint and format
    const url = `/vrp_testing/test_result/${testId}`;
    
    fetch(url)
        .then(response => response.json())
        .then(data => {
            console.log('Test data:', data);
            if (data.status === 'success') {
                // Store current solution for potential dynamic operations
                window.currentVrpSolution = data.result;
                window.currentTestConfig = {
                    snapshot_id: data.result.test_info?.snapshot_id,
                    preset_id: data.result.test_info?.preset_id,
                    algorithm: data.result.test_info?.algorithm,
                    num_vehicles: data.result.test_info?.num_vehicles,
                    test_type: data.result.test_info?.test_type || 'static'
                };
                
                // Display the test result
                displayTestResults(data.result, data.result.test_info?.test_type || 'static');
                
                // If dynamic test, set up insertion controls
                if (data.result.test_info?.test_type === 'dynamic') {
                    setupDynamicInsertionUI(data.result);
                }
            } else {
                resultsContent.innerHTML = `<div class="alert alert-danger">Error: ${data.message || 'Failed to load test'}</div>`;
            }
        })
        .catch(error => {
            console.error('Error loading test:', error);
            resultsContent.innerHTML = '<div class="alert alert-danger">An error occurred while loading the test</div>';
        });
}

function runTest() {
    // Add error checking for form elements
    const snapshotElement = document.getElementById('selected-snapshot');
    if (!snapshotElement) {
        console.error("Error: Could not find 'selected-snapshot' element");
        alert("Please select a snapshot first");
        return;
    }
    
    const presetElement = document.getElementById('preset-select');
    if (!presetElement || presetElement.value === "") {
        console.error("Error: Invalid preset selection");
        alert("Please select a preset");
        return;
    }
    
    // Get values with null checking
    const snapshotId = snapshotElement.value;
    const presetId = presetElement.value;
    const algorithm = document.getElementById('algorithm')?.value || 'or_tools';
    const numVehicles = parseInt(document.getElementById('num-vehicles')?.value || '1');
    const testType = document.getElementById('test-type')?.value || 'static';
    const apiKey = document.getElementById('api-key')?.value || '';
    
    // Prepare request data
    const requestData = {
        snapshot_id: snapshotId,
        preset_id: presetId,
        algorithm: algorithm,
        num_vehicles: numVehicles,
        test_type: testType,
        api_key: apiKey
    };
    
    // Show loading state
    const btn = document.getElementById('run-test-submit');
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Running Test...';
    
    // Show loading in results panel
    const resultsPanel = document.getElementById('results-panel');
    const resultsContent = document.getElementById('results-content');
    resultsPanel.classList.remove('hidden');
    resultsContent.innerHTML = '<div class="loading"><i class="fas fa-spinner fa-spin"></i> Running test...</div>';
    
    // Clear any previous dynamic insertion controls
    const dynamicInsertionControls = document.getElementById('dynamic-insertion-controls');
    if (dynamicInsertionControls) dynamicInsertionControls.innerHTML = '';
    
    // Call API to run test
    const url = '/vrp_testing/run_test';
    console.log('Sending request to:', url, 'with data:', requestData);
    
    fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestData)
    })
    .then(response => response.json())
    .then(data => {
        console.log('Response from server:', data);
        if (data.status === 'success') {
            // Store current solution for dynamic insertion
            window.currentVrpSolution = data.solution;
            window.currentTestConfig = requestData;
            
            // Display results
            displayTestResults(data.solution, testType);
            
            // Set up dynamic insertion UI if applicable
            if (testType === 'dynamic') {
                setupDynamicInsertionUI(data.solution);
            }
            
            // Refresh test history
            loadTestHistory();
        } else {
            resultsContent.innerHTML = `<div class="alert alert-danger">Error: ${data.message || 'Failed to run test'}</div>`;
        }
    })
    .catch(error => {
        console.error('Error:', error);
        resultsContent.innerHTML = '<div class="alert alert-danger">An error occurred while running the test</div>';
    })
    .finally(() => {
        // Restore button state
        btn.disabled = false;
        btn.innerHTML = originalText;
    });
}

/**
 * Displays test results in the results panel and visualizes routes on the map
 */
function displayTestResults(solution, testType) {
    const resultsPanel = document.getElementById('results-panel');
    const resultsContent = document.getElementById('results-content');
    resultsPanel.classList.remove('hidden');

    // Determine route type based on testType or solution structure
    const isCheckpointRoute = (testType === 'checkpoints' || testType === 'dynamic') || (solution.routes && solution.routes[0]?.stops && solution.routes[0].stops[0]?.type === 'checkpoint');

    // Add a more descriptive distance type label
    const distanceTypeLabel = solution.distance_type === 'road_network' ? 
        'Road Network (OpenRouteService)' : 
        (solution.distance_type === 'haversine' ? 
            'Straight-line (Haversine)' : solution.distance_type);

    let html = `
        <div class="results-summary">
            <h4>Test Results (${testType})</h4>
            <p><strong>Total Distance:</strong> ${solution.total_distance?.toFixed(2) || 'N/A'} km</p>
            <p><strong>Execution Time:</strong> ${solution.execution_time_ms || 'N/A'} ms</p>
            <p><strong>Vehicles Used:</strong> ${solution.routes?.length || 0} of ${solution.test_info?.num_vehicles || 'N/A'}</p>
            <p><strong>Distance Calculation:</strong> <span class="${solution.distance_type === 'road_network' ? 'text-success' : 'text-warning'}">${distanceTypeLabel}</span></p>
        </div>
    `;

    html += '<h5>Routes</h5>';
    if (solution.routes && Array.isArray(solution.routes) && solution.routes.length > 0) {
        solution.routes.forEach((route, index) => {
            const routeDistance = route.distance !== undefined ? route.distance.toFixed(2) : 'N/A';
            // Adjust stop count based on route type
            const stopCount = isCheckpointRoute ? 
                (route.stops?.length || 0) : 
                (route.stops?.length || 0);
            const stopLabel = isCheckpointRoute ? 'Checkpoints Visited' : 'Destinations Visited';

            html += `
                <div class="route mb-3 p-2 border rounded">
                    <h6>Vehicle ${index + 1}</h6>
                    <p><strong>Distance:</strong> ${routeDistance} km</p>
                    <p><strong>${stopLabel}:</strong> ${stopCount}</p>
                    <div class="route-path">
                        <strong>${isCheckpointRoute ? 'Checkpoint Sequence:' : 'Path:'}</strong>
                        <ol class="list-group list-group-numbered list-group-flush small">`;

            if (isCheckpointRoute && route.stops && Array.isArray(route.stops)) {
                 // Display checkpoint sequence
                 html += `<li class="list-group-item">Warehouse (Start)</li>`;
                 route.stops.forEach((stop, stopIdx) => {
                     const clusters = stop.clusters_served?.join(', ') || 'Unknown';
                     html += `<li class="list-group-item" data-route-index="${index}" data-stop-index="${stopIdx}">CP @ (${stop.lat?.toFixed(5)}, ${stop.lon?.toFixed(5)}) - Serves: ${clusters}</li>`;
                 });
                 html += `<li class="list-group-item">Warehouse (End)</li>`;
            } else if (!isCheckpointRoute && route.path && Array.isArray(route.path)) {
                // Display destination path (like original static)
                route.path.forEach((stop, stopIdx) => {
                    const stopType = stopIdx === 0 || stopIdx === route.path.length - 1 ? 'Warehouse' : `Destination ${stopIdx}`;
                    const stopLat = stop.lat !== undefined ? stop.lat.toFixed(5) : 'N/A';
                    const stopLon = stop.lon !== undefined ? stop.lon.toFixed(5) : 'N/A';
                    html += `<li class="list-group-item">${stopType} (${stopLat}, ${stopLon})</li>`;
                });
            } else {
                html += `<li class="list-group-item">No path data available.</li>`;
            }

            html += `   </ol>
                    </div>
                </div>`;
        });
    } else {
        html += `<p>No routes generated or available.</p>`;
    }

    resultsContent.innerHTML = html; // Render text results first

    // Add map display logic
    const mapElement = document.getElementById('test-map');
    if (mapElement) {
        mapElement.innerHTML = ''; // Clear previous map

        // *** ADD CHECK HERE ***
        if (solution && solution.warehouse && typeof solution.warehouse.lat === 'number' && typeof solution.warehouse.lon === 'number') {
            try {
                // Map creation might fail if Leaflet isn't loaded or div isn't ready
                const map = Utils.createMap('test-map', [solution.warehouse.lat, solution.warehouse.lon], 13);
                if (map) { // Check if map was created successfully
                     displayRouteOnMap(map, solution, isCheckpointRoute); // Pass flag
                } else {
                     console.error("Failed to create map instance.");
                     mapElement.innerHTML = '<div class="alert alert-danger">Error creating map.</div>';
                }
            } catch (mapError) {
                console.error("Error during map creation/display:", mapError);
                mapElement.innerHTML = `<div class="alert alert-danger">Error displaying map: ${mapError.message}</div>`;
            }
        } else {
            console.error("Map data incomplete or invalid warehouse:", solution ? solution.warehouse : 'solution undefined');
            mapElement.innerHTML = '<div class="alert alert-warning">Map data incomplete (missing or invalid warehouse coordinates).</div>';
        }
    }

    if (typeof ensureLayoutIntegrity === 'function') {
        ensureLayoutIntegrity();
    }
}

// Modify displayRouteOnMap to handle checkpoint routes
function displayRouteOnMap(map, solution, isCheckpointRoute) {
    // Add warehouse marker
    const warehouseIcon = L.divIcon({
        className: 'warehouse-icon',
        html: '<i class="fas fa-warehouse"></i>',
        iconSize: [20, 20]
    });
    L.marker([solution.warehouse.lat, solution.warehouse.lon], {icon: warehouseIcon})
        .addTo(map)
        .bindPopup('Warehouse');

    const colors = ['#f44336', '#2196f3', '#4caf50', '#ff9800', '#9c27b0', '#00bcd4', '#ffeb3b', '#795548'];

    if (solution.routes && Array.isArray(solution.routes)) {
        solution.routes.forEach((route, index) => {
            const color = colors[index % colors.length];
            let points = [];

            if (isCheckpointRoute && route.path && Array.isArray(route.path)) {
                 // Checkpoint route path already includes warehouse start/end and checkpoints
                 points = route.path.map(stop =>
                     stop && stop.lat !== undefined && stop.lon !== undefined ? [stop.lat, stop.lon] : null
                 ).filter(p => p !== null);
            } else if (!isCheckpointRoute && route.path && Array.isArray(route.path)) {
                 // Static route path includes warehouse start/end and destinations
                 points = route.path.map(stop =>
                     stop && stop.lat !== undefined && stop.lon !== undefined ? [stop.lat, stop.lon] : null
                 ).filter(p => p !== null);
            }

            if (points.length > 1) {
                L.polyline(points, { color: color, weight: 5, opacity: 0.7 }).addTo(map);
            }

            // Add markers for stops
            if (isCheckpointRoute && route.stops && Array.isArray(route.stops)) {
                // Checkpoint markers
                const checkpointIcon = L.divIcon({
                    className: 'checkpoint-icon',
                    html: `CP`, // Generic CP label
                    iconSize: [16, 16]
                });
                route.stops.forEach((stop, stopIdx) => {
                    if (stop && stop.lat !== undefined && stop.lon !== undefined) {
                        L.marker([stop.lat, stop.lon], { icon: checkpointIcon })
                            .addTo(map)
                            .bindPopup(`CP (Route ${index + 1})<br>Serves: ${stop.clusters_served?.join(', ') || 'N/A'}`); // Add Route index
                    }
                });
            } else if (!isCheckpointRoute && route.destination_coords && Array.isArray(route.destination_coords)) {
                // Static destination markers
                route.destination_coords.forEach((dest_coord, stopIdx) => {
                    if (dest_coord && dest_coord.lat !== undefined && dest_coord.lon !== undefined) {
                        // Use route index for color/label if needed, here we use stop order number
                        const icon = L.divIcon({
                            className: 'destination-icon',
                            html: stopIdx + 1, // Display stop number in sequence for this route
                            iconSize: [16, 16],
                            // Optionally add style based on route index 'index' if needed
                            // style: `background-color: ${colors[index % colors.length]};` // Example
                        });
                        L.marker([dest_coord.lat, dest_coord.lon], { icon: icon })
                            .addTo(map)
                            .bindPopup(`Destination ${stopIdx + 1} (Route ${index + 1})`); // Add Route index
                    }
                });
            }
        });
    }
}

// NEW: Function to set up UI for dynamic insertion
function setupDynamicInsertionUI(solution) {
    const controlsDiv = document.getElementById('dynamic-insertion-controls');
    if (!controlsDiv || !solution || !solution.routes || solution.routes.length === 0) {
        controlsDiv.innerHTML = '<p class="text-muted">No routes available for dynamic insertion.</p>';
        return;
    }

    // Assuming single vehicle for simplicity now, extend later if needed
    const route = solution.routes[0];
    if (!route.stops || route.stops.length === 0) {
         controlsDiv.innerHTML = '<p class="text-muted">Route has no checkpoints for insertion.</p>';
         return;
    }

    let optionsHtml = '<option value="0">After Warehouse (Start)</option>'; // Insert after start
    route.stops.forEach((stop, index) => {
        optionsHtml += `<option value="${index + 1}">After Checkpoint ${index + 1} (${stop.lat.toFixed(4)}, ${stop.lon.toFixed(4)})</option>`;
    });

    controlsDiv.innerHTML = `
        <div class="form-group mb-2">
            <label for="insertion-point-select" class="form-label">Insert New Location(s) After:</label>
            <select id="insertion-point-select" class="form-select form-select-sm">
                ${optionsHtml}
            </select>
        </div>
        <button id="insert-dynamic-btn" class="btn btn-warning btn-sm">
            <i class="fas fa-plus-circle"></i> Insert & Recalculate Route
        </button>
    `;

    // Add event listener to the new button
    const insertBtn = document.getElementById('insert-dynamic-btn');
    if (insertBtn) {
        insertBtn.addEventListener('click', handleDynamicInsertion);
    }
}

// NEW: Function to handle the dynamic insertion request
function handleDynamicInsertion() {
    const insertionIndex = parseInt(document.getElementById('insertion-point-select').value);
    const dynamicLocationsText = document.getElementById('dynamic-locations-input').value.trim();
    const newLocations = [];

    if (!dynamicLocationsText) {
        alert('Please enter dynamic locations (Lat,Lon) to insert.');
        return;
    }

    // Parse dynamic locations (similar to runStaticDynamicComparison)
    const lines = dynamicLocationsText.split('\n');
    lines.forEach((line, index) => {
        const parts = line.split(',');
        if (parts.length === 2) {
            const lat = parseFloat(parts[0].trim());
            const lon = parseFloat(parts[1].trim());
            if (!isNaN(lat) && !isNaN(lon)) {
                newLocations.push({ id: `dynamic_insert_${index + 1}`, lat: lat, lon: lon });
            } else { console.warn(`Invalid coordinate format on line ${index + 1}: ${line}`); }
        } else { console.warn(`Skipping invalid line ${index + 1}: ${line}`); }
    });

    if (newLocations.length === 0) {
        alert('No valid dynamic locations entered.');
        return;
    }

    if (window.currentVrpSolution && window.currentTestConfig) {
        // Show loading state
        const btn = document.getElementById('insert-dynamic-btn');
        const originalText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Inserting...';
        document.getElementById('results-content').innerHTML = '<div class="loading"><i class="fas fa-spinner fa-spin"></i> Recalculating route...</div>';


        const url = '/vrp_testing/insert_dynamic';
        const requestData = {
            current_solution: window.currentVrpSolution, // Send the whole current solution
            prepared_data_ref: { // Send references to recreate prepared_data if needed
                 snapshot_id: window.currentTestConfig.snapshot_id,
                 preset_id: window.currentTestConfig.preset_id
            },
            insertion_index: insertionIndex, // Where to insert *after* (0=after warehouse, 1=after 1st CP, etc.)
            new_locations: newLocations,
            num_vehicles: window.currentTestConfig.num_vehicles, // Pass original config
            algorithm: window.currentTestConfig.algorithm
        };

        console.log('Sending dynamic insertion request:', requestData);

        fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestData)
        })
        .then(response => response.json())
        .then(data => {
            console.log('Dynamic insertion response:', data);
            if (data.status === 'success') {
                // Update the stored solution and redisplay
                window.currentVrpSolution = data.updated_solution;
                displayTestResults(data.updated_solution, 'dynamic'); // Redisplay as dynamic
                setupDynamicInsertionUI(data.updated_solution); // Re-setup UI with new route
                alert('Route updated with dynamic locations.');
            } else {
                alert(`Error inserting dynamic locations: ${data.message}`);
                // Restore previous view?
                displayTestResults(window.currentVrpSolution, 'dynamic');
                setupDynamicInsertionUI(window.currentVrpSolution);
            }
        })
        .catch(error => {
            console.error('Dynamic insertion error:', error);
            alert('An error occurred during dynamic insertion.');
            // Restore previous view?
            displayTestResults(window.currentVrpSolution, 'dynamic');
            setupDynamicInsertionUI(window.currentVrpSolution);
        })
        .finally(() => {
             // Restore button state (or maybe remove it if insertion is one-time?)
             btn.disabled = false;
             btn.innerHTML = originalText;
        });

    } else {
        alert('Cannot perform dynamic insertion: Initial solution data not found.');
    }
}

// Add defensive checks to loadTestHistory
function loadTestHistory() {
    const url = '/vrp_testing/test_history';
    fetch(url)
        .then(response => response.json())
        .then(data => {
            console.log('Response from server:', data);
            if (data.status === 'success') {
                const testHistoryContent = document.getElementById('test-history-content');
                if (!testHistoryContent) {
                    console.warn('Test history container not found');
                    return;
                }
                
                if (data.tests && data.tests.length > 0) {
                    // Create table for test history
                    let html = `
                        <table class="table">
                            <thead>
                                <tr>
                                    <th><input type="checkbox" id="select-all-tests"></th>
                                    <th>ID</th>
                                    <th>Date</th>
                                    <th>Algorithm</th>
                                    <th>Vehicles</th>
                                    <th>Test Type</th>
                                    <th>Distance (km)</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                    `;
                    
                    data.tests.forEach(test => {
                        html += `
                            <tr>
                                <td><input type="checkbox" class="test-checkbox select-test-cb" value="${test.id}"></td>
                                <td>${test.id}</td>
                                <td>${test.test_info && test.test_info.timestamp ? 
                                    new Date(test.test_info.timestamp).toLocaleString() : 
                                    new Date(test.created_at || Date.now()).toLocaleString()}</td>
                                <td>${test.test_info ? test.test_info.algorithm : 'N/A'}</td>
                                <td>${test.test_info ? test.test_info.num_vehicles : 'N/A'}</td>
                                <td>${test.test_info ? (test.test_info.test_type || 'N/A') : 'N/A'}</td>
                                <td>${test.total_distance !== undefined && test.total_distance !== null ? 
                                    test.total_distance.toFixed(2) : 'N/A'}</td>
                                <td>
                                    <button class="btn btn-sm btn-info view-test-btn" data-test-id="${test.id}">
                                        <i class="fas fa-eye"></i> View
                                    </button>
                                    <button class="btn btn-sm btn-danger delete-test-btn" data-test-id="${test.id}">
                                        <i class="fas fa-trash"></i> Delete
                                    </button>
                                </td>
                            </tr>
                        `;
                    });
                    
                    html += `</tbody></table>`;
                    testHistoryContent.innerHTML = html;
                    
                    // Add event listeners for delete buttons
                    document.querySelectorAll('.delete-test-btn').forEach(button => {
                        button.addEventListener('click', function(e) {
                            const testId = this.getAttribute('data-test-id');
                            if (confirm('Are you sure you want to delete this test?')) {
                                deleteTest(testId);
                            }
                        });
                    });
                    
                    // Add event listeners for view buttons
                    document.querySelectorAll('.view-test-btn').forEach(button => {
                        button.addEventListener('click', function() {
                            const testId = this.getAttribute('data-test-id');
                            viewTest(testId);
                        });
                    });
                    
                    // Handle select all checkbox
                    const selectAllCheckbox = document.getElementById('select-all-tests');
                    if (selectAllCheckbox) {
                        selectAllCheckbox.addEventListener('change', function() {
                            document.querySelectorAll('.test-checkbox').forEach(cb => {
                                cb.checked = this.checked;
                            });
                            updateCompareButtonState();
                        });
                    }
                    
                    // Add listeners for individual checkboxes
                    document.querySelectorAll('.test-checkbox').forEach(checkbox => {
                        checkbox.addEventListener('change', updateCompareButtonState);
                    });
                    
                    // Initial state of compare button
                    updateCompareButtonState();
                    
                } else {
                    testHistoryContent.innerHTML = '<p>No tests have been run yet.</p>';
                    const compareBtn = document.getElementById('compare-tests-btn');
                    if (compareBtn) compareBtn.disabled = true;
                }
            }
        })
        .catch(error => {
            console.error('Error loading test history:', error);
        });
}

/**
 * Updates the state of the compare button based on selected tests
 */
function updateCompareButtonState() {
    const compareBtn = document.getElementById('compare-tests-btn');
    if (!compareBtn) return;
    
    const selectedTests = document.querySelectorAll('.test-checkbox:checked');
    compareBtn.disabled = selectedTests.length < 2;
}

/**
 * Compares multiple selected tests from test history
 */
function compareTests() {
    // Get all checked test checkboxes
    const selectedTests = document.querySelectorAll('.test-checkbox:checked');
    const testIds = Array.from(selectedTests).map(cb => cb.value);
    
    if (testIds.length < 2) {
        alert('Please select at least 2 tests to compare');
        return;
    }
    
    // Show loading state in results panel
    const resultsPanel = document.getElementById('results-panel');
    const resultsContent = document.getElementById('results-content');
    
    resultsPanel.classList.remove('hidden');
    resultsContent.innerHTML = '<div class="loading"><i class="fas fa-spinner fa-spin"></i> Loading test comparison...</div>';
    
    // Fetch test data for comparison
    const url = '/vrp_testing/get_tests';
    const requestData = { test_ids: testIds };
    console.log('Sending request to:', url, 'with data:', requestData);
    fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestData)
    })
    .then(response => response.json())
    .then(data => {
        console.log('Response from server:', data);
        if (data.status === 'success') {
            displayTestComparison(data.tests);
        } else {
            resultsContent.innerHTML = `<div class="alert alert-danger">Error: ${data.message || 'Failed to load test comparison'}</div>`;
        }
    })
    .catch(error => {
        console.error('Error loading test comparison:', error);
        resultsContent.innerHTML = '<div class="alert alert-danger">An error occurred while loading the test comparison</div>';
    });
}

/**
 * Displays a comparison of multiple tests
 */
function displayTestComparison(tests) {
    const resultsContent = document.getElementById('results-content');
    
    // Create comparison table
    let html = `
        <h4>Test Comparison</h4>
        <table class="table table-striped">
            <thead>
                <tr>
                    <th>Test ID</th>
                    <th>Date</th>
                    <th>Algorithm</th>
                    <th>Vehicles</th>
                    <th>Checkpoints</th>
                    <th>Total Distance</th>
                    <th>Time (ms)</th>
                </tr>
            </thead>
            <tbody>
    `;
    
    tests.forEach(test => {
        html += `
            <tr>
                <td>${test.id}</td>
                <td>${new Date(test.created_at || test.test_info?.timestamp || Date.now()).toLocaleString()}</td>
                <td>${test.test_info?.algorithm || 'N/A'}</td>
                <td>${test.test_info?.num_vehicles || 'N/A'}</td>
                <td>${test.test_info?.use_checkpoints ? 'Yes' : 'No'}</td>
                <td>${test.total_distance !== undefined ? test.total_distance.toFixed(2) : 'N/A'} km</td>
                <td>${test.test_info?.execution_time_ms || 'N/A'}</td>
            </tr>
        `;
    });
    
    html += `
            </tbody>
        </table>
        
        <h5 class="mt-4">Performance Comparison</h5>
        <div>
            <canvas id="comparison-chart" width="400" height="200"></canvas>
        </div>
    `;
    
    resultsContent.innerHTML = html;
    
    // Create a chart for visual comparison (if Chart.js is available)
    if (typeof Chart !== 'undefined') {
        const ctx = document.getElementById('comparison-chart').getContext('2d');
        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: tests.map(t => `Test ${t.id}`),
                datasets: [
                    {
                        label: 'Total Distance (km)',
                        data: tests.map(t => t.total_distance),
                        backgroundColor: 'rgba(54, 162, 235, 0.5)',
                        borderColor: 'rgba(54, 162, 235, 1)',
                        borderWidth: 1
                    },
                    {
                        label: 'Execution Time (ms)',
                        data: tests.map(t => t.test_info?.execution_time_ms || 0),
                        backgroundColor: 'rgba(255, 99, 132, 0.5)',
                        borderColor: 'rgba(255, 99, 132, 1)',
                        borderWidth: 1
                    }
                ]
            },
            options: {
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        });
    }
    
    // Scroll to results
    document.getElementById('results-panel').scrollIntoView({ behavior: 'smooth' });
    ensureLayoutIntegrity();
}

// Add this function after your other functions
function ensureLayoutIntegrity() {
    // Fix table overflow
    document.querySelectorAll('.table').forEach(table => {
        table.parentElement.style.overflow = 'auto';
    });
    
    // Add spacing to dynamically created elements
    document.querySelectorAll('.panel, .card').forEach(panel => {
        panel.style.marginBottom = '30px';
    });
    
    // Ensure result content has proper spacing
    const resultsContent = document.getElementById('results-content');
    if (resultsContent) {
        resultsContent.style.padding = '20px 0';
    }
}