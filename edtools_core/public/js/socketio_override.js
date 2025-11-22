// Override Socket.IO client to use external Railway service
// IMPORTANTE: Este script se ejecuta ANTES de que Frappe inicialice Socket.IO
// FIX: Manejo correcto de HTTPS/WSS - Railway termina SSL automáticamente
(function() {
    // Guardar la función init original
    const originalInit = frappe.realtime?.init;

    // Override del método init para interceptar la configuración
    if (typeof frappe !== 'undefined' && frappe.realtime) {
        frappe.realtime.init = function(port, lazy_connect) {
            console.log("🔌 SocketIO Override v4: Interceptando inicialización");
            console.log("🔌 Sitename:", frappe.boot?.sitename);

            // Override get_host para usar URL externa
            this.get_host = function() {
                const externalUrl = "https://socketio-production-ef94.up.railway.app";

                // FIX: Usar window.location.hostname en lugar de frappe.boot.sitename
                // porque frappe.boot.sitename puede tener valores de desarrollo
                const sitename = window.location.hostname;
                const fullUrl = externalUrl + `/${sitename}`;

                console.log("🔌 Sitename (from hostname):", sitename);
                console.log("🔌 URL completa:", fullUrl);

                // Railway termina SSL, retornamos HTTPS que se convierte a WSS
                return fullUrl;
            };

            // FIX: Override get_socket_options para añadir extraHeaders
            const originalGetSocketOptions = this.get_socket_options;
            this.get_socket_options = function() {
                const options = originalGetSocketOptions ? originalGetSocketOptions.call(this) : {};

                // Añadir header personalizado con sitename para autenticación
                // Usar siempre window.location.hostname para consistencia
                options.extraHeaders = options.extraHeaders || {};
                options.extraHeaders['x-frappe-site-name'] = window.location.hostname;

                console.log("🔌 Socket options:", options);
                return options;
            };

            // Llamar al init original si existe
            if (originalInit) {
                return originalInit.call(this, port, lazy_connect);
            }
        };

        console.log('✅ Socket.IO override v4 configurado - Railway SSL + headers');
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
