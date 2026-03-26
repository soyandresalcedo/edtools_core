# Copyright (c) 2026, EdTools and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe import _

from edtools_core.course_enrollment_import import coerce_enrollment_date_str, process_enrollments
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

		default_date = coerce_enrollment_date_str(self.get("enrollment_date"))

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

		try:
			result = process_enrollments(
				file_path,
				default_enrollment_date=default_date,
				progress_callback=_progress,
			)
		except Exception as e:
			frappe.log_error(
				title="Course Enrollment Import — error no controlado",
				message=frappe.get_traceback(),
			)
			frappe.throw(
				_("Error al procesar la importación: {0}").format(str(e)),
				title=_("Importación"),
			)

		s = result.get("summary") or {}
		validation_errors = result.get("validation_errors") or []
		results = result.get("results") or []
		errors = result.get("errors") or []

		summary_html = f"""
		<h4 style="margin-top: 10px; color: var(--text-color);">{_('Resultado del proceso')}</h4>
		<div style="background-color: var(--fg-color); padding: 14px; border-radius: 6px; margin-bottom: 12px;
		            border: 1px solid var(--border-color); color: var(--text-color);">
			<p><strong>{_('Course Enrollment creados')}:</strong> {s.get('course_enrollments_created', 0)}</p>
			<p><strong>{_('Duplicados (ya inscrito en el periodo)')}:</strong> {s.get('duplicates', 0)}</p>
			<p><strong>{_('Grupos de estudiantes (creados/actualizados)')}:</strong> {s.get('student_groups_created_or_updated', 0)}</p>
			<p><strong>{_('Filas con error en procesamiento')}:</strong> {s.get('rows_with_errors', 0)}</p>
		</div>
		"""

		rows_html = ""
		if validation_errors:
			for e in validation_errors:
				row = e.get("row") if e.get("row") is not None else "—"
				rows_html += f"""
				<tr style="border-bottom: 1px solid var(--border-color);">
					<td style="border: 1px solid var(--border-color); padding: 10px;">{row}</td>
					<td style="border: 1px solid var(--border-color); padding: 10px;">—</td>
					<td style="border: 1px solid var(--border-color); padding: 10px;">—</td>
					<td style="border: 1px solid var(--border-color); padding: 10px;">—</td>
					<td style="border: 1px solid var(--border-color); padding: 10px;">ErrorValidacion</td>
					<td style="border: 1px solid var(--border-color); padding: 10px;">{e.get('message', '')}</td>
				</tr>
				"""
		else:
			for r in results:
				rows_html += f"""
				<tr style="border-bottom: 1px solid var(--border-color);">
					<td style="border: 1px solid var(--border-color); padding: 10px;">{r.get('row') if r.get('row') is not None else '—'}</td>
					<td style="border: 1px solid var(--border-color); padding: 10px;">{r.get('student_id') or r.get('student') or '—'}</td>
					<td style="border: 1px solid var(--border-color); padding: 10px;">{r.get('course_input') or r.get('course') or '—'}</td>
					<td style="border: 1px solid var(--border-color); padding: 10px;">{r.get('academic_term') or '—'}</td>
					<td style="border: 1px solid var(--border-color); padding: 10px;">{r.get('status') or '—'}</td>
					<td style="border: 1px solid var(--border-color); padding: 10px;">{r.get('detail') or '—'}</td>
				</tr>
				"""

		table_html = f"""
		<table style="width: 100%; border-collapse: collapse; margin-top: 10px;
		              background-color: var(--bg-color); color: var(--text-color);">
			<thead style="background-color: var(--border-color); border-bottom: 2px solid var(--border-color);">
				<tr>
					<th style="border: 1px solid var(--border-color); padding: 12px; text-align: left;">{_('Fila')}</th>
					<th style="border: 1px solid var(--border-color); padding: 12px; text-align: left;">{_('Estudiante')}</th>
					<th style="border: 1px solid var(--border-color); padding: 12px; text-align: left;">{_('Curso')}</th>
					<th style="border: 1px solid var(--border-color); padding: 12px; text-align: left;">{_('Término')}</th>
					<th style="border: 1px solid var(--border-color); padding: 12px; text-align: left;">{_('Estado')}</th>
					<th style="border: 1px solid var(--border-color); padding: 12px; text-align: left;">{_('Detalle')}</th>
				</tr>
			</thead>
			<tbody>
				{rows_html or f"<tr><td colspan='6' style='padding: 12px;'>{_('Sin registros para mostrar.')}</td></tr>"}
			</tbody>
		</table>
		"""

		errors_html = ""
		if errors:
			error_items = "".join(
				f"<li>{_('Fila')} {e.get('row') if e.get('row') is not None else '—'}: {e.get('message', '')}</li>"
				for e in errors
			)
			errors_html = f"""
			<div style="margin-top: 12px; background-color: var(--fg-color); border: 1px solid var(--border-color); padding: 10px; border-radius: 6px;">
				<strong>{_('Errores detectados')}</strong>
				<ul style="margin-top: 8px;">{error_items}</ul>
			</div>
			"""

		self.result_summary = summary_html + table_html
		self.result_errors = errors_html
		self.flags.ignore_permissions = True
		self.save()

		has_issues = bool(result.get("validation_errors") or result.get("errors"))
		return {
			"success": bool(result.get("success")) and not has_issues,
			"validation_errors": result.get("validation_errors"),
			"summary": result.get("summary"),
			"errors": result.get("errors"),
			"message": _("Importación finalizada. Revisa el bloque de resultados en el formulario."),
		}
