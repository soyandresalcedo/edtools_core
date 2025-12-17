import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def after_install():
	"""Run after edtools_core app installation"""
	create_student_status_fields()
	frappe.db.commit()


def create_student_status_fields():
	"""Create custom fields for Student status management"""
	create_custom_fields(get_custom_fields())
	frappe.logger().info("Created custom fields for Student status management")


def get_custom_fields():
	"""
	Custom fields for Student DocType to manage academic/administrative status.

	Fields:
	- student_status: Select field with predefined status options
	- status_change_date: Date field to track when status was changed
	- status_notes: Small text field for optional notes about status change

	These fields work in conjunction with the existing 'enabled' field:
	- 'enabled': Technical/system access control (can login?)
	- 'student_status': Academic/administrative control (can enroll in programs?)
	"""
	return {
		"Student": [
			{
				"fieldname": "student_status",
				"fieldtype": "Select",
				"label": "Student Status",
				"options": "\nActive\nLOA\nGraduated\nSuspended\nWithdrawn\nTransferred\nInactive",
				"default": "Active",
				"insert_after": "enabled",
				"in_list_view": 1,
				"in_standard_filter": 1,
				"reqd": 1,
				"description": "Academic/administrative status. Only Active students can be enrolled in programs.",
			},
			{
				"fieldname": "status_change_date",
				"fieldtype": "Date",
				"label": "Status Change Date",
				"insert_after": "student_status",
				"read_only": 1,
				"description": "Date when student status was last changed",
			},
			{
				"fieldname": "status_notes",
				"fieldtype": "Small Text",
				"label": "Status Notes",
				"insert_after": "status_change_date",
				"description": "Optional notes about status change (reason, context, etc.)",
			},
		]
	}
