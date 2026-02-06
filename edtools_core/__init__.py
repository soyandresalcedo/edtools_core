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


def _patch_education_billing():
	"""Si education.education.billing no existe (p. ej. Education v15), inyectar el de edtools_core."""
	import sys
	import types
	try:
		import education.education.billing as _  # noqa: F401
		return
	except ModuleNotFoundError:
		pass
	from edtools_core import billing as edtools_billing
	billing = types.ModuleType("education.education.billing")
	billing.get_payment_options = edtools_billing.get_payment_options
	billing.handle_payment_success = edtools_billing.handle_payment_success
	billing.handle_payment_failure = edtools_billing.handle_payment_failure
	sys.modules["education.education.billing"] = billing
	try:
		import education.education as edu_edu
		edu_edu.billing = billing
	except Exception:
		pass


_patch_portal_redirect()
_patch_student_portal_csrf()
_patch_education_api()
_patch_education_billing()
