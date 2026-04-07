# Copyright (c) Edtools — destinos por rol (raíz /, /me, post-login OAuth, etc.)

import frappe
from frappe.utils import get_url


def get_role_based_redirect_path(user: str | None = None) -> str:
	"""
	Ruta relativa según sesión:
	- Guest → login (fragmento #login para el panel del formulario)
	- Student → student-portal
	- System User (desk) → /app/home
	- Otros usuarios web → get_home_page() o /me
	"""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return "/login#login"

	roles = frappe.get_roles(user)
	if "Student" in roles:
		return "/student-portal"

	try:
		user_type = frappe.db.get_value("User", user, "user_type")
	except Exception:
		user_type = None
	if user_type == "System User":
		return "/app/home"

	from frappe.website.utils import get_home_page

	hp = get_home_page()
	if hp and str(hp).strip() not in ("", "login", "me", "index"):
		p = str(hp).strip().strip("/")
		return f"/{p}" if p else "/me"
	return "/me"


def get_role_based_redirect_url(user: str | None = None) -> str:
	"""URL absoluta para redirect_to en OAuth y flujos que exigen URL completa."""
	path = get_role_based_redirect_path(user)
	return get_url(path)
