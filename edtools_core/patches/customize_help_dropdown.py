# Copyright (c) 2026, EdTools and contributors
# For license information, please see license.txt

"""Customize Help (Ayuda) dropdown: Documentation link, hide 3 items, Soporte non-clickable."""

import frappe

DOCUMENTATION_URL = "https://docs.edtools.co/api-reference/introduction"

# Item labels to hide (English and Spanish as stored in DB)
LABELS_TO_HIDE = [
    "About",
    "Acerca de",
    "User Forum",
    "CUC University School",
    "IDITEK School",
    "Colegio Anglo Hispano School",
    "Report an Issue",
    "Foro de usuarios",
    "Escuela CUC University",
    "Escuela IDITEK",
    "Escuela Colegio Anglo Hispano",
    "Reportar un problema",
]

# Item label (or partial) for Soporte - we set route to "#" so JS can make it non-clickable
SOPORTE_LABEL_SUBSTRING = "Soporte"


def execute():
    frappe.flags.in_patch = True
    try:
        doc = frappe.get_single("Navbar Settings")
        changed = False

        for item in doc.help_dropdown:
            # 1) Documentation: point to docs.edtools.co (by route or by label)
            if item.item_type == "Route" and item.route:
                label = (item.item_label or "").strip()
                if "docs.erpnext.com" in item.route or label in ("Documentation", "Documentación"):
                    item.route = DOCUMENTATION_URL
                    changed = True

            # 2) Hide User Forum, School, Report an Issue
            if (item.item_label or "").strip() in LABELS_TO_HIDE:
                item.hidden = 1
                changed = True

            # 3) Soporte institucional: keep visible but use "#" so JS can make it non-clickable
            if item.item_label and SOPORTE_LABEL_SUBSTRING in item.item_label and item.route:
                item.route = "#"
                changed = True

        if changed:
            doc.save(ignore_permissions=True)
            frappe.db.commit()
            frappe.logger().info("Navbar Settings: help dropdown updated (Documentation, hidden items, Soporte)")
    finally:
        frappe.flags.in_patch = False
