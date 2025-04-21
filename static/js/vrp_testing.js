let dynamicPickingState = 'idle'; // 'idle', 'picking_pickup', 'picking_dropoff'
let tempPickupCoords = null;
let tempDropoffCoords = null;
let tempPickupMarker = null;
let tempDropoffMarker = null;
let dynamicLocationPairs = []; // To store processed pairs [{pickup: {...}, dropoff: {...}}, ...]
let currentDynamicMapInstance = null; // Store the map instance used for picking
let currentVrpSolution = null; // Store the initial solution for reference
let currentTestConfig = null; // Store the config used for the initial run

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
                currentVrpSolution = data.result;
                currentTestConfig = {
                    snapshot_id: data.result.test_info?.snapshot_id,
                    preset_id: data.result.test_info?.preset_id,
                    algorithm: data.result.test_info?.algorithm,
                    num_vehicles: data.result.test_info?.num_vehicles,
                    test_type: data.result.test_info?.test_type || 'static',
                    api_key: '' // API key might not be stored, retrieve if needed
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
            currentVrpSolution = data.solution;
            currentTestConfig = requestData;
            
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
    const dynamicSection = document.getElementById('dynamic-section');
    const dynamicLocationsList = document.getElementById('dynamic-locations-list');
    const mapElement = document.getElementById('test-map');
    
    resultsPanel.classList.remove('hidden');
    dynamicSection.classList.add('hidden');
    dynamicLocationsList.innerHTML = '';
    dynamicLocationPairs = []; // Reset stored pairs
    
    // Clean up previous map if it exists
    if (currentDynamicMapInstance) {
        console.log("Removing existing map instance");
        currentDynamicMapInstance.remove();
        currentDynamicMapInstance = null;
    }
    
    if (mapElement) {
        mapElement.innerHTML = ''; // Clear previous map element content
    }

    // Determine route type based on testType or solution structure
    const isCheckpointRoute = (testType === 'checkpoints' || testType === 'dynamic') || 
                             (solution.routes && solution.routes[0]?.stops && 
                              solution.routes[0].stops[0]?.type === 'checkpoint');

    // Add a more descriptive distance type label
    const distanceTypeLabel = solution.distance_type === 'road_network' ? 
        'Road Network (OpenRouteService)' : 
        (solution.distance_type === 'haversine' ? 
            'Straight-line (Haversine)' : solution.distance_type || 'Unknown');

    // Generate HTML content for results summary
    let html = `
        <div class="results-summary">
            <h4>Test Results (${testType})</h4>
            <p><strong>Total Distance:</strong> ${solution.total_distance?.toFixed(2) || 'N/A'} km</p>
            <p><strong>Execution Time:</strong> ${solution.execution_time_ms || 'N/A'} ms</p>
            <p><strong>Vehicles Used:</strong> ${solution.routes?.length || 0} of ${solution.test_info?.num_vehicles || 'N/A'}</p>
            <p><strong>Distance Calculation:</strong> <span class="${solution.distance_type === 'road_network' ? 'text-success' : 'text-warning'}">${distanceTypeLabel}</span></p>
        </div>
    `;

    // Add cluster coverage section for checkpoint routes
    if (isCheckpointRoute) {
        // Create a map of clusters to checkpoints that cover them
        const clusterCoverage = {};
        
        solution.routes.forEach((route, routeIdx) => {
            route.stops?.forEach(stop => {
                if (stop.clusters_served && Array.isArray(stop.clusters_served)) {
                    stop.clusters_served.forEach(clusterId => {
                        if (!clusterCoverage[clusterId]) {
                            clusterCoverage[clusterId] = [];
                        }
                        clusterCoverage[clusterId].push({
                            routeIdx,
                            lat: stop.lat,
                            lon: stop.lon
                        });
                    });
                }
            });
        });
        
        // Generate cluster coverage summary table
        html += `<div class="card mb-4">
            <div class="card-header">
                <h5>Cluster Coverage Summary</h5>
            </div>
            <div class="card-body">
                <table class="table table-sm">
                    <thead>
                        <tr>
                            <th>Cluster ID</th>
                            <th>Covered By Checkpoints</th>
                            <th>In Route(s)</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>`;

        // Get all required clusters
        const allRequiredClusters = new Set([
             ...Object.keys(clusterCoverage).map(Number),
             ...(solution.missing_clusters || [])
            ]);

        // Sort cluster IDs numerically for consistent display
        const sortedClusterIds = Array.from(allRequiredClusters).sort((a, b) => a - b);

        // Generate rows for each cluster
        sortedClusterIds.forEach(clusterId => {
            const checkpoints = clusterCoverage[clusterId];
            const isMissing = solution.missing_clusters && solution.missing_clusters.includes(clusterId);

            let cpList = '-';
            let routes = '-';
            let statusHtml = '';

            if (isMissing) {
                cpList = '<span class="text-danger">Not Covered</span>';
                routes = '-';
                statusHtml = '<span class="badge bg-danger">Skipped</span>';
            } else if (checkpoints && checkpoints.length > 0) {
                // Format list of unique checkpoint coordinates covering this cluster
                const uniqueCheckpoints = {};
                checkpoints.forEach(cp => {
                    const key = `${cp.lat.toFixed(5)},${cp.lon.toFixed(5)}`;
                    if (!uniqueCheckpoints[key]) {
                        uniqueCheckpoints[key] = { lat: cp.lat, lon: cp.lon, routes: new Set() };
                    }
                    uniqueCheckpoints[key].routes.add(cp.routeIdx + 1);
                });

                cpList = Object.values(uniqueCheckpoints).map(cp =>
                    `CP @ (${cp.lat.toFixed(5)}, ${cp.lon.toFixed(5)})`
                ).join('<br>');

                // List unique vehicle routes involved
                const uniqueRoutes = new Set();
                checkpoints.forEach(cp => uniqueRoutes.add(cp.routeIdx + 1));
                routes = Array.from(uniqueRoutes).sort((a, b) => a - b).join(', ');
                statusHtml = '<span class="badge bg-success">Covered</span>';
            } else {
                 cpList = '<span class="text-warning">Coverage Unknown</span>';
                 routes = '-';
                 statusHtml = '<span class="badge bg-warning">Unknown</span>';
            }

            html += `<tr>
                <td>${clusterId}</td>
                <td>${cpList}</td>
                <td>${routes ? `Vehicle ${routes}` : '-'}</td>
                <td>${statusHtml}</td>
            </tr>`;
        });

        html += `</tbody></table></div></div>`;
    }

    // Add routes section
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

    resultsContent.innerHTML = html;

    // Initialize and display map
    if (mapElement) {
        try {
            // Extract warehouse coordinates with fallback options
            let warehouseCoords = [1.3521, 103.8198]; // Default to Singapore
            let validWarehouse = false;
            
            if (solution) {
                if (solution.warehouse) {
                    if (Array.isArray(solution.warehouse) && solution.warehouse.length >= 2) {
                        warehouseCoords = [solution.warehouse[0], solution.warehouse[1]];
                        validWarehouse = true;
                    } else if (typeof solution.warehouse === 'object') {
                        if (typeof solution.warehouse.lat === 'number' && 
                            (typeof solution.warehouse.lon === 'number' || typeof solution.warehouse.lng === 'number')) {
                            warehouseCoords = [
                                solution.warehouse.lat, 
                                solution.warehouse.lon || solution.warehouse.lng
                            ];
                            validWarehouse = true;
                        }
                    }
                } else if (solution.routes && solution.routes.length > 0) {
                    // Try to find warehouse in the first route
                    const firstRoute = solution.routes[0];
                    if (firstRoute.path && firstRoute.path.length > 0) {
                        const firstPoint = firstRoute.path[0];
                        if (firstPoint && typeof firstPoint.lat === 'number' && 
                            (typeof firstPoint.lon === 'number' || typeof firstPoint.lng === 'number')) {
                            warehouseCoords = [
                                firstPoint.lat, 
                                firstPoint.lon || firstPoint.lng
                            ];
                            validWarehouse = true;
                        }
                    }
                }
            }
            
            console.log("Creating new map with center:", warehouseCoords);
            
            // Create a new map instance
            const map = L.map('test-map').setView(warehouseCoords, 13);
            currentDynamicMapInstance = map;
            
            // Add the tile layer
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            }).addTo(map);
            
            // Display routes if available
            if (solution && solution.routes) {
                displayRouteOnMap(map, solution, isCheckpointRoute);
            }
            
            // Setup dynamic functionality if needed
            if (testType === 'dynamic') {
                setupDynamicPicking(map);
                setupDynamicInsertionUI(solution);
                dynamicSection.classList.remove('hidden');
            }
        } catch (mapError) {
            console.error("Error during map creation/display:", mapError);
            mapElement.innerHTML = `<div class="alert alert-danger">Error displaying map: ${mapError.message}</div>`;
        }
    }

    if (typeof ensureLayoutIntegrity === 'function') {
        ensureLayoutIntegrity();
    }
}

// Function to set up dynamic location picking
function setupDynamicPicking(map) {
    const addPairBtn = document.getElementById('add-dynamic-pair-btn');
    const instructions = document.getElementById('dynamic-instructions');

    if (!addPairBtn || !instructions || !map) {
        console.error("Missing elements needed for dynamic picking setup");
        return;
    }

    addPairBtn.onclick = () => {
        if (dynamicPickingState === 'idle') {
            dynamicPickingState = 'picking_pickup';
            instructions.textContent = 'Click on the map to select the PICKUP location.';
            addPairBtn.innerHTML = '<i class="fas fa-times"></i> Cancel Picking';
            addPairBtn.classList.remove('btn-primary');
            addPairBtn.classList.add('btn-secondary');
            map.getContainer().style.cursor = 'crosshair';
        } else {
            // Cancel picking
            resetPickingState(map);
        }
    };

    map.off('click');
    map.on('click', handleDynamicMapClick);
}

// Function to handle clicks on the map during dynamic picking
function handleDynamicMapClick(e) {
    if (!currentDynamicMapInstance) return; // Ensure map exists

    if (dynamicPickingState === 'picking_pickup') {
        tempPickupCoords = e.latlng;
        if (tempPickupMarker) tempPickupMarker.remove(); // Remove previous temp marker
        tempPickupMarker = L.marker(tempPickupCoords, { icon: Utils.createSimpleIcon('P', 'green') }).addTo(currentDynamicMapInstance);
        tempPickupMarker.bindPopup('Temporary Pickup').openPopup();

        dynamicPickingState = 'picking_dropoff';
        document.getElementById('dynamic-instructions').textContent = 'Click on the map to select the DROPOFF location.';
        // Keep button as Cancel

    } else if (dynamicPickingState === 'picking_dropoff') {
        tempDropoffCoords = e.latlng;
        if (tempDropoffMarker) tempDropoffMarker.remove(); // Remove previous temp marker
        tempDropoffMarker = L.marker(tempDropoffCoords, { icon: Utils.createSimpleIcon('D', 'red') }).addTo(currentDynamicMapInstance);
        tempDropoffMarker.bindPopup('Temporary Dropoff').openPopup();

        // Both points selected, process the pair
        processNewPair(tempPickupCoords, tempDropoffCoords);
        resetPickingState(currentDynamicMapInstance); // Reset state after selection
    }
}

// Function to reset the picking state
function resetPickingState(map) {
    const addPairBtn = document.getElementById('add-dynamic-pair-btn');
    const instructions = document.getElementById('dynamic-instructions');

    dynamicPickingState = 'idle';
    tempPickupCoords = null;
    tempDropoffCoords = null;
    if (tempPickupMarker) tempPickupMarker.remove();
    if (tempDropoffMarker) tempDropoffMarker.remove();
    tempPickupMarker = null;
    tempDropoffMarker = null;

    instructions.textContent = 'Click the button below, then click on the map to select a pickup location, followed by a dropoff location.';
    addPairBtn.innerHTML = '<i class="fas fa-map-marker-alt"></i> Add New Location Pair';
    addPairBtn.classList.remove('btn-secondary');
    addPairBtn.classList.add('btn-primary');
    if (map) map.getContainer().style.cursor = '';
}

// Function to process the selected pair (calls backend)
function processNewPair(pickupCoords, dropoffCoords) {
    console.log("Processing new pair:", pickupCoords, dropoffCoords);
    const dynamicLocationsList = document.getElementById('dynamic-locations-list');
    const loadingHtml = `<div class="list-group-item list-group-item-action temp-processing">
                            <div class="d-flex w-100 justify-content-between">
                                <h6 class="mb-1"><i class="fas fa-spinner fa-spin"></i> Processing new pair...</h6>
                            </div>
                            <small>Pickup: ${pickupCoords.lat.toFixed(5)}, ${pickupCoords.lng.toFixed(5)}</small><br>
                            <small>Dropoff: ${dropoffCoords.lat.toFixed(5)}, ${dropoffCoords.lng.toFixed(5)}</small>
                         </div>`;
    dynamicLocationsList.insertAdjacentHTML('beforeend', loadingHtml);

    // Use the globally stored config
    const snapshotId = currentTestConfig?.snapshot_id;
    const presetId = currentTestConfig?.preset_id;

    if (!snapshotId || !presetId) {
         alert("Error: Cannot process dynamic pair without snapshot/preset context from the initial test run.");
         document.querySelector('.temp-processing')?.remove();
         return;
    }

    fetch('/vrp_testing/process_dynamic_pair', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            pickup_lat: pickupCoords.lat,
            pickup_lon: pickupCoords.lng,
            dropoff_lat: dropoffCoords.lat,
            dropoff_lon: dropoffCoords.lng,
            snapshot_id: snapshotId,
            preset_id: presetId
        })
    })
    .then(response => response.json())
    .then(data => {
        document.querySelector('.temp-processing')?.remove(); // Remove loading indicator
        if (data.status === 'success') {
            console.log("Processed pair data:", data.pair_info);
            dynamicLocationPairs.push(data.pair_info); // Store the processed pair
            displayProcessedPair(data.pair_info); // Add to the list display
            // Enable insertion button if pairs exist
            const insertBtn = document.getElementById('insert-dynamic-btn');
            if (insertBtn) insertBtn.disabled = false;
        } else {
            alert(`Error processing pair: ${data.message}`);
        }
    })
    .catch(error => {
        document.querySelector('.temp-processing')?.remove();
        console.error('Error processing dynamic pair:', error);
        alert('An error occurred while processing the location pair.');
    });
}

// Function to display a processed pair in the list
function displayProcessedPair(pairInfo) {
    const dynamicLocationsList = document.getElementById('dynamic-locations-list');
    const pickupCluster = pairInfo.pickup.cluster_id ? `Cluster ${pairInfo.pickup.cluster_id}` : 'N/A';
    const dropoffCluster = pairInfo.dropoff.cluster_id ? `Cluster ${pairInfo.dropoff.cluster_id}` : 'N/A';
    const pickupCPs = pairInfo.pickup.checkpoints.length > 0 ? pairInfo.pickup.checkpoints.map(cp => `CP #${cp.id}`).join(', ') : 'None';
    const dropoffCPs = pairInfo.dropoff.checkpoints.length > 0 ? pairInfo.dropoff.checkpoints.map(cp => `CP #${cp.id}`).join(', ') : 'None';

    const pairHtml = `
        <div class="list-group-item list-group-item-action">
            <div class="d-flex w-100 justify-content-between">
                <h6 class="mb-1">New Location Pair #${dynamicLocationPairs.length}</h6>
                <small>${new Date().toLocaleTimeString()}</small>
            </div>
            <p class="mb-1 small">
                <strong>Pickup:</strong> (${pairInfo.pickup.lat.toFixed(5)}, ${pairInfo.pickup.lon.toFixed(5)}) - ${pairInfo.pickup.address?.street || 'Unknown Street'} <br>
                &nbsp;&nbsp;↳ Cluster: ${pickupCluster}, Checkpoints: ${pickupCPs}
            </p>
            <p class="mb-1 small">
                <strong>Dropoff:</strong> (${pairInfo.dropoff.lat.toFixed(5)}, ${pairInfo.dropoff.lon.toFixed(5)}) - ${pairInfo.dropoff.address?.street || 'Unknown Street'} <br>
                &nbsp;&nbsp;↳ Cluster: ${dropoffCluster}, Checkpoints: ${dropoffCPs}
            </p>
        </div>`;
    dynamicLocationsList.insertAdjacentHTML('beforeend', pairHtml);
}

// Helper to create simple icons for temp markers
Utils.createSimpleIcon = function(text, color) {
    return L.divIcon({
        className: 'simple-marker',
        html: `<div style="background-color:${color}; color:white; border-radius:50%; width:20px; height:20px; display:flex; align-items:center; justify-content:center; font-size:12px; font-weight:bold;">${text}</div>`,
        iconSize: [20, 20],
        iconAnchor: [10, 10]
    });
};

// Display routes on map with checkpoint handling
function displayRouteOnMap(map, solution, isCheckpointRoute) {
    if (!map || !solution) {
        console.error("Invalid map or solution for route display");
        return;
    }

    // Clear any existing layers
    if (window.routeLayers && window.routeLayers.length) {
        window.routeLayers.forEach(layer => {
            if (layer && map.hasLayer(layer)) {
                map.removeLayer(layer);
            }
        });
    }
    window.routeLayers = [];

    // Define colors for routes
    const colors = ['#f44336', '#2196f3', '#4caf50', '#ff9800', '#9c27b0', '#00bcd4', '#ffeb3b', '#795548'];

    // Display warehouse marker (using original warehouse context if available)
    try {
        let warehouseLat, warehouseLon;
        // Use the warehouse from the main solution context, not potentially the subproblem start point
        const mainWarehouse = solution.test_info?.original_warehouse || solution.warehouse; // Prefer original if available
        if (mainWarehouse) {
             if (Array.isArray(mainWarehouse) && mainWarehouse.length >= 2) {
                warehouseLat = mainWarehouse[0];
                warehouseLon = mainWarehouse[1];
            } else if (typeof mainWarehouse === 'object') {
                warehouseLat = mainWarehouse.lat;
                warehouseLon = mainWarehouse.lon || mainWarehouse.lng;
            }
        }

        if (warehouseLat !== undefined && warehouseLon !== undefined) {
            const warehouseIcon = L.divIcon({
                className: 'warehouse-icon',
                html: '<i class="fas fa-warehouse"></i>',
                iconSize: [24, 24],
                iconAnchor: [12, 12]
            });

            const warehouseMarker = L.marker([warehouseLat, warehouseLon], {
                icon: warehouseIcon
            }).addTo(map);

            warehouseMarker.bindPopup('Warehouse');
            window.routeLayers.push(warehouseMarker);
        } else {
             console.warn("Could not determine warehouse coordinates for marker.");
        }
    } catch (e) {
        console.error("Error adding warehouse marker:", e);
    }

    // --- Add Original Preset Destination Markers ---
    if (solution.destinations && Array.isArray(solution.destinations)) {
        console.log(`Adding ${solution.destinations.length} original destination markers.`);
        solution.destinations.forEach(dest => {
            if (dest && dest.lat !== undefined && (dest.lon !== undefined || dest.lng !== undefined)) {
                // Check if this location is already marked as part of an active route (checkpoint or dynamic stop)
                let alreadyMarked = false;
                window.routeLayers.forEach(layer => {
                    if (layer instanceof L.Marker) {
                        const markerLatLng = layer.getLatLng();
                        if (markerLatLng.lat === dest.lat && markerLatLng.lng === (dest.lon || dest.lng)) {
                            alreadyMarked = true;
                        }
                    }
                });

                // Only add a distinct marker if it's not already part of an active route path/stop
                if (!alreadyMarked) {
                    const clusterId = dest.cluster_id || 'N/A';
                    const markerIcon = L.divIcon({
                        html: `<span class="original-destination-marker" title="Cluster ${clusterId}"></span>`,
                        className: 'original-destination-icon',
                        iconSize: [8, 8], // Make them small
                        iconAnchor: [4, 4]
                    });
                    const popupContent = `
                        <div class="original-destination-popup">
                            <h6>Original Location (Cluster ${clusterId})</h6>
                            <p>Coords: ${dest.lat.toFixed(5)}, ${(dest.lon || dest.lng).toFixed(5)}</p>
                        </div>`;

                    const marker = L.marker([dest.lat, dest.lon || dest.lng], { icon: markerIcon, zIndexOffset: -100 }) // Lower z-index
                        .addTo(map)
                        .bindPopup(popupContent);
                    window.routeLayers.push(marker); // Add to layers for clearing
                }
            }
        });
    }
    // --- End Original Destination Markers ---

    // Display routes
    if (solution.routes && Array.isArray(solution.routes)) {
        solution.routes.forEach((route, index) => {
            const color = colors[index % colors.length];
            let points = [];
            let pathSource = 'unknown';

            // --- Determine Path Points Based on Route Type ---
            if (isCheckpointRoute) {
                // For checkpoint routes, PRIORITIZE detailed geometry if available
                if (route.detailed_path_geometry && Array.isArray(route.detailed_path_geometry) && route.detailed_path_geometry.length > 1) {
                    points = route.detailed_path_geometry; // Use the detailed path from backend
                    pathSource = 'ors_detailed_checkpoint';
                    console.log(`Route ${index + 1}: Using detailed geometry for checkpoint route.`);
                } else {
                    // FALLBACK: If no detailed geometry, connect start, checkpoints, end with straight lines
                    pathSource = 'checkpoint_stops_filtered_fallback';
                    points = [];
                    console.log(`Route ${index + 1}: No detailed geometry found, falling back to straight lines between checkpoints.`);
                    if (route.path && Array.isArray(route.path)) {
                        route.path.forEach((point, index) => {
                            // Include: Start, Checkpoints, End
                            if (index === 0 || index === route.path.length - 1 || point.type === 'checkpoint') {
                                if (point && point.lat !== undefined && (point.lon !== undefined || point.lng !== undefined)) {
                                    const coords = [point.lat, point.lon || point.lng];
                                    // Avoid adding duplicate consecutive points
                                    if (points.length === 0 || points[points.length - 1][0] !== coords[0] || points[points.length - 1][1] !== coords[1]) {
                                        points.push(coords);
                                    }
                                }
                            }
                        });
                    }
                    // Fallback for < 2 points in filtered list
                    if (points.length < 2 && route.path && route.path.length >= 2) {
                         console.warn(`Route ${index + 1}: Fallback filtering resulted in < 2 points. Drawing direct start-to-end.`);
                         points = []; // Reset and just use start/end
                         const startPoint = route.path[0];
                         const endPoint = route.path[route.path.length - 1];
                         if (startPoint && startPoint.lat !== undefined && (startPoint.lon !== undefined || startPoint.lng !== undefined)) {
                             points.push([startPoint.lat, startPoint.lon || startPoint.lng]);
                         }
                         if (endPoint && endPoint.lat !== undefined && (endPoint.lon !== undefined || endPoint.lng !== undefined)) {
                             if (points.length === 0 || points[0][0] !== endPoint.lat || points[0][1] !== (endPoint.lon || endPoint.lng)) {
                                 points.push([endPoint.lat, endPoint.lon || endPoint.lng]);
                             }
                         }
                    }
                }
            } else { // Static routes (non-checkpoint)
                // Use detailed geometry if available, otherwise basic path
                if (route.detailed_path_geometry && Array.isArray(route.detailed_path_geometry) && route.detailed_path_geometry.length > 1) {
                    points = route.detailed_path_geometry;
                    pathSource = 'ors_detailed_static';
                } else if (route.path && Array.isArray(route.path)) {
                    points = route.path.map(stop => {
                        if (stop && stop.lat !== undefined && (stop.lon !== undefined || stop.lng !== undefined)) {
                            return [stop.lat, stop.lon || stop.lng];
                        }
                        return null;
                    }).filter(p => p !== null);
                    pathSource = 'basic_path_static';
                }
            }
            // --- End Path Point Determination ---

            console.log(`Route ${index + 1} Path Source: ${pathSource}, Points: ${points.length}`);

            // Draw polyline if enough points
            if (points.length > 1) {
                const pathOptions = {
                    color: color,
                    // Use consistent weight, or differentiate based on source if desired
                    weight: 4, // pathSource === 'ors_detailed_checkpoint' || pathSource === 'ors_detailed_static' ? 4 : 5,
                    opacity: 0.8
                };
                const polyline = L.polyline(points, pathOptions).addTo(map);
                window.routeLayers.push(polyline);

                // Add directional arrows (requires Leaflet.Polyline.Decorator)
                try {
                     L.polylineDecorator(polyline, {
                        patterns: [
                            {offset: 25, repeat: 50, symbol: L.Symbol.arrowHead({pixelSize: 10, pathOptions: {fillOpacity: 1, weight: 0, color: color}})}
                        ]
                    }).addTo(map);
                } catch(arrowError) {
                    console.warn("Could not add directional arrows. Is Leaflet.PolylineDecorator included?", arrowError);
                }
            } else {
                 console.warn(`Route ${index + 1}: Not enough points (${points?.length || 0}) to draw polyline.`);
            }

            // --- Marker Logic ---
            // Add markers for stops (Checkpoints or Destinations)
            const stopsToMark = isCheckpointRoute ? route.stops : (route.path || []).slice(1, -1);

            if (stopsToMark && Array.isArray(stopsToMark)) {
                stopsToMark.forEach((stop, stopIdx) => {
                    if (stop && stop.lat !== undefined && (stop.lon !== undefined || stop.lng !== undefined)) {
                        let markerIcon;
                        let popupContent;
                        const isDynamic = stop.is_dynamic === true; // Check the boolean flag from backend
                        const type = stop.type; // 'pickup', 'dropoff', 'checkpoint', etc.

                        // --- UPDATED LOGIC ---
                        if (isDynamic && (type === 'pickup' || type === 'dropoff')) {
                            // **Explicitly handle dynamic stops within checkpoint routes**
                            const markerType = type === 'pickup' ? 'P' : 'D';
                            const markerColor = type === 'pickup' ? 'darkorange' : 'purple';
                            markerIcon = Utils.createSimpleIcon(markerType, markerColor);
                            popupContent = `
                                <div class="dynamic-stop-popup">
                                    <h6>Dynamic ${type === 'pickup' ? 'Pickup' : 'Dropoff'} (Vehicle ${index + 1})</h6>
                                    <p><strong>Coordinates:</strong> ${stop.lat.toFixed(5)}, ${stop.lon.toFixed(5)}</p>
                                    <p><strong>Cluster:</strong> ${stop.cluster_id || 'N/A'}</p>
                                    ${stop.address ? `<p><small>${stop.address.street || ''}, ${stop.address.city || ''}</small></p>` : ''}
                                </div>`;

                        } else if (isCheckpointRoute) {
                            // Checkpoint markers (for non-dynamic stops in checkpoint routes)
                            markerIcon = L.divIcon({
                                className: 'checkpoint-icon-container',
                                html: `<div class="cp-marker" style="
                                      background-color: ${color};
                                      color: white;
                                      border-radius: 50%;
                                      width: 28px;
                                      height: 28px;
                                      display: flex;
                                      align-items: center;
                                      justify-content: center;
                                      font-weight: bold;
                                      border: 2px solid white;
                                      box-shadow: 0 1px 3px rgba(0,0,0,0.4);">
                                    ${stopIdx + 1}
                                  </div>`,
                                iconSize: [28, 28],
                                iconAnchor: [14, 14],
                                popupAnchor: [0, -14]
                            });
                            const clusters = stop.clusters_served || [];
                            popupContent = `
                                <div class="checkpoint-popup">
                                    <h6>Checkpoint ${stopIdx + 1} (Vehicle ${index + 1})</h6>
                                    <p><strong>Coordinates:</strong> ${stop.lat.toFixed(5)}, ${stop.lon.toFixed(5)}</p>
                                    <p><strong>Serves clusters:</strong></p>
                                    <div class="cluster-badges">
                                        ${clusters.map(id => `<span class="badge bg-info me-1">${id}</span>`).join('')}
                                    </div>
                                </div>`;

                        } else {
                            // Static route destination markers (original logic for non-checkpoint routes)
                            markerIcon = L.divIcon({
                                className: 'destination-icon',
                                html: `<div style="
                                      background-color: ${color};
                                      color: white;
                                      border-radius: 50%;
                                      width: 22px;
                                      height: 22px;
                                      display: flex;
                                      align-items: center;
                                      justify-content: center;
                                      font-size: 12px;
                                      font-weight: bold;
                                      border: 1px solid white;">
                                    ${stopIdx + 1}
                                  </div>`,
                                iconSize: [22, 22],
                                iconAnchor: [11, 11]
                            });
                            popupContent = `Destination ${stopIdx + 1} (Vehicle ${index + 1})`;
                        }
                        // --- END UPDATED LOGIC ---


                        const marker = L.marker([stop.lat, stop.lon || stop.lng], { icon: markerIcon })
                            .addTo(map)
                            .bindPopup(popupContent);

                        // Store reference for interaction
                        marker._stopIndex = stopIdx;
                        marker._routeIndex = index;
                        marker._isDynamic = isDynamic; // Store flag

                        window.routeLayers.push(marker);
                    }
                });
            }
        });
    }

    // Add markers for original destinations (only if not a checkpoint route, to avoid clutter)
    if (!isCheckpointRoute && solution.destinations && Array.isArray(solution.destinations)) {
         solution.destinations.forEach(dest => {
            if (dest && dest.lat !== undefined && dest.lon !== undefined) {
                const destIcon = L.divIcon({
                    className: 'original-destination-icon',
                    html: `<div style="
                              background-color: #9e9e9e;
                              width: 8px;
                              height: 8px;
                              border-radius: 50%;
                              border: 1px solid #ffffff;">
                          </div>`,
                    iconSize: [8, 8],
                    iconAnchor: [4, 4]
                });

                const marker = L.marker([dest.lat, dest.lon], { icon: destIcon })
                    .addTo(map)
                    .bindPopup(`Original Location<br>Cluster: ${dest.cluster_id || 'N/A'}`);

                window.routeLayers.push(marker);
            }
        });
    }

    // Fit map bounds to show all routes if appropriate points exist
    try {
        if (window.routeLayers && window.routeLayers.length > 0) {
            const group = new L.featureGroup(window.routeLayers.filter(layer =>
                layer instanceof L.Polyline || layer instanceof L.Marker
            ));

            if (group.getBounds().isValid()) {
                map.fitBounds(group.getBounds(), {
                    padding: [50, 50], // Add padding
                    maxZoom: 16 // Limit zoom level
                });
            }
        }
    } catch (e) {
        console.error("Error fitting bounds:", e);
    }
}

// Helper function to populate insertion points for a given vehicle index
function populateInsertionPoints(vehicleIndex, solution) {
    const insertionPointSelect = document.getElementById('insertion-point-select');
    if (!insertionPointSelect || !solution || !solution.routes || !solution.routes[vehicleIndex]) {
        if (insertionPointSelect) insertionPointSelect.innerHTML = '<option value="-1">N/A</option>';
        return;
    }

    const route = solution.routes[vehicleIndex];
    const isCheckpoint = route.stops && route.stops[0]?.type === 'checkpoint';
    const stops = isCheckpoint ? route.stops : (route.path || []).slice(1, -1); // Use path for static, exclude warehouse

    insertionPointSelect.innerHTML = ''; // Clear existing options

    // Option to insert right after the warehouse
    insertionPointSelect.innerHTML += `<option value="0">After Warehouse (Start)</option>`;

    // Options to insert after each stop
    stops.forEach((stop, index) => {
        let label = `Stop ${index + 1}`;
        if (isCheckpoint) {
            label = `Checkpoint ${index + 1} (${stop.lat.toFixed(3)}, ${stop.lon.toFixed(3)})`;
        } else {
            label = `Destination ${index + 1} (${stop.lat.toFixed(3)}, ${stop.lon || stop.lng.toFixed(3)})`;
        }
        // The value represents inserting *after* this stop's index (relative to the stops array)
        insertionPointSelect.innerHTML += `<option value="${index + 1}">After ${label}</option>`;
    });
}

// Updated: Function to set up UI for dynamic insertion based on the current solution
function setupDynamicInsertionUI(solution) {
    const controlsDiv = document.getElementById('dynamic-insertion-controls');
    if (!controlsDiv || !solution || !solution.routes || solution.routes.length === 0) {
        controlsDiv.innerHTML = '<p class="text-muted small">No routes available for dynamic insertion.</p>';
        return;
    }

    // Vehicle Selection Dropdown
    let vehicleSelectHtml = '';
    if (solution.routes.length > 1) {
        vehicleSelectHtml = `
            <div class="form-group mb-2">
                <label for="target-vehicle-select" class="form-label small">Target Vehicle:</label>
                <select id="target-vehicle-select" class="form-select form-select-sm">
        `;
        solution.routes.forEach((route, index) => {
            vehicleSelectHtml += `<option value="${index}">Vehicle ${index + 1}</option>`;
        });
        vehicleSelectHtml += `
                </select>
            </div>`;
    } else {
        vehicleSelectHtml = `<input type="hidden" id="target-vehicle-select" value="0">`;
    }

    // Insertion Point Selection Dropdown
    const insertionPointHtml = `
        <div class="form-group mb-2">
            <label for="insertion-point-select" class="form-label small">Insert After:</label>
            <select id="insertion-point-select" class="form-select form-select-sm">
                <!-- Options will be populated dynamically -->
                <option value="0">After Warehouse (Start)</option>
            </select>
        </div>`;


    controlsDiv.innerHTML = `
        ${vehicleSelectHtml}
        ${insertionPointHtml}
        <button id="insert-dynamic-btn" class="btn btn-warning btn-sm mt-2" ${dynamicLocationPairs.length === 0 ? 'disabled' : ''}>
            <i class="fas fa-calculator"></i> Insert & Recalculate Route
        </button>
        <p class="text-muted small mt-1">Adds the new pairs to the selected vehicle's route after the chosen point.</p>
    `;

    // Add event listener to the vehicle select dropdown (if it exists)
    const vehicleSelect = document.getElementById('target-vehicle-select');
    if (vehicleSelect && solution.routes.length > 1) {
        vehicleSelect.addEventListener('change', (event) => {
            const selectedVehicleIndex = parseInt(event.target.value);
            populateInsertionPoints(selectedVehicleIndex, solution);
        });
    }

    // Populate insertion points for the initially selected vehicle (index 0)
    populateInsertionPoints(0, solution);


    // Add event listener to the insert button
    const insertBtn = document.getElementById('insert-dynamic-btn');
    if (insertBtn) {
        insertBtn.addEventListener('click', handleDynamicInsertion);
    }
}

// Updated: Function to handle the dynamic insertion request
function handleDynamicInsertion() {
    const vehicleSelect = document.getElementById('target-vehicle-select');
    const insertionPointSelect = document.getElementById('insertion-point-select'); // Get insertion point dropdown

    // Check if elements exist
    if (!vehicleSelect || !insertionPointSelect) {
        alert("Error: UI elements for insertion control not found.");
        console.error("Missing vehicleSelect or insertionPointSelect elements.");
        return;
    }

    const targetVehicleIndex = parseInt(vehicleSelect.value);
    const insertionPointValue = insertionPointSelect.value; // Get the raw value first
    console.log("Raw insertion point value:", insertionPointValue); // Log raw value
    const insertionPointIndex = parseInt(insertionPointValue); // Get selected insertion index

    // Check if parsing resulted in NaN (e.g., if value is empty or not a number)
    if (isNaN(targetVehicleIndex)) {
         alert("Error: Invalid vehicle selected.");
         console.error("targetVehicleIndex is NaN. Value:", vehicleSelect.value);
         return;
    }
    if (isNaN(insertionPointIndex)) {
         alert("Error: Invalid insertion point selected. Please ensure an option is chosen.");
         console.error("insertionPointIndex is NaN. Value:", insertionPointValue);
         return;
    }
    console.log("Parsed insertion point index:", insertionPointIndex); // Log parsed value

    // Check if pairs exist
    if (!dynamicLocationPairs || dynamicLocationPairs.length === 0) {
        alert("Error: No dynamic location pairs have been added.");
        return;
    }

    // Check if current solution and config are available
    if (!currentVrpSolution || !currentTestConfig) {
        alert("Error: Missing current solution or test configuration context.");
        return;
    }

    // Show loading state
    const insertBtn = document.getElementById('insert-dynamic-btn');
    if (insertBtn) {
        insertBtn.disabled = true;
        insertBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Inserting...';
    }

    const url = '/vrp_testing/insert_dynamic';
    const requestData = {
        current_solution: currentVrpSolution,
        prepared_data_ref: {
             snapshot_id: currentTestConfig.snapshot_id,
             preset_id: currentTestConfig.preset_id,
             api_key: currentTestConfig.api_key // Pass API key if needed by prepare_test_data
        },
        new_location_pairs: dynamicLocationPairs,
        target_vehicle_index: targetVehicleIndex,
        insertion_point_index: insertionPointIndex, // Ensure this is correctly obtained and passed
        algorithm: currentTestConfig.algorithm || 'or_tools' // Default algorithm if not set
    };

    // Log the exact data being sent
    console.log('Sending dynamic insertion request data:', JSON.stringify(requestData, null, 2));

    fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestData)
    })
    .then(response => response.json())
    .then(data => {
        console.log('Dynamic insertion response:', data);
        if (data.status === 'success') {
            currentVrpSolution = data.updated_solution; // Update the global solution
            currentTestConfig.test_type = 'dynamic_updated'; // Update test type if needed
            // Redisplay results AND update insertion UI based on the NEW solution
            displayTestResults(data.updated_solution, 'dynamic');
            alert('Route updated successfully with dynamic locations.');
            // Clear dynamic pairs after successful insertion
            dynamicLocationPairs = [];
            const dynamicList = document.getElementById('dynamic-locations-list');
            if (dynamicList) dynamicList.innerHTML = '';
            // Button state will be reset by setupDynamicInsertionUI called within displayTestResults
        } else {
            alert(`Error inserting dynamic locations: ${data.message}`);
            // Restore previous view AND insertion UI if needed (displayTestResults handles this)
            displayTestResults(currentVrpSolution, 'dynamic');
        }
    })
    .catch(error => {
        console.error('Error during dynamic insertion fetch:', error);
        alert('Network error or server issue during dynamic insertion.');
         // Restore previous view AND insertion UI
        displayTestResults(currentVrpSolution, 'dynamic');
    })
    .finally(() => {
         // Button state is handled by displayTestResults calling setupDynamicInsertionUI again
         // Ensure button is re-enabled if it wasn't re-created (though it should be)
         const finalInsertBtn = document.getElementById('insert-dynamic-btn');
         if (finalInsertBtn) {
             finalInsertBtn.disabled = (dynamicLocationPairs.length === 0); // Disable if no pairs left
             finalInsertBtn.innerHTML = '<i class="fas fa-calculator"></i> Insert & Recalculate Route';
         }
    });
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