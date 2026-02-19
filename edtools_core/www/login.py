# Contexto de la página de login: delegar a Frappe y forzar logo y nombre CUC University.

import frappe

no_cache = True


def get_context(context):
	from frappe.www import login as frappe_login

	frappe_login.get_context(context)
	context["logo"] = "/assets/edtools_core/images/cuc-university-logo.png"
	context["app_name"] = "CUC University"
