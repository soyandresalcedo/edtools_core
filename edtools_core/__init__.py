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


def _patch_education_api():
	"""Inyecta get_user_info en education.education.api (v15 no lo tiene; el Vue develop sí lo llama)."""
	try:
		from edtools_core.student_portal_api import patch_education_api
		patch_education_api()
	except Exception:
		pass


def _patch_login_context():
	"""Login siempre con logo y nombre institucional."""
	try:
		from edtools_core.login_context import patch_login_context
		patch_login_context()
	except Exception:
		pass


def _patch_email_footer():
	"""Quitar 'Sent via ERPNext' del pie de los correos."""
	try:
		from edtools_core.email_footer_patch import patch_email_footer
		patch_email_footer()
	except Exception:
		pass


_patch_portal_redirect()
_patch_student_portal_csrf()
_patch_education_api()
_patch_login_context()
_patch_email_footer()


def _patch_sessions_navbar():
    """Filtra menú Ayuda en boot; sessions.get() sobrescribe navbar_settings después de boot_session."""
    try:
        from edtools_core.sessions_navbar_patch import patch_sessions_get
        patch_sessions_get()
    except Exception:
        pass


_patch_sessions_navbar()