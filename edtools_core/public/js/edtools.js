// Edtools Text Replacement - Keep Frappe design, only change text

// Help dropdown: Documentation URL, hide 3 items, Soporte + CUC School non-clickable
var DOCS_EDTOOLS_URL = "https://docs.edtools.co/api-reference/introduction";
var HELP_LABELS_TO_HIDE = ["About", "Acerca de", "User Forum", "CUC University School", "Report an Issue", "Foro de usuarios", "Escuela CUC University", "Reportar un problema"];

function makeLinkNonClickable(el) {
    if (el.getAttribute("data-edtools-noclick") === "1") return;
    el.setAttribute("data-edtools-noclick", "1");
    el.setAttribute("href", "#");
    el.classList.add("disabled");
    el.setAttribute("tabindex", "-1");
    el.setAttribute("aria-disabled", "true");
    el.style.pointerEvents = "none";
    el.style.cursor = "default";
    el.addEventListener("click", function(e) {
        e.preventDefault();
        e.stopPropagation();
        return false;
    });
}

function customizeHelpDropdown() {
    var menu = document.getElementById("toolbar-help");
    if (!menu) return;

    var items = menu.querySelectorAll(".dropdown-item");
    items.forEach(function(el) {
        var text = (el.textContent || "").trim();

        // 1) Documentation: ensure link points to docs.edtools.co
        if (el.tagName === "A" && el.getAttribute("href")) {
            var href = el.getAttribute("href") || "";
            if (href.indexOf("docs.erpnext.com") !== -1 || (href.indexOf("erpnext") !== -1 && text.toLowerCase().indexOf("documentation") !== -1)) {
                el.setAttribute("href", DOCS_EDTOOLS_URL);
            }
            // 2) Soporte de CUC University: siempre no clickeable (sin importar href actual)
            if (text.indexOf("Soporte") !== -1 && text.indexOf("CUC") !== -1) {
                makeLinkNonClickable(el);
            }
            // 3) CUC University School: no clickeable por si no se ocultó
            if (text.indexOf("CUC University School") !== -1) {
                makeLinkNonClickable(el);
                el.style.display = "none";
            }
        }

        // 4) Hide About, User Forum, CUC University School, Report an Issue (exact or partial)
        var t = text.trim();
        var hide = (t === "About" || t === "Acerca de") ||
            text.indexOf("User Forum") !== -1 || text.indexOf("CUC University School") !== -1 || text.indexOf("Report an Issue") !== -1 ||
            text.indexOf("Foro de usuarios") !== -1 || text.indexOf("Reportar un problema") !== -1;
        if (hide) {
            el.style.display = "none";
        }
    });
}

// Re-aplicar al abrir el dropdown Ayuda (por si el menú se renderiza al hacer clic)
function bindHelpDropdownCustomize() {
    var btn = document.querySelector(".dropdown-help .dropdown-toggle, [aria-controls='toolbar-help']");
    var menu = document.getElementById("toolbar-help");
    if (!btn || !menu) return;
    btn.addEventListener("click", function() {
        setTimeout(customizeHelpDropdown, 100);
    });
    // Por si el dropdown se abre por hover/focus
    menu.addEventListener("mouseenter", function() { customizeHelpDropdown(); });
}

// Wait for DOM to be ready
(function() {
    // Replace text throughout the application
    replaceTextInPage();

    // Update page titles
    updatePageTitles();

    // Help dropdown (navbar may be ready after a short delay)
    function runHelpCustomize() {
        customizeHelpDropdown();
        bindHelpDropdownCustomize();
    }
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function() {
            setTimeout(runHelpCustomize, 500);
        });
    } else {
        setTimeout(runHelpCustomize, 500);
    }
})();

function replaceTextInPage() {
    // Text replacements - only changes wording, not design
    const replacements = {
        'Frappe': 'CUC University',
        'ERPNext': 'CUC University',
        'Edtools': 'CUC University',
        'with ERPNext': 'with CUC University',
        'Powered by Frappe': 'Powered by CUC University',
        'Powered by ERPNext': 'Powered by CUC University',
        "Let's begin your journey with ERPNext": "Comencemos tu experiencia con CUC University",
        "Let's begin your journey with Edtools": "Comencemos tu experiencia con CUC University",
        'Configuración de ERPNext': 'Configuración de CUC University',
        'ERPNext Settings': 'Configuración de CUC University'
    };

    // Function to replace text in a text node
    function replaceInTextNode(node) {
        if (node.nodeType === Node.TEXT_NODE) {
            let text = node.nodeValue;
            for (let [oldText, newText] of Object.entries(replacements)) {
                text = text.replace(new RegExp(oldText, 'g'), newText);
            }
            node.nodeValue = text;
        } else if (node.nodeType === Node.ELEMENT_NODE) {
            // Skip script and style tags
            if (node.tagName !== 'SCRIPT' && node.tagName !== 'STYLE') {
                for (let child of node.childNodes) {
                    replaceInTextNode(child);
                }
            }
        }
    }

    // Replace in current page
    replaceInTextNode(document.body);

    // Watch for new content (like modals, dialogs)
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            mutation.addedNodes.forEach(function(node) {
                if (node.nodeType === Node.ELEMENT_NODE) {
                    replaceInTextNode(node);
                }
            });
        });
    });

    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
}

function updatePageTitles() {
    // Update browser tab title
    if (document.title.includes('Frappe')) {
        document.title = document.title.replace('Frappe', 'CUC University');
    }
    if (document.title.includes('ERPNext')) {
        document.title = document.title.replace('ERPNext', 'CUC University');
    }
    if (document.title.includes('Edtools')) {
        document.title = document.title.replace('Edtools', 'CUC University');
    }

    // Update frappe.boot if available
    if (window.frappe && frappe.boot) {
        frappe.boot.app_name = "CUC University";
        if (frappe.boot.website_settings) {
            frappe.boot.website_settings.app_name = "CUC University";
        }
    }
}

// Reintento en 502 para search_link (evita fallo al crear Student Group en Railway)
function initSearchLinkRetry() {
    if (!frappe.call) return;
    var _call = frappe.call.bind(frappe);
    frappe.call = function(opts) {
        // IMPORTANTE: frappe.call puede recibir (method, args, callback) o (opts).
        // Hay que pasar TODOS los argumentos a _call con apply, no solo opts.
        var callArgs = Array.prototype.slice.call(arguments);
        var cmd = '';
        if (typeof opts === 'string') {
            cmd = opts;
        } else if (opts && (opts.args || opts.method)) {
            cmd = (opts.args && opts.args.cmd) || opts.method || '';
        }
        var isSearchLink = String(cmd).indexOf('search_link') !== -1;
        if (!isSearchLink) return _call.apply(frappe, callArgs);
        function attempt(retriesLeft) {
            return _call.apply(frappe, callArgs).catch(function(xhr) {
                if (xhr && xhr.status === 502 && retriesLeft > 0) {
                    return new Promise(function(r) { setTimeout(r, 1500); }).then(function() {
                        return attempt(retriesLeft - 1);
                    });
                }
                return Promise.reject(xhr);
            });
        }
        return attempt(1);
    };
}

// Also run on app_ready event (for Frappe Desk)
if (typeof $ !== 'undefined') {
    $(document).on('app_ready', function() {
        updatePageTitles();
        replaceTextInPage();
        customizeHelpDropdown();
        bindHelpDropdownCustomize();
        initStudentLinkFormatter();
        initSearchLinkRetry();
    });
}

// Run again when Frappe is ready (for web pages)
if (typeof frappe !== 'undefined' && frappe.ready) {
    frappe.ready(function() {
        updatePageTitles();
        replaceTextInPage();
        customizeHelpDropdown();
        bindHelpDropdownCustomize();
        initStudentLinkFormatter();
        initSearchLinkRetry();
    });
}

// Link formatter para Student: usar student_name cuando esté disponible (evita mostrar EDU-STU-xxx en tablas)
// Fix: filas añadidas con "Obtener Estudiantes" no tienen título en _link_titles; student_name sí está en la fila
function initStudentLinkFormatter() {
    if (frappe.form && frappe.form.link_formatters) {
        frappe.form.link_formatters['Student'] = function(value, doc, docfield) {
            if (doc && doc.student_name) {
                return doc.student_name;
            }
            return value;
        };
    }
}
