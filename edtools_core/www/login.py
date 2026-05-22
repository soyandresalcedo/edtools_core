# Contexto de la página de login: delega al get_context nativo de Frappe y
# sobreescribe logo/nombre/título/subtítulo/fondo desde Website Settings
# vía edtools_core.branding.

no_cache = True


def get_context(context):
	from frappe.www import login as frappe_login
	from edtools_core.branding import get_login_branding

	frappe_login.get_context(context)
	context.update(get_login_branding())
	return context
