// Override Socket.IO client to use external Railway service
// IMPORTANTE: Este script se ejecuta ANTES de que Frappe inicialice Socket.IO
// DEBUG: Force rebuild v2 - 2024-11-20
(function() {
    // Ejecutar inmediatamente, no esperar a DOMContentLoaded
    function applyOverride() {
        if (typeof frappe !== 'undefined' && frappe.realtime) {
            // Override get_host method to use external Socket.IO service
            frappe.realtime.get_host = function() {
                // FIX: Evitar usar frappe.boot.socketio_port.startsWith() - causa error de tipo
                // Retornamos URL directa sin depender de socketio_port
                const url = "https://socketio-production-ef94.up.railway.app";

                console.log("🔌 SocketIO Override v2 conectando a:", url);

                return url;
            };

            console.log('✅ Socket.IO override configurado para servicio externo');
            return true;
        }
        return false;
    }

    // Intentar aplicar inmediatamente
    if (!applyOverride()) {
        // Si frappe no está listo, esperar a que se cargue
        document.addEventListener('DOMContentLoaded', applyOverride);
    }
})();
