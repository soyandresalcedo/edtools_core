# Copyright (c) 2026, Edtools and contributors
# Modifica el menú Ayuda en boot para que Documentation, CUC School y Soporte no redirijan.

DOCUMENTATION_URL = "https://docs.edtools.co/api-reference/introduction"

LABELS_TO_HIDE = (
    "User Forum",
    "CUC University School",
    "Report an Issue",
    "Foro de usuarios",
    "Escuela CUC University",
    "Reportar un problema",
)


def filter_navbar_settings_in_boot(bootinfo):
    """Filtra y corrige help_dropdown en boot: Documentation URL, ocultar 3 ítems, Soporte no clickeable."""
    ns = bootinfo.get("navbar_settings")
    if not ns or not getattr(ns, "help_dropdown", None):
        return

    for item in ns.help_dropdown:
        label = (getattr(item, "item_label", None) or "").strip()
        route = (getattr(item, "route", None) or "") or ""
        item_type = getattr(item, "item_type", None)

        # Ocultar User Forum, CUC University School, Report an Issue
        if label in LABELS_TO_HIDE:
            item.hidden = 1
            continue

        # Documentation -> docs.edtools.co
        if item_type == "Route" and route:
            if "docs.erpnext.com" in route or label in ("Documentation", "Documentación"):
                item.route = DOCUMENTATION_URL
                continue
            # Soporte de CUC University -> no clickeable
            if "Soporte" in label and "CUC" in label:
                item.route = "#"
