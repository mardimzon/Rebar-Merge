// static/js/welcome.js

document.addEventListener('DOMContentLoaded', function() {
    // Help toggle functionality
    const helpToggle = document.getElementById('help-toggle');
    const helpContent = document.getElementById('help-content');
    const connectionBadgeContainer = document.getElementById('connection-badge-container');
    
    if (helpToggle && helpContent) {
        helpToggle.addEventListener('click', function(e) {
            e.preventDefault();
            
            // Toggle the help content visibility
            if (helpContent.style.display === 'none' || helpContent.style.display === '') {
                helpContent.style.display = 'block';
                helpToggle.innerHTML = '<i class="fas fa-times-circle"></i> Hide help';
            } else {
                helpContent.style.display = 'none';
                helpToggle.innerHTML = '<i class="fas fa-question-circle"></i> Need help connecting?';
            }
        });
    }
    
    // Pre-check connection status with improved error handling
    checkConnectionStatus();
    
    function checkConnectionStatus() {
        // Show checking status first
        if (connectionBadgeContainer) {
            connectionBadgeContainer.innerHTML = `
                <div class="connection-badge checking">
                    <i class="fas fa-sync fa-spin"></i> Checking connection...
                </div>
            `;
        }
        
        // Try to fetch connection status to see if the server is running
        fetch('/api/connection_status')
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                // If we can connect to the server, check if it's connected to the Raspberry Pi
                if (data.connected) {
                    // Add a connected badge to the UI
                    if (connectionBadgeContainer) {
                        connectionBadgeContainer.innerHTML = `
                            <div class="connection-badge connected">
                                <i class="fas fa-check-circle"></i> Raspberry Pi Connected
                            </div>
                        `;
                    }
                } else {
                    // Add a warning badge
                    if (connectionBadgeContainer) {
                        connectionBadgeContainer.innerHTML = `
                            <div class="connection-badge warning">
                                <i class="fas fa-exclamation-circle"></i> Raspberry Pi Not Detected
                            </div>
                        `;
                    }
                }
            })
            .catch(error => {
                console.log('Error checking connection status:', error);
                // Show error status
                if (connectionBadgeContainer) {
                    connectionBadgeContainer.innerHTML = `
                        <div class="connection-badge error">
                            <i class="fas fa-times-circle"></i> Connection Error
                        </div>
                    `;
                }
            });
    }
    
    // Add connection badge styles dynamically
    addConnectionBadgeStyles();
    
    function addConnectionBadgeStyles() {
        const style = document.createElement('style');
        style.textContent = `
            .connection-badge {
                display: inline-block;
                padding: 8px 15px;
                border-radius: 20px;
                margin-bottom: 20px;
                font-size: 0.9rem;
                font-weight: 500;
                transition: all 0.3s ease;
            }
            
            .connection-badge.connected {
                background-color: #d4edda;
                color: #155724;
                border: 1px solid #c3e6cb;
            }
            
            .connection-badge.warning {
                background-color: #fff3cd;
                color: #856404;
                border: 1px solid #ffeeba;
            }
            
            .connection-badge.error {
                background-color: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
            }
            
            .connection-badge.checking {
                background-color: #e2e3e5;
                color: #383d41;
                border: 1px solid #d6d8db;
            }
            
            .connection-badge i {
                margin-right: 5px;
            }
        `;
        document.head.appendChild(style);
    }
});