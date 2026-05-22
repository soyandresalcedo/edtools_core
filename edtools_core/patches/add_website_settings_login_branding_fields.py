"""
Crea Custom Fields en Website Settings para personalizar el login dinámicamente:

- login_background_image: imagen de fondo del panel izquierdo (Attach Image)
- login_title_override:   sobrescribe el texto "Login to {app_name}" (Data)
- login_subtitle:         línea bajo el título (Data)

Idempotente: si el campo existe, sólo corrige propiedades clave (insert_after).
Patrón consistente con add_course_short_name_field.py.
"""

import frappe

_FIELDS = [
	{
		"fieldname": "login_background_image",
		"label": "Login Background Image",
		"fieldtype": "Attach Image",
		"insert_after": "app_logo",
		"description": (
			"Imagen de fondo del panel izquierdo en /login. "
			"Recomendado: horizontal ≥ 1920×1080, < 2 MB."
		),
	},
	{
		"fieldname": "login_title_override",
		"label": "Login Title Override",
		"fieldtype": "Data",
		"insert_after": "app_name",
		"description": (
			"Si tiene valor, reemplaza el texto 'Login to {app_name}' del login. "
			"Dejar vacío para usar el comportamiento por defecto."
		),
	},
	{
		"fieldname": "login_subtitle",
		"label": "Login Subtitle",
		"fieldtype": "Data",
		"insert_after": "login_background_image",
		"description": "Texto opcional bajo el título del login (ej. 'Sistema de Gestión Educativa').",
	},
]


def _ensure_field(spec: dict) -> None:
	existing_name = frappe.db.exists(
		"Custom Field",
		{"dt": "Website Settings", "fieldname": spec["fieldname"]},
	)

	if not existing_name:
		doc = frappe.get_doc(
			{
				"doctype": "Custom Field",
				"dt": "Website Settings",
				"fieldname": spec["fieldname"],
				"label": spec["label"],
				"fieldtype": spec["fieldtype"],
				"insert_after": spec["insert_after"],
				"description": spec.get("description"),
				"translatable": 0,
			}
		)
		doc.insert(ignore_permissions=True)
		return

	cf = frappe.get_doc("Custom Field", existing_name)
	changed = False
	if cf.get("insert_after") != spec["insert_after"]:
		cf.insert_after = spec["insert_after"]
		changed = True
	if cf.get("fieldtype") != spec["fieldtype"]:
		cf.fieldtype = spec["fieldtype"]
		changed = True
	if not (cf.get("description") or "").strip() and spec.get("description"):
		cf.description = spec["description"]
		changed = True
	if changed:
		cf.save(ignore_permissions=True)


def execute():
	frappe.clear_cache(doctype="Website Settings")
	for spec in _FIELDS:
		_ensure_field(spec)
	frappe.db.commit()
	frappe.clear_cache(doctype="Website Settings")
