# Inyecta get_user_info (y get_student_info) en education.education.api para Student Portal.
# Education version-15 no tiene estos métodos; el frontend Vue (develop) sí los llama.

import json
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
	"""Inyecta get_user_info y APIs del Student Portal en education.education.api (v15 puede no tenerlas)."""
	try:
		import education.education.api as edu_api
		edu_api.get_user_info = get_user_info
		# get_student_info suele estar en v15; por si no, lo exponemos desde edtools_core
		if not hasattr(edu_api, "get_student_info"):
			from edtools_core.student_portal_api import _get_student_info
			edu_api.get_student_info = _get_student_info
		if not hasattr(edu_api, "get_school_abbr_logo"):
			edu_api.get_school_abbr_logo = get_school_abbr_logo
		if not hasattr(edu_api, "get_course_schedule_for_student"):
			edu_api.get_course_schedule_for_student = get_course_schedule_for_student
	except Exception:
		pass


@frappe.whitelist()
def get_school_abbr_logo():
	"""Compat con Student Portal Vue (education develop). Education v15 puede no tener estos campos."""
	abbr = None
	logo = None
	try:
		# Education develop tiene school_college_name_abbreviation / school_college_logo; v15 puede no tenerlos
		abbr = frappe.db.get_single_value(
			"Education Settings", "school_college_name_abbreviation"
		)
		logo = frappe.db.get_single_value("Education Settings", "school_college_logo")
	except Exception:
		pass
	return {"name": abbr or "Edtools Education", "logo": logo or "/favicon.png"}


@frappe.whitelist()
def get_course_schedule_for_student(program_name=None, student_groups=None):
	"""Compat con Student Portal Vue (education develop). Education v15 puede no tenerlo."""
	try:
		# Parámetros pueden venir como string (JSON) desde el request
		if isinstance(student_groups, str):
			try:
				student_groups = json.loads(student_groups) if student_groups else []
			except Exception:
				student_groups = []
		if not program_name or not student_groups:
			return []

		def _label(sg):
			if sg is None:
				return None
			if isinstance(sg, dict):
				return sg.get("label") or sg.get("name")
			return sg

		group_names = [_label(sg) for sg in (student_groups or []) if _label(sg)]
		if not group_names:
			return []

		schedule = frappe.db.get_list(
			"Course Schedule",
			fields=[
				"schedule_date",
				"room",
				"class_schedule_color",
				"course",
				"from_time",
				"to_time",
				"instructor",
				"title",
				"name",
			],
			filters={"program": program_name, "student_group": ["in", group_names]},
			order_by="schedule_date asc",
		)
		# Asegurar que from_time/to_time sean strings para el frontend (split('.')[0])
		for row in schedule:
			for field in ("from_time", "to_time"):
				if field in row and row[field] is not None:
					row[field] = str(row[field])
		return schedule
	except Exception as e:
		frappe.log_error(title="get_course_schedule_for_student", message=frappe.get_traceback())
		return []


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
