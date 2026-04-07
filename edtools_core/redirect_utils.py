import frappe
from frappe.utils import get_url


def get_role_based_redirect_path(user: str | None = None) -> str:
	"""Resuelve destino según rol para evitar /me como destino final."""
	user = user or frappe.session.user

	if not user or user == "Guest":
		return "/login"

	roles = frappe.get_roles(user)
	if "Student" in roles:
		return "/student-portal"

	return "/app/home"


def get_role_based_redirect_url(user: str | None = None) -> str:
	"""Devuelve URL absoluta para flujos que esperan redirect_to completo."""
	return get_url(get_role_based_redirect_path(user))
