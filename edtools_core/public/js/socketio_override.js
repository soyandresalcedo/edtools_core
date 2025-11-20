// Override Socket.IO client to use external Railway service
(function() {
    // Wait for frappe to be ready
    document.addEventListener('DOMContentLoaded', function() {
        if (typeof frappe !== 'undefined' && frappe.realtime) {
            // Override get_host method to use external Socket.IO service
            frappe.realtime.get_host = function() {
                // TODO: Replace with actual Railway Socket.IO service URL
                // Format: https://socketio-production-XXXX.up.railway.app
                const socketio_url = "RAILWAY_SOCKETIO_URL_PLACEHOLDER";

                console.log("🔌 Conectando Socket.IO a:", socketio_url);
                return socketio_url;
            };

            console.log('✅ Socket.IO override configurado para servicio externo');
        }
    });
})();
