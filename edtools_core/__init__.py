__version__ = "0.0.1"


def _patch_portal_redirect():
	"""Redirect Website Users (e.g. Student) to role home page after login."""
	try:
		from edtools_core.portal_redirect import patch_redirect_post_login
		patch_redirect_post_login()
	except Exception:
		pass  # Evitar romper carga si Frappe no está listo


_patch_portal_redirect()
