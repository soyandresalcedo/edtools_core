# Copyright (c) 2026, Edtools and contributors
# Modifica el menú Ayuda en boot: Documentation link, ocultar School/Forum/Report, Soporte no clickeable.

DOCUMENTATION_URL = "https://docs.edtools.co/api-reference/introduction"

# Ocultar ítems que apunten a estas URLs (no dependemos del texto del botón)
URLS_TO_HIDE = (
    "frappe.io/school",
    "discuss.frappe",
    "report",  # Report an Issue
)

# URLs que convertimos a "#" para que no redirijan (Soporte)
URLS_TO_DISABLE = (
    "support.frappe.io",
    "frappe.io/support",
)


def _get(item, key, default=None):
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _set(item, key, value):
    if isinstance(item, dict):
        item[key] = value
    else:
        setattr(item, key, value)


def filter_navbar_settings_in_boot(bootinfo):
    """Filtra y corrige help_dropdown en boot (bootinfo puede ser dict si viene de caché)."""
    ns = bootinfo.get("navbar_settings")
    if not ns:
        return
    help_dropdown = _get(ns, "help_dropdown") or getattr(ns, "help_dropdown", None)
    if not help_dropdown:
        return

    for item in help_dropdown:
        label = (str(_get(item, "item_label") or "")).strip()
        route = str(_get(item, "route") or "") or ""
        item_type = _get(item, "item_type")
        route_lower = route.lower()

        # 1) Ocultar por URL: School, Forum, Report an Issue
        if route and any(u in route_lower for u in URLS_TO_HIDE):
            _set(item, "hidden", 1)
            continue

        # 2) Ocultar por etiqueta (por si la URL es distinta)
        if label in (
            "About", "Acerca de",
            "User Forum", "CUC University School", "Report an Issue",
            "Foro de usuarios", "Escuela CUC University", "Reportar un problema",
            "Frappe School",
        ):
            _set(item, "hidden", 1)
            continue

        # 3) Documentation -> docs.edtools.co
        if item_type == "Route" and route:
            if "docs.erpnext.com" in route or label in ("Documentation", "Documentación"):
                _set(item, "route", DOCUMENTATION_URL)
                continue
            # 4) Soporte: no clickeable (por URL o por etiqueta)
            if any(u in route_lower for u in URLS_TO_DISABLE) or ("Soporte" in label and "CUC" in label):
                _set(item, "route", "#")
