# Student-portal: CSRF válido y sin caché para que Jinja siempre renderice (evita 417 y {{ logo }} 404).

import re
import frappe


def patch_student_portal_csrf():
	"""Antes de renderizar student-portal: asegurar CSRF y desactivar caché (evita HTML con {{ }} sin renderizar)."""
	_patch_get_context()
	_patch_template_render()


def _patch_get_context():
	try:
		import education.education.www.student_portal as student_portal
		original_get_context = student_portal.get_context

		def get_context(context):
			# 1) Token para que {{ frappe.session.csrf_token }} no sea None (evita 417)
			token = frappe.sessions.get_csrf_token()
			if token and hasattr(frappe.local, "session") and frappe.local.session is not None:
				frappe.local.session["csrf_token"] = token
				if getattr(frappe.local.session, "data", None) is not None:
					frappe.local.session.data["csrf_token"] = token
			context["csrf_token"] = token or ""
			context["no_cache"] = 1
			return original_get_context(context)

		student_portal.get_context = get_context
	except Exception:
		pass


def _patch_template_render():
	"""Corrige el HTML ya renderizado: reemplaza window.csrf_token inválido (None/vacío) por el token real."""
	try:
		from frappe.website.page_renderers import template_page
		TemplatePage = template_page.TemplatePage
		if getattr(TemplatePage, "_edtools_csrf_patched", False):
			return
		original_render = TemplatePage.render

		def render(self):
			html = self.get_html()
			html = self.add_csrf_token(html)
			path = getattr(self, "path", "") or ""
			if path == "student-portal" or (isinstance(path, str) and path.startswith("student-portal/")):
				token = frappe.sessions.get_csrf_token()
				if token:
					safe_token = token.replace("\\", "\\\\").replace("'", "\\'")
					# Sustituir cualquier valor inválido o literal Jinja por el token real
					html = html.replace("window.csrf_token = 'None'", f"window.csrf_token = '{safe_token}'", 1)
					html = html.replace('window.csrf_token = "None"', f'window.csrf_token = "{safe_token}"', 1)
					html = html.replace("window.csrf_token = '{{ csrf_token }}'", f"window.csrf_token = '{safe_token}'", 1)
					html = re.sub(r"window\.csrf_token\s*=\s*''\s*", f"window.csrf_token = '{safe_token}' ", html, count=1)
					html = re.sub(
						r"window\.csrf_token\s*=\s*'\{\{\s*frappe\.session\.csrf_token\s*\}\}'\s*",
						f"window.csrf_token = '{safe_token}' ",
						html,
						count=1,
					)
			return self.build_response(html)

		TemplatePage.render = render
		TemplatePage._edtools_csrf_patched = True
	except Exception:
		pass
