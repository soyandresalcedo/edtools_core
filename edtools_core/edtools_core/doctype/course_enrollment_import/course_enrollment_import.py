# Copyright (c) 2026, EdTools and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe import _

from edtools_core.course_enrollment_import import process_enrollments
from edtools_core.grade_import import _resolve_file_path


class CourseEnrollmentImport(Document):
	@frappe.whitelist()
	def process_import(self):
		file_url = (self.get("excel_file") or "").strip()
		if not file_url:
			frappe.throw(_("Por favor adjunta un archivo Excel (.xlsx) o CSV."))

		file_path = _resolve_file_path(file_url)
		if not file_path:
			frappe.throw(
				_(
					"No se encontró el archivo en el servidor. Si lo subiste como privado, se soporta; vuelve a intentar o recarga el archivo."
				)
			)

		default_date = (self.get("enrollment_date") or "").strip() or None

		def _progress(current, total, message):
			if total and total > 0:
				pct = min(100, round(100 * current / total, 1))
			else:
				pct = 0
			frappe.publish_realtime(
				"course_enrollment_import_progress",
				{"progress": pct, "current": current, "total": total, "message": message or ""},
				user=frappe.session.user,
			)

		result = process_enrollments(
			file_path,
			default_enrollment_date=default_date,
			progress_callback=_progress,
		)

		summary_lines = []
		error_lines = []
		if result.get("validation_errors"):
			summary_lines.append(_("Validación fallida (no se procesó el lote):"))
			for e in result["validation_errors"]:
				row = e.get("row") if e.get("row") is not None else "—"
				msg = _("Fila {0}: {1}").format(row, e.get("message", ""))
				summary_lines.append("  " + str(msg))
				error_lines.append(str(msg))
		else:
			s = result.get("summary") or {}
			summary_lines.append(
				_("Course Enrollment creados: {0}").format(s.get("course_enrollments_created", 0))
			)
			summary_lines.append(
				_("Duplicados (ya inscrito en el periodo): {0}").format(s.get("duplicates", 0))
			)
			summary_lines.append(
				_("Grupos de estudiantes (creados/actualizados): {0}").format(
					s.get("student_groups_created_or_updated", 0)
				)
			)
			summary_lines.append(
				_("Filas con error en procesamiento: {0}").format(s.get("rows_with_errors", 0))
			)

		for e in result.get("errors") or []:
			row = e.get("row") if e.get("row") is not None else "—"
			error_lines.append(str(_("Fila {0}: {1}").format(row, e.get("message", ""))))

		self.result_summary = "\n".join(summary_lines)
		self.result_errors = "\n".join(error_lines) if error_lines else ""
		self.flags.ignore_permissions = True
		self.save()

		has_issues = bool(result.get("validation_errors") or result.get("errors"))
		return {
			"success": bool(result.get("success")) and not has_issues,
			"validation_errors": result.get("validation_errors"),
			"summary": result.get("summary"),
			"errors": result.get("errors"),
			"message": self.result_summary,
		}
