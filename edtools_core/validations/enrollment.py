# Copyright (c) 2024, Andres Salcedo and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def validate_student_status(doc, method=None):
	"""
	Validate that student is enabled AND in Active status before allowing enrollment.

	This validation ensures two conditions are met:
	1. Field 'enabled' must be 1 (technical/system access control)
	2. Field 'student_status' must be 'Active' (academic/administrative control)

	The separation allows for flexible control:
	- A Graduated student (student_status='Graduated') can still access the system
	  (enabled=1) to view transcripts/certificates, but cannot enroll in new programs.
	- A student on LOA (Leave of Absence) can access the system but cannot enroll.
	- A disabled student (enabled=0) cannot access the system at all, regardless of status.

	Args:
		doc: Program Enrollment or Course Enrollment document
		method: Hook method name (not used, required by Frappe hooks signature)

	Raises:
		frappe.ValidationError: If student does not meet requirements for enrollment

	Usage:
		This function is called automatically via doc_events hooks in hooks.py:
		- Program Enrollment: validate event
		- Course Enrollment: validate event
	"""
	if not doc.student:
		# No student specified, skip validation (will fail on required field check)
		return

	# Fetch student data in a single database call for efficiency
	student = frappe.db.get_value(
		"Student", doc.student, ["enabled", "student_status", "student_name"], as_dict=True
	)

	if not student:
		frappe.throw(_("No se encontró el estudiante {0}.").format(doc.student))

	display_name = (student.student_name or doc.student or "").strip() or doc.student

	# Validation 1: Student must be enabled (technical access control)
	if not student.enabled:
		frappe.throw(
			_("No se puede matricular a {0}: la cuenta del estudiante está deshabilitada.").format(
				display_name
			),
			title=_("Cuenta deshabilitada"),
		)

	# Validation 2: Student must be in Active status (academic/administrative control)
	# Default to 'Active' for backward compatibility with existing records
	student_status = student.student_status or "Active"

	if student_status != "Active":
		frappe.throw(
			_(
				"No se puede matricular a {0}: el estado del estudiante es {1}. "
				"Solo se permite matricular estudiantes en estado Activo."
			).format(display_name, student_status),
			title=_("Estado del estudiante no válido"),
		)

	# Log successful validation for audit trail
	frappe.logger().debug(
		f"Enrollment validation passed for student {doc.student} "
		f"(enabled={student.enabled}, status={student_status})"
	)
