# Copyright (c) Edtools
# Agrega el campo meeting_url al DocType Room para enlaces de reunión virtual (Teams, Zoom, etc.).

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
			"description": "URL de Teams, Zoom o otra plataforma para clases virtuales. Se muestra como enlace en el horario del portal.",
			"insert_after": "room_number",
		})
		cf.insert(ignore_permissions=True)
		frappe.db.commit()
		frappe.logger().info("Custom Field Room.meeting_url created")
	else:
		frappe.logger().info("Custom Field Room.meeting_url already exists")
