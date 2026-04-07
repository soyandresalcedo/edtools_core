# Copyright (c) Edtools
# Redirige a usuarios con rol Student (y otros con role_home_page) al portal correcto tras login.

import frappe


def patch_redirect_post_login():
	"""Post-login (OAuth): mismo criterio que raíz / y /me (redirect_utils)."""
	from edtools_core.redirect_utils import get_role_based_redirect_url

	original = frappe.utils.oauth.redirect_post_login

	def redirect_post_login(desk_user: bool, redirect_to: str | None = None, provider: str | None = None):
		if not redirect_to and not desk_user:
			redirect_to = get_role_based_redirect_url(frappe.session.user)
		return original(desk_user, redirect_to=redirect_to, provider=provider)

	frappe.utils.oauth.redirect_post_login = redirect_post_login
	# Por si frappe.www.login ya fue importado (tiene su propia referencia a redirect_post_login).
	try:
		import frappe.www.login as login_mod
		login_mod.redirect_post_login = redirect_post_login
	except Exception:
		pass
