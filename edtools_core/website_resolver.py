# Resuelve /student-portal y /student-portal/* al mismo endpoint para que recargas (F5) no den 404.
# El Vue SPA usa client-side routing; el servidor debe devolver siempre el mismo HTML para cualquier subruta.

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
	if not path:
		from frappe.website.path_resolver import resolve_path
		return resolve_path(path)
	# Normalizar: quitar barras al inicio/final por si el path viene con formato distinto
	path_normalized = (path or "").strip("/ ")
	if path_normalized == "student-portal" or path_normalized.startswith("student-portal/"):
		return "student-portal"
	from frappe.website.path_resolver import resolve_path
	return resolve_path(path)
