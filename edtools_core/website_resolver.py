# Resuelve /student-portal y /student-portal/* al mismo endpoint para que recargas (F5) no den 404.
# El Vue SPA usa client-side routing; el servidor debe devolver siempre el mismo HTML para cualquier subruta.

import frappe


def resolve(path):
	"""Para student-portal y subrutas (schedule, grades, etc.) devolver endpoint 'student-portal'."""
	if path == "student-portal" or (path.startswith("student-portal/")):
		return "student-portal"
	from frappe.website.path_resolver import resolve_path
	return resolve_path(path)
