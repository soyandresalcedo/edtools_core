# Student-portal: CSRF válido y sin caché para que Jinja siempre renderice (evita 417 y {{ logo }} 404).

import frappe


def patch_student_portal_csrf():
	"""Antes de renderizar student-portal: asegurar CSRF y desactivar caché (evita HTML con {{ }} sin renderizar)."""
	try:
		import education.education.www.student_portal as student_portal
		original_get_context = student_portal.get_context

		def get_context(context):
			# 1) Token para que {{ frappe.session.csrf_token }} no sea None (evita 417)
			# Frappe guarda el token en session.data.csrf_token; la plantilla usa session.csrf_token
			token = frappe.sessions.get_csrf_token()
			if token and hasattr(frappe.local, "session") and frappe.local.session is not None:
				frappe.local.session["csrf_token"] = token
			# 2) Sin caché: cada request renderiza de nuevo con sesión actual (evita servir HTML con {{ abbr }}, {{ logo }} crudos)
			context["no_cache"] = 1
			return original_get_context(context)

		student_portal.get_context = get_context
	except Exception:
		pass
