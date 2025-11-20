// Override Socket.IO client to use external Railway service
(function() {
    // Wait for frappe to be ready
    document.addEventListener('DOMContentLoaded', function() {
        if (typeof frappe !== 'undefined' && frappe.realtime) {
            // Override get_host method to use external Socket.IO service
            frappe.realtime.get_host = function() {
                // Definimos la URL directamente para evitar errores de tipos de datos
                const url = "https://socketio-production-ef94.up.railway.app";

                // (Opcional) Log para ver que funciona
                console.log("🔌 SocketIO Override activo conectando a:", url);

                return url;
            };

            console.log('✅ Socket.IO override configurado para servicio externo');
        }
    });
})();
