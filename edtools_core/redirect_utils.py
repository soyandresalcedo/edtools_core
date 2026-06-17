import frappe
from frappe.utils import get_url


def get_role_based_redirect_path(user: str | None = None) -> str:
	"""Resuelve destino según rol para evitar /me como destino final."""
	user = user or frappe.session.user

	if not user or user == "Guest":
		return "/login"

	roles = frappe.get_roles(user)
	if "Student" in roles:
		if _student_has_pending_surveys(user):
			return "/student-portal/surveys"
		return "/student-portal"

	return "/app/home"


def _student_has_pending_surveys(user: str) -> bool:
	"""True si el estudiante vinculado al usuario tiene encuestas obligatorias pendientes."""
	try:
		student_name = frappe.db.get_value("Student", {"user": user}, "name")
		if not student_name:
			return False
		from edtools_core.surveys.portal_gate import is_portal_blocked

		return is_portal_blocked(student_name)
	except Exception:
		frappe.log_error(
			title="Error verificando encuestas en redirect post-login",
			message=frappe.get_traceback(),
		)
		return False


def get_role_based_redirect_url(user: str | None = None) -> str:
	"""Devuelve URL absoluta para flujos que esperan redirect_to completo."""
	return get_url(get_role_based_redirect_path(user))
