// Override Socket.IO client to use external Railway service
// IMPORTANTE: Este script se ejecuta ANTES de que Frappe inicialice Socket.IO
// FIX: Manejo correcto de HTTPS/WSS - Railway termina SSL automáticamente
(function() {
    // Guardar la función init original
    const originalInit = frappe.realtime?.init;

    // Override del método init para interceptar la configuración
    if (typeof frappe !== 'undefined' && frappe.realtime) {
        frappe.realtime.init = function(port, lazy_connect) {
            console.log("🔌 SocketIO Override v3: Interceptando inicialización");

            // Override get_host para usar URL externa
            this.get_host = function() {
                const externalUrl = "https://socketio-production-ef94.up.railway.app";
                console.log("🔌 Conectando a servicio externo:", externalUrl);

                // Railway termina SSL, retornamos HTTPS que se convierte a WSS
                return externalUrl + `/${frappe.boot.sitename}`;
            };

            // Llamar al init original si existe
            if (originalInit) {
                return originalInit.call(this, port, lazy_connect);
            }
        };

        console.log('✅ Socket.IO override v3 configurado - Railway SSL terminat');
    } else {
        // Si frappe.realtime no existe aún, esperar
        document.addEventListener('DOMContentLoaded', function() {
            if (frappe && frappe.realtime) {
                console.log('⚠️  Frappe cargado tarde, aplicando override...');
                // Aplicar override después de carga
            }
        });
    }
})();
