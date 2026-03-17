# Aumenta el límite del Custom Field Room.meeting_url de 140 a 500 caracteres.
# Ejecutar una vez en sitios donde el campo ya existía con el valor por defecto.

MEETING_URL_LENGTH = 500

import frappe


def execute():
	custom_field_name = frappe.db.exists(
		"Custom Field",
		{"dt": "Room", "fieldname": "meeting_url"}
	)
	if not custom_field_name:
		return
	cf = frappe.get_doc("Custom Field", custom_field_name)
	current_length = int(cf.get("length") or 0)
	if current_length >= MEETING_URL_LENGTH:
		return
	cf.length = MEETING_URL_LENGTH
	cf.save(ignore_permissions=True)
	frappe.db.commit()
	frappe.db.change_column_type("Room", "meeting_url", "varchar(%s)" % MEETING_URL_LENGTH)
	frappe.logger().info("Room.meeting_url length updated to %s", MEETING_URL_LENGTH)
