__version__ = "0.0.1"


def _patch_portal_redirect():
	"""Redirect Website Users (e.g. Student) to role home page after login."""
	try:
		from edtools_core.portal_redirect import patch_redirect_post_login
		patch_redirect_post_login()
	except Exception:
		pass


def _patch_student_portal_csrf():
	"""Asegura CSRF token en student-portal para evitar 417 en get_user_info."""
	try:
		from edtools_core.student_portal_csrf import patch_student_portal_csrf
		patch_student_portal_csrf()
	except Exception:
		pass


_patch_portal_redirect()
_patch_student_portal_csrf()
