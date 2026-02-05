# Copyright (c) Edtools
# Redirige a usuarios con rol Student (y otros con role_home_page) al portal correcto tras login.

import frappe


def patch_redirect_post_login():
	"""Hace que el redirect post-login use get_home_page() para Website Users.
	Así usuarios con rol Student van a /student-portal en lugar de /me.
	"""
	from frappe.utils import get_url
	from frappe.website.utils import get_home_page

	original = frappe.utils.oauth.redirect_post_login

	def redirect_post_login(desk_user: bool, redirect_to: str | None = None, provider: str | None = None):
		if not redirect_to and not desk_user:
			home = get_home_page()
			if home:
				redirect_to = get_url("/" + home.strip("/"))
		return original(desk_user, redirect_to=redirect_to, provider=provider)

	frappe.utils.oauth.redirect_post_login = redirect_post_login
	# Por si frappe.www.login ya fue importado (tiene su propia referencia a redirect_post_login).
	try:
		import frappe.www.login as login_mod
		login_mod.redirect_post_login = redirect_post_login
	except Exception:
		pass
