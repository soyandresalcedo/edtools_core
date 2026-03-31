# Contexto de la página de login: delegar a Frappe y forzar branding institucional.

import frappe

no_cache = True


def get_context(context):
	from frappe.www import login as frappe_login

	frappe_login.get_context(context)
	context["logo"] = "/assets/edtools_core/images/logo-iditek.png?v=20260401"
	context["app_name"] = "IDITEK"
