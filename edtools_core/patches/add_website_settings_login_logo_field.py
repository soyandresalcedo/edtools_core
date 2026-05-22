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

	updates = {
		"insert_after": insert_after,
		"fieldtype": fieldtype,
		"label": label,
		"description": description,
	}
	for key, val in updates.items():
		if frappe.db.get_value("Custom Field", existing, key) != val:
			frappe.db.set_value("Custom Field", existing, key, val, update_modified=False)


def execute():
	frappe.clear_cache(doctype="Website Settings")

	_ensure_field(
		"login_logo_image",
		"Login Logo",
		"Attach Image",
		"app_logo",
		"Logo sobre el formulario de /login (encima del título). PNG con fondo transparente, alto ≥ 200px.",
	)

	# Refrescar meta antes de reordenar insert_after (evita LinkValidationError)
	frappe.db.commit()
	frappe.clear_cache(doctype="Website Settings")
	frappe.clear_cache(doctype="Custom Field")

	bg_cf = frappe.db.exists("Custom Field", {"dt": "Website Settings", "fieldname": "login_background_image"})
	if bg_cf and frappe.db.get_value("Custom Field", bg_cf, "insert_after") != "login_logo_image":
		frappe.db.set_value(
			"Custom Field",
			bg_cf,
			"insert_after",
			"login_logo_image",
			update_modified=False,
		)

	# Migrar valor existente de app_logo → login_logo_image si aplica
	ws = frappe.get_single("Website Settings")
	if not (ws.get("login_logo_image") or "").strip():
		app_logo = (ws.get("app_logo") or "").strip()
		frappe.db.set_value(
			"Website Settings",
			"Website Settings",
			"login_logo_image",
			app_logo or DEFAULT_ASSET_LOGO,
			update_modified=True,
		)

	frappe.db.commit()
	frappe.clear_cache(doctype="Website Settings")
