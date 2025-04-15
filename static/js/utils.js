/**
 * Shared utilities for the application
 */
const Utils = (function() {
    // Flag to enable/disable debug mode
    const DEBUG_MODE = true;
    
    /**
     * Show a notification to the user
     */
    function showNotification(message, type = 'info') {
        // Create notification container if it doesn't exist
        let container = document.getElementById('notification-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'notification-container';
            container.style.position = 'fixed';
            container.style.top = '20px';
            container.style.right = '20px';
            container.style.zIndex = '9999';
            document.body.appendChild(container);
        }
        
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `alert alert-${type} alert-dismissible fade show`;
        notification.innerHTML = `
            ${message}
            <button type="button" class="close" data-dismiss="alert" aria-label="Close">
                <span aria-hidden="true">&times;</span>
            </button>
        `;
        
        // Add to container
        container.appendChild(notification);
        
        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => notification.remove(), 300);
        }, 5000);
        
        // Log to console in debug mode
        if (DEBUG_MODE) {
            console.log(`[${type.toUpperCase()}] ${message}`);
        }
    }
    
    /**
     * Hide notification
     */
    function hideNotification() {
        const notification = document.getElementById('notification');
        if (notification) {
            notification.classList.add('hidden');
        }
    }
    
    /**
     * Log debug messages
     */
    function debugLog(message) {
        // Always log to console
        console.log(`CHECKPOINT DEBUG: ${message}`);
        
        // If debug panel exists, add message there
        const panel = document.getElementById('checkpoint-debug-panel');
        if (panel) {
            const msgElement = document.createElement('div');
            msgElement.textContent = `${new Date().toLocaleTimeString()} - ${message}`;
            panel.appendChild(msgElement);
            panel.scrollTop = panel.scrollHeight;
        }
    }

    /**
     * Check API endpoints
     */
    function checkApiEndpoints() {
        const endpoints = [
            '/presets/get_presets',
            '/clustering/get_clusters',
            '/checkpoint/cluster/1/checkpoints' 
        ];
        
        Utils.debugLog("Testing API endpoints...");
        
        endpoints.forEach(url => {
            fetch(url)
                .then(response => {
                    Utils.debugLog(`Endpoint ${url}: ${response.status} ${response.ok ? 'OK' : 'ERROR'}`);
                    return response.text();
                })
                .then(text => {
                    let preview = text.substring(0, 50).replace(/\n/g, ' ');
                    Utils.debugLog(`Response preview: ${preview}...`);
                })
                .catch(error => {
                    Utils.debugLog(`Endpoint ${url} failed: ${error.message}`);
                });
        });
    }

    /**
     * Test checkpoint generation API
     */
    function testCheckpointGeneration(clusterId) {
        Utils.debugLog(`Testing checkpoint generation API for cluster ${clusterId}`);
        
        // Update to use the correct endpoint from checkpoints.py
        fetch(`/checkpoint/cluster/${clusterId}/generate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => {
            Utils.debugLog(`Test response status: ${response.status}`);
            return response.text();
        })
        .then(text => {
            Utils.debugLog(`Raw response: ${text.substring(0, 200)}...`);
            try {
                const data = JSON.parse(text);
                Utils.debugLog(`Parsed response: ${JSON.stringify(data, null, 2).substring(0, 200)}...`);
            } catch (e) {
                Utils.debugLog(`Parse error: ${e.message}`);
            }
        })
        .catch(error => {
            Utils.debugLog(`Test request failed: ${error.message}`);
        });
    }
    
    /**
     * Create and initialize a Leaflet map
     * @param {string} elementId - ID of the HTML element for the map
     * @param {Array} initialCoords - [lat, lng] coordinates to center the map
     * @param {number} zoom - Initial zoom level
     * @param {Object} options - Additional map options
     * @returns {Object} Initialized Leaflet map
     */
    function createMap(elementId, initialCoords = [3.1390, 101.6869], zoom = 13, options = {}) {
        // Check if element exists
        const mapElement = document.getElementById(elementId);
        if (!mapElement) {
            console.error(`Map element '${elementId}' not found!`);
            return null;
        }
        
        // Check if map is already initialized to prevent double init
        if (mapElement._leaflet_id) {
            console.log(`Map '${elementId}' already initialized, returning existing instance`);
            return L.map._maps[mapElement._leaflet_id];
        }
        
        // Create new map with options
        console.log(`Initializing map '${elementId}'`);
        const mapOptions = Object.assign({}, options);
        const map = L.map(elementId, mapOptions).setView(initialCoords, zoom);
        
        // Add OpenStreetMap tiles
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        }).addTo(map);
        
        // Store globally if requested (critical for clustering functionality)
        if (options.globalName) {
            window[options.globalName] = map;
            console.log(`Map stored globally as window.${options.globalName}`);
        }
        
        return map;
    }
    
    /**
     * Clear all layers from a map except the base tile layer
     * @param {Object} map - The Leaflet map to clear
     */
    function clearMapLayers(map) {
        if (!map) return;
        
        map.eachLayer(function(layer) {
            if (!(layer instanceof L.TileLayer)) {
                map.removeLayer(layer);
            }
        });
    }
    
    /**
     * Create a marker icon
     * @param {string} type - Type of marker ('warehouse', 'destination', 'checkpoint')
     * @param {Object} options - Customization options
     * @returns {Object} Leaflet divIcon
     */
    function createMarkerIcon(type, options = {}) {
        const defaults = {
            number: '',
            color: '',
            size: type === 'warehouse' ? 24 : 22,
            className: `${type}-marker`
        };
        
        const config = Object.assign({}, defaults, options);
        
        let html = '';
        if (type === 'warehouse') {
            html = '<div class="warehouse-icon"></div>';
        } else if (type === 'checkpoint') {
            html = `<div class="checkpoint-icon" style="background-color: ${config.color || '#33cc33'};">
                   <div class="checkpoint-number">${config.number}</div>
                   </div>`;
        } else {
            html = `<div class="destination-icon" ${config.color ? `style="background-color: ${config.color};"` : ''}>${config.number}</div>`;
        }
        
        return L.divIcon({
            className: config.className,
            html: html,
            iconSize: [config.size, config.size],
            iconAnchor: [config.size/2, config.size/2]
        });
    }
    
    /**
     * Show loading indicator
     * @param {string} message - Loading message to display
     * @param {boolean} withProgress - Whether to show a progress bar
     */
    function showLoadingIndicator(message = 'Loading...', withProgress = false) {
        // Create overlay if it doesn't exist
        let loadingOverlay = document.getElementById('loading-overlay');
        if (!loadingOverlay) {
            loadingOverlay = document.createElement('div');
            loadingOverlay.id = 'loading-overlay';
            loadingOverlay.style.position = 'fixed';
            loadingOverlay.style.top = '0';
            loadingOverlay.style.left = '0';
            loadingOverlay.style.width = '100%';
            loadingOverlay.style.height = '100%';
            loadingOverlay.style.backgroundColor = 'rgba(0,0,0,0.5)';
            loadingOverlay.style.display = 'flex';
            loadingOverlay.style.justifyContent = 'center';
            loadingOverlay.style.alignItems = 'center';
            loadingOverlay.style.zIndex = '9999';
            
            const container = document.createElement('div');
            container.className = 'loading-container';
            container.style.backgroundColor = 'white';
            container.style.padding = '20px';
            container.style.borderRadius = '5px';
            container.style.textAlign = 'center';
            
            container.innerHTML = `
                <div class="loading-spinner" style="margin-bottom:10px;"></div>
                <h3 id="loading-message">${message}</h3>
                ${withProgress ? '<div class="progress-container" style="width:100%;background:#eee;height:10px;margin-top:10px;"><div id="loading-progress-bar" style="width:0%;background:#007bff;height:10px;"></div></div>' : ''}
            `;
            
            loadingOverlay.appendChild(container);
            document.body.appendChild(loadingOverlay);
        } else {
            document.getElementById('loading-message').textContent = message;
            if (withProgress) {
                document.getElementById('loading-progress-bar').style.width = '0%';
            }
            loadingOverlay.style.display = 'flex';
        }
        
        return loadingOverlay;
    }
    
    /**
     * Update loading progress
     * @param {number} percent - Progress percentage (0-100)
     * @param {string} message - Optional new message
     */
    function updateLoadingProgress(percent, message = null) {
        const progressBar = document.getElementById('loading-progress-bar');
        if (progressBar) {
            progressBar.style.width = `${percent}%`;
        }
        
        if (message) {
            const messageElement = document.getElementById('loading-message');
            if (messageElement) {
                messageElement.textContent = message;
            }
        }
    }
    
    /**
     * Hide loading indicator
     */
    function hideLoadingIndicator() {
        const loadingOverlay = document.getElementById('loading-overlay');
        if (loadingOverlay) {
            // Complete the progress bar animation first
            const progressBar = document.getElementById('loading-progress-bar');
            if (progressBar) {
                progressBar.style.width = '100%';
            }
            
            // Hide after a short delay to show completion
            setTimeout(() => {
                loadingOverlay.style.display = 'none';
            }, 500);
        }
    }
    
    // Public API
    return {
        showNotification: showNotification,
        hideNotification: hideNotification,
        debugLog: debugLog,
        checkApiEndpoints: checkApiEndpoints,
        testCheckpointGeneration: testCheckpointGeneration,
        createMap: createMap,
        clearMapLayers: clearMapLayers,
        createMarkerIcon: createMarkerIcon,
        showLoadingIndicator: showLoadingIndicator,
        updateLoadingProgress: updateLoadingProgress,
        hideLoadingIndicator: hideLoadingIndicator
    };
})();