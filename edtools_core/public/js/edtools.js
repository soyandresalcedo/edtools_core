// Edtools Custom Branding JavaScript

frappe.ready(function() {
    // Replace "Frappe" and "ERPNext" text throughout the UI
    replaceTextInPage();

    // Override app title
    if (frappe.boot) {
        frappe.boot.app_name = "Edtools";
    }
});

function replaceTextInPage() {
    // Replace text in common elements
    const replacements = {
        'Frappe': 'Edtools',
        'ERPNext': 'Edtools',
        'with ERPNext': 'with Edtools',
        'Powered by Frappe': 'Powered by Edtools',
        'Powered by ERPNext': 'Powered by Edtools'
    };

    // Function to replace text in a node
    function replaceInNode(node) {
        if (node.nodeType === Node.TEXT_NODE) {
            let text = node.nodeValue;
            for (let [oldText, newText] of Object.entries(replacements)) {
                text = text.replace(new RegExp(oldText, 'g'), newText);
            }
            node.nodeValue = text;
        } else if (node.nodeType === Node.ELEMENT_NODE) {
            for (let child of node.childNodes) {
                replaceInNode(child);
            }
        }
    }

    // Replace in body
    replaceInNode(document.body);

    // Watch for dynamic content changes
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            mutation.addedNodes.forEach(function(node) {
                if (node.nodeType === Node.ELEMENT_NODE) {
                    replaceInNode(node);
                }
            });
        });
    });

    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
}

// Custom boot session modifications
$(document).on('app_ready', function() {
    // Override default branding
    if (window.frappe && frappe.boot) {
        frappe.boot.app_name = "Edtools";
        frappe.boot.website_settings = frappe.boot.website_settings || {};
        frappe.boot.website_settings.app_name = "Edtools";
    }

    // Update page title
    if (document.title.includes('Frappe')) {
        document.title = document.title.replace('Frappe', 'Edtools');
    }
    if (document.title.includes('ERPNext')) {
        document.title = document.title.replace('ERPNext', 'Edtools');
    }
});
