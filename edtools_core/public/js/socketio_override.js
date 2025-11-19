// Override Socket.IO client to use external service
(function() {
    // Wait for frappe to be ready
    document.addEventListener('DOMContentLoaded', function() {
        if (typeof frappe !== 'undefined' && frappe.realtime) {
            // Override get_host method to use external Socket.IO URL
            const original_get_host = frappe.realtime.get_host.bind(frappe.realtime);

            frappe.realtime.get_host = function(port = 9000) {
                // If socketio_port is a full URL, use it directly
                if (frappe.boot && frappe.boot.socketio_port &&
                    (frappe.boot.socketio_port.startsWith('http://') ||
                     frappe.boot.socketio_port.startsWith('https://'))) {
                    console.log('Using external Socket.IO service:', frappe.boot.socketio_port);
                    return frappe.boot.socketio_port + `/${frappe.boot.sitename}`;
                }
                // Otherwise use original method
                return original_get_host(port);
            };

            console.log('Socket.IO client configured for external service');
        }
    });
})();
