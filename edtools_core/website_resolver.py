# Resuelve /student-portal y /student-portal/* al mismo endpoint para que recargas (F5) no den 404.
# El Vue SPA usa client-side routing; el servidor debe devolver siempre el mismo HTML para cualquier subruta.
# Raíz /, /index, /me y /profile → páginas www/*_redirect (get_context + frappe.redirect, patrón CUC).

import frappe


@frappe.whitelist(allow_guest=True)
def clear_student_portal_404_cache():
	"""
	Borra la caché de 404 del website para que /student-portal y subrutas vuelvan a resolverse.
	Útil tras un deploy en Railway si las rutas del student-portal empiezan a devolver 404.
	Llamar una vez: GET o POST a /api/method/edtools_core.website_resolver.clear_student_portal_404_cache
	"""
	try:
		frappe.cache.delete_value("website_404")
		return {"ok": True, "message": "Cache website_404 cleared."}
	except Exception as e:
		return {"ok": False, "message": str(e)}


def resolve(path):
	"""Para student-portal y subrutas (schedule, grades, fees, etc.) devolver endpoint 'student-portal'."""
	path_norm = (path or "").strip("/ ")
	# Raíz e index → página web home_redirect (redirect real en get_context; evita Web Page home "None").
	if not path_norm or path_norm == "index":
		return "home_redirect"
	# Sustituir "My Account" estándar por redirect por rol (mismo criterio que la raíz).
	if path_norm in ("me", "profile"):
		return "me_redirect"
	if path_norm == "student-portal" or path_norm.startswith("student-portal/"):
		return "student-portal"
	from frappe.website.path_resolver import resolve_path

	return resolve_path(path)
