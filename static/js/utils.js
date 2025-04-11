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
    
    // Public API
    return {
        showNotification: showNotification,
        debugLog: debugLog,
        checkApiEndpoints: checkApiEndpoints,
        testCheckpointGeneration: testCheckpointGeneration
    };
})();