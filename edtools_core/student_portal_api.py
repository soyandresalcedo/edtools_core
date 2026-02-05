# Inyecta get_user_info (y get_student_info) en education.education.api para Student Portal.
# Education version-15 no tiene estos métodos; el frontend Vue (develop) sí los llama.

import frappe


@frappe.whitelist()
def get_user_info():
	"""Compat con Student Portal Vue (education develop). Education v15 no lo tiene."""
	if frappe.session.user == "Guest":
		frappe.throw("Authentication failed", exc=frappe.AuthenticationError)
	users = frappe.db.get_list(
		"User",
		fields=["name", "email", "enabled", "user_image", "full_name", "user_type"],
		filters={"name": frappe.session.user},
	)
	if not users:
		frappe.throw("User not found", exc=frappe.AuthenticationError)
	result = users[0]
	result["session_user"] = True
	return result


def patch_education_api():
	"""Inyecta get_user_info (y get_student_info si falta) en education.education.api."""
	try:
		import education.education.api as edu_api
		edu_api.get_user_info = get_user_info
		# get_student_info suele estar en v15; por si no, lo exponemos desde edtools_core
		if not hasattr(edu_api, "get_student_info"):
			from edtools_core.student_portal_api import _get_student_info
			edu_api.get_student_info = _get_student_info
	except Exception:
		pass


@frappe.whitelist()
def _get_student_info():
	"""Solo se usa si education.api no tiene get_student_info."""
	email = frappe.session.user
	if email == "Administrator":
		return
	students = frappe.db.get_list(
		"Student",
		fields=["*"],
		filters={"user": email},
	)
	if not students:
		return
	student_info = students[0]
	# current_program y student_groups si existen en education
	try:
		import education.education.api as edu_api
		if hasattr(edu_api, "get_current_enrollment") and hasattr(edu_api, "get_student_groups"):
			current_program = edu_api.get_current_enrollment(student_info["name"])
			if current_program:
				student_groups = edu_api.get_student_groups(student_info["name"], current_program.get("program"))
				student_info["student_groups"] = student_groups or []
				student_info["current_program"] = current_program
	except Exception:
		pass
	return student_info
