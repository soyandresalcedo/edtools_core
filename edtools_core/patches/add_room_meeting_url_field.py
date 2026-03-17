# Copyright (c) Edtools
# Agrega el campo meeting_url al DocType Room para enlaces de reunión virtual (Teams, Zoom, etc.).
# Límite 500 caracteres para soportar URLs largas de Teams, Zoom, etc.

MEETING_URL_LENGTH = 500

import frappe


def execute():
	custom_field_name = frappe.db.exists(
		"Custom Field",
		{"dt": "Room", "fieldname": "meeting_url"}
	)
	if not custom_field_name:
		cf = frappe.get_doc({
			"doctype": "Custom Field",
			"dt": "Room",
			"fieldname": "meeting_url",
			"label": "Meeting URL",
			"fieldtype": "Data",
			"length": MEETING_URL_LENGTH,
			"description": "URL de Teams, Zoom o otra plataforma para clases virtuales. Se muestra como enlace en el horario del portal.",
			"insert_after": "room_number",
		})
		cf.insert(ignore_permissions=True)
		frappe.db.commit()
		frappe.logger().info("Custom Field Room.meeting_url created (length=%s)", MEETING_URL_LENGTH)
	else:
		# Actualizar longitud si ya existía con el valor por defecto (140)
		cf = frappe.get_doc("Custom Field", custom_field_name)
		current_length = int(cf.get("length") or 0)
		if current_length < MEETING_URL_LENGTH:
			cf.length = MEETING_URL_LENGTH
			cf.save(ignore_permissions=True)
			frappe.db.commit()
			# Cambiar tipo de columna en la base de datos (PostgreSQL: varchar(500))
			frappe.db.change_column_type("Room", "meeting_url", "varchar(%s)" % MEETING_URL_LENGTH)
			frappe.logger().info("Custom Field Room.meeting_url length updated to %s", MEETING_URL_LENGTH)
		else:
			frappe.logger().info("Custom Field Room.meeting_url already exists")
