# Copyright (c) 2026, EdTools and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.model.document import Document


class GradeImport(Document):
	@frappe.whitelist()
	def process_import(self):
		"""
		Valida el archivo adjunto y ejecuta la importación masiva de notas.
		Usa el módulo grade_import para validación y process_grades.
		"""
		from edtools_core.grade_import import validate_format, process_grades, _resolve_file_path

		file_url = (self.get("excel_file") or "").strip()
		if not file_url:
			frappe.throw("Por favor adjunta un archivo Excel (.xlsx) o CSV.")

		grading_scale = (self.get("grading_scale") or "").strip() or None

		# Resolver ruta (soporta /files/ y /private/files/)
		file_path = _resolve_file_path(file_url)
		if not file_path:
			frappe.throw("No se encontró el archivo en el servidor. Si lo subiste como privado, se soporta; vuelve a intentar o recarga el archivo.")

		def _progress(current, total, message):
			if total and total > 0:
				pct = min(100, round(100 * current / total, 1))
			else:
				pct = 0
			frappe.publish_realtime(
				"grade_import_progress",
				{"progress": pct, "current": current, "total": total, "message": message or ""},
				user=frappe.session.user,
			)

		result = process_grades(file_path, grading_scale, progress_callback=_progress)

		# Formatear resumen y errores para mostrar en el formulario
		summary_lines = []
		error_lines = []
		if result.get("validation_errors"):
			summary_lines.append("Validación fallida (no se creó nada):")
			for e in result["validation_errors"]:
				row = e.get("row") or "—"
				msg = "Fila {}: {}".format(row, e.get("message", ""))
				summary_lines.append("  " + msg)
				error_lines.append(msg)
		else:
			s = result.get("summary") or {}
			summary_lines.append(
				"Grupos de estudiantes creados: {}".format(s.get("student_groups_created", 0))
			)
			summary_lines.append(
				"Planes de evaluación creados: {}".format(s.get("assessment_plans_created", 0))
			)
			summary_lines.append(
				"Resultados nuevos creados: {}".format(s.get("assessment_results_created", 0))
			)
			summary_lines.append(
				"Resultados existentes actualizados: {}".format(s.get("assessment_results_updated", 0))
			)
			updated_sub = s.get("assessment_results_updated_submitted", 0)
			if updated_sub:
				summary_lines.append(
					"  (de los cuales ya estaban presentados, actualizados en sitio: {})".format(updated_sub)
				)
			summary_lines.append(
				"Filas procesadas correctamente: {}".format(s.get("rows_processed", 0))
			)
			summary_lines.append(
				"Filas con error: {}".format(s.get("rows_with_errors", 0))
			)

		for e in result.get("errors") or []:
			row = e.get("row") or "—"
			error_lines.append("Fila {}: {}".format(row, e.get("message", "")))

		self.result_summary = "\n".join(summary_lines)
		self.result_errors = "\n".join(error_lines) if error_lines else ""
		self.flags.ignore_permissions = True
		self.save()

		return {
			"success": result.get("success", False),
			"validation_errors": result.get("validation_errors"),
			"summary": result.get("summary"),
			"errors": result.get("errors"),
			"message": self.result_summary,
		}
