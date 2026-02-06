# Copyright (c) Edtools
# Redirige al usuario tras editar perfil: Student -> student-portal, resto -> /me

import frappe
from frappe.website.utils import get_home_page
from frappe.utils import get_url

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.redirect("/login")
	# Estudiantes y otros con role_home_page van a su home; el resto a /me
	home = get_home_page()
	redirect_to = get_url("/" + home.strip("/")) if home else get_url("/me")
	frappe.redirect(redirect_to)
