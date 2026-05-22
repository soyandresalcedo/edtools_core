"""
Añade login_logo_image en Website Settings (logo del formulario de /login).

Mismo patrón que login_background_image: Attach Image editable desde el desk
sin depender de app_logo nativo (que puede quedar con rutas /assets/ rotas).
"""

import frappe

DEFAULT_ASSET_LOGO = "/assets/edtools_core/images/cuc-university-logo.png"


def _ensure_field(fieldname, label, fieldtype, insert_after, description):
	existing = frappe.db.exists("Custom Field", {"dt": "Website Settings", "fieldname": fieldname})
	if not existing:
		frappe.get_doc(
			{
				"doctype": "Custom Field",
				"dt": "Website Settings",
				"fieldname": fieldname,
				"label": label,
				"fieldtype": fieldtype,
				"insert_after": insert_after,
				"description": description,
				"translatable": 0,
			}
		).insert(ignore_permissions=True)
		return

	cf = frappe.get_doc("Custom Field", existing)
	changed = False
	for key, val in {
		"insert_after": insert_after,
		"fieldtype": fieldtype,
		"label": label,
		"description": description,
	}.items():
		if cf.get(key) != val:
			cf.set(key, val)
			changed = True
	if changed:
		cf.save(ignore_permissions=True)


def execute():
	frappe.clear_cache(doctype="Website Settings")

	_ensure_field(
		"login_logo_image",
		"Login Logo",
		"Attach Image",
		"app_logo",
		"Logo sobre el formulario de /login (encima del título). PNG con fondo transparente, alto ≥ 200px.",
	)

	# Reordenar: fondo va después del logo de login
	bg_cf = frappe.db.exists("Custom Field", {"dt": "Website Settings", "fieldname": "login_background_image"})
	if bg_cf:
		cf = frappe.get_doc("Custom Field", bg_cf)
		if cf.insert_after != "login_logo_image":
			cf.insert_after = "login_logo_image"
			cf.save(ignore_permissions=True)

	# Migrar valor existente de app_logo → login_logo_image si aplica
	ws = frappe.get_single("Website Settings")
	if not (ws.get("login_logo_image") or "").strip():
		app_logo = (ws.get("app_logo") or "").strip()
		ws.login_logo_image = app_logo or DEFAULT_ASSET_LOGO
		ws.flags.ignore_permissions = True
		ws.save(ignore_permissions=True)

	frappe.db.commit()
	frappe.clear_cache(doctype="Website Settings")
