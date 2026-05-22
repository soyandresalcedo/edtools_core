"""
Lectura centralizada del branding del login desde Website Settings.

Devuelve el contexto que consume www/login.py para inyectar logo, nombre,
título, subtítulo y fondo en la página /login.

Prioridad del logo en /login:
  login_logo_image → app_logo → Navbar Settings → hooks → asset por defecto

Cache buster: ?v=<timestamp> en URLs /files/ tras guardar Website Settings.
"""

import frappe
from frappe import _

DEFAULT_LOGIN_BACKGROUND = "/assets/edtools_core/images/fondo-cuc.png"
DEFAULT_LOGIN_LOGO = "/assets/edtools_core/images/cuc-university-logo.png"


def get_login_branding() -> dict:
	"""Devuelve dict listo para `context.update(...)` en el get_context del login."""
	# Lectura fresca (no cacheada): /login tiene no_cache=True
	ws = frappe.get_doc("Website Settings")

	app_name = (
		ws.app_name
		or frappe.get_system_settings("app_name")
		or _("Edtools")
	)

	title_override = (ws.get("login_title_override") or "").strip()
	title = title_override or _("Login to {0}").format(app_name)

	background = ws.get("login_background_image") or DEFAULT_LOGIN_BACKGROUND
	background = _with_cache_buster(background, ws.modified)

	logo = _resolve_login_logo(ws)
	logo = _with_cache_buster(logo, ws.modified)

	return {
		"logo": logo,
		"app_name": app_name,
		"login_title": title,
		"login_subtitle": (ws.get("login_subtitle") or "").strip(),
		"login_background": background,
	}


def _resolve_login_logo(ws) -> str:
	"""Logo del formulario de login: campo dedicado primero, luego fallbacks."""
	logo = (ws.get("login_logo_image") or ws.get("app_logo") or "").strip()
	if logo:
		return logo

	from frappe.core.doctype.navbar_settings.navbar_settings import get_app_logo

	return get_app_logo() or DEFAULT_LOGIN_LOGO


def _with_cache_buster(url: str | None, modified) -> str | None:
	"""Añade `?v=<timestamp>` a URLs servidas desde /files/."""
	if not url or not url.startswith("/files/"):
		return url
	try:
		ts = int(frappe.utils.get_datetime(modified).timestamp())
	except Exception:
		return url
	sep = "&" if "?" in url else "?"
	return f"{url}{sep}v={ts}"
