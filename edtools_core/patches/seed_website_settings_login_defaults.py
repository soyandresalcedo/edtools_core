"""
Seed inicial de branding en Website Settings.

Sólo escribe campos que estén vacíos para no sobreescribir configuraciones
ya personalizadas por el administrador.

Debe ejecutarse DESPUÉS de add_website_settings_login_branding_fields para
que los Custom Fields ya existan en el meta.
"""

import frappe

_SEED = {
	"app_name": "CUC University",
	"app_logo": "/assets/edtools_core/images/cuc-university-logo.png",
	"login_background_image": "/assets/edtools_core/images/fondo-cuc.png",
	"login_subtitle": "Sistema de Gestión Educativa",
}


def execute():
	frappe.clear_cache(doctype="Website Settings")
	ws = frappe.get_single("Website Settings")

	changed = False
	for field, value in _SEED.items():
		# Saltar si el meta no tiene el campo (algún CF aún no creado, defensa).
		if not ws.meta.has_field(field):
			continue
		current = (ws.get(field) or "").strip() if isinstance(ws.get(field), str) else ws.get(field)
		if not current:
			ws.set(field, value)
			changed = True

	if changed:
		ws.flags.ignore_permissions = True
		ws.flags.ignore_validate = True
		ws.save(ignore_permissions=True)
		frappe.db.commit()

	frappe.clear_cache(doctype="Website Settings")
