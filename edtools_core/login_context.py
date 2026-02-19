# Parche del contexto de la página de login: logo CUC University y nombre de app.
# Así la pantalla de login siempre muestra el logo y "CUC University" sin depender de Website Settings.


def patch_login_context():
	"""Override get_context del login para inyectar logo y app_name de CUC University."""
	import frappe
	from frappe.www import login as login_module

	original_get_context = login_module.get_context

	def get_context(context):
		original_get_context(context)
		# Forzar logo y nombre en la página de login
		context["logo"] = "/assets/edtools_core/images/cuc-university-logo.png"
		context["app_name"] = "CUC University"

	login_module.get_context = get_context
