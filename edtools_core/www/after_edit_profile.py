# Copyright (c) Edtools
# Redirige al usuario tras editar perfil: Student -> student-portal, resto -> /me
# Frappe busca el .py con guiones reemplazados por _ (after_edit_profile.py).

import frappe

from edtools_core.redirect_utils import get_role_based_redirect_url

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.redirect("/login")
	frappe.redirect(get_role_based_redirect_url())
