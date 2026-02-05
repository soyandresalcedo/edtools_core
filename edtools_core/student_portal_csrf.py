# Asegura que la página student-portal tenga CSRF token válido (evita 417 en get_user_info).

import frappe


def patch_student_portal_csrf():
	"""Antes de renderizar student-portal, asegurar que la sesión tenga CSRF token."""
	try:
		import education.education.www.student_portal as student_portal
		original_get_context = student_portal.get_context

		def get_context(context):
			# Generar/obtener token para que {{ frappe.session.csrf_token }} en el template no sea None
			frappe.sessions.get_csrf_token()
			return original_get_context(context)

		student_portal.get_context = get_context
	except Exception:
		pass
