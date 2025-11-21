// Override Socket.IO client to use external Railway service
// IMPORTANTE: Este script se ejecuta ANTES de que Frappe inicialice Socket.IO
(function() {
    // Ejecutar inmediatamente, no esperar a DOMContentLoaded
    function applyOverride() {
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
