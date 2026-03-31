# Parche del contexto de la página de login para branding institucional.


def patch_login_context():
	"""Override get_context del login para inyectar logo y app_name de IDITEK."""
	import frappe
	from frappe.www import login as login_module

	original_get_context = login_module.get_context

	def get_context(context):
		original_get_context(context)
		# Forzar logo y nombre en la página de login
		context["logo"] = "/assets/edtools_core/images/iditek-logo.png?v=20260331"
		context["app_name"] = "IDITEK"

	login_module.get_context = get_context
