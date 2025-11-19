// Edtools Text Replacement - Keep Frappe design, only change text

// Wait for DOM to be ready
(function() {
    // Replace text throughout the application
    replaceTextInPage();

    // Update page titles
    updatePageTitles();
})();

function replaceTextInPage() {
    // Text replacements - only changes wording, not design
    const replacements = {
        'Frappe': 'Edtools',
        'ERPNext': 'Edtools',
        'with ERPNext': 'with Edtools',
        'Powered by Frappe': 'Powered by Edtools',
        'Powered by ERPNext': 'Powered by Edtools',
        "Let's begin your journey with ERPNext": "Comencemos tu experiencia con Edtools",
        "Let's begin your journey with Edtools": "Comencemos tu experiencia con Edtools",
        'Configuración de ERPNext': 'Configuración de Edtools',
        'ERPNext Settings': 'Configuración de Edtools'
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
        document.title = document.title.replace('Frappe', 'Edtools');
    }
    if (document.title.includes('ERPNext')) {
        document.title = document.title.replace('ERPNext', 'Edtools');
    }

    // Update frappe.boot if available
    if (window.frappe && frappe.boot) {
        frappe.boot.app_name = "Edtools";
        if (frappe.boot.website_settings) {
            frappe.boot.website_settings.app_name = "Edtools";
        }
    }
}

// Also run on app_ready event (for Frappe Desk)
if (typeof $ !== 'undefined') {
    $(document).on('app_ready', function() {
        updatePageTitles();
        replaceTextInPage();
    });
}

// Run again when Frappe is ready (for web pages)
if (typeof frappe !== 'undefined' && frappe.ready) {
    frappe.ready(function() {
        updatePageTitles();
        replaceTextInPage();
    });
}
