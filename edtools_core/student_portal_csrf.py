# Student-portal: CSRF válido y sin caché para que Jinja siempre renderice (evita 417 y {{ logo }} 404).

import re
import frappe


def patch_student_portal_csrf():
	"""Antes de renderizar student-portal: asegurar CSRF y desactivar caché (evita HTML con {{ }} sin renderizar)."""
	_patch_get_context()
	_patch_template_render()


# Logo por defecto que existe en Frappe (evita 404 en /favicon.png)
DEFAULT_LOGO = "/assets/frappe/images/frappe-favicon.svg"
DEFAULT_ABBR = "Edtools Education"


def _patch_get_context():
	try:
		import education.education.www.student_portal as student_portal
		original_get_context = student_portal.get_context

		def get_context(context):
			# 1) Token CSRF
			token = frappe.sessions.get_csrf_token()
			if token and hasattr(frappe.local, "session") and frappe.local.session is not None:
				frappe.local.session["csrf_token"] = token
				if getattr(frappe.local.session, "data", None) is not None:
					frappe.local.session.data["csrf_token"] = token
			context["csrf_token"] = token or ""
			context["no_cache"] = 1
			try:
				original_get_context(context)
			except Exception:
				pass
			# 2) Título y logo por defecto (Education v15 puede no tener los campos en Education Settings)
			context["abbr"] = context.get("abbr") or DEFAULT_ABBR
			context["logo"] = context.get("logo") or DEFAULT_LOGO
			return context

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
				abbr = (getattr(self, "context", None) or {}).get("abbr") or DEFAULT_ABBR
				logo = (getattr(self, "context", None) or {}).get("logo") or DEFAULT_LOGO
				abbr_safe = abbr.replace("\\", "\\\\").replace("'", "\\'")
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
				# Título de pestaña: sustituir literal {{ abbr }} o vacío
				html = re.sub(
					r"window\.document\.title\s*=\s*'\{\{\s*abbr\s*\}\}'",
					f"window.document.title = '{abbr_safe}'",
					html,
					count=1,
				)
				html = html.replace("window.document.title = ''", f"window.document.title = '{abbr_safe}'", 1)
				# Logo/favicon: evitar 404 usando ruta que existe en Frappe
				html = html.replace("link.href = '{{ logo }}'", f"link.href = '{logo}'", 1)
				html = html.replace("link.href = '/favicon.png'", f"link.href = '{logo}'", 1)
				# Cualquier referencia a /favicon.png (link del head, script, etc.) → logo que existe
				html = re.sub(r'href\s*=\s*["\']/favicon\.png["\']', f'href="{logo}"', html)
			return self.build_response(html)

		TemplatePage.render = render
		TemplatePage._edtools_csrf_patched = True
	except Exception:
		pass
