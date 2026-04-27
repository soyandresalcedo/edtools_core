# Contexto de la página de login: delegar a Frappe y forzar branding institucional.

import frappe

no_cache = True


def get_context(context):
	from frappe.www import login as frappe_login

	frappe_login.get_context(context)
	context["logo"] = "/assets/edtools_core/images/colegio_anglo_hispano-logoblanco.png?v=20260427"
	context["app_name"] = "Colegio Anglo Hispano"
