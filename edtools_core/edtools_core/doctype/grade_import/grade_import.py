# Copyright (c) 2026, EdTools and contributors
# For license information, please see license.txt

from __future__ import annotations

import html

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

		s = result.get("summary") or {}
		validation_errors = result.get("validation_errors") or []
		results = result.get("results") or []
		errors = result.get("errors") or []

		summary_html = f"""
		<h4 style="margin-top: 10px; color: var(--text-color);">Resultado del proceso</h4>
		<div style="background-color: var(--fg-color); padding: 14px; border-radius: 6px; margin-bottom: 12px;
		            border: 1px solid var(--border-color); color: var(--text-color);">
			<p><strong>Grupos de estudiantes creados:</strong> {s.get('student_groups_created', 0)}</p>
			<p><strong>Planes de evaluación creados:</strong> {s.get('assessment_plans_created', 0)}</p>
			<p><strong>Resultados nuevos creados:</strong> {s.get('assessment_results_created', 0)}</p>
			<p><strong>Resultados existentes actualizados:</strong> {s.get('assessment_results_updated', 0)}</p>
			<p><strong>Resultados submitted actualizados en sitio:</strong> {s.get('assessment_results_updated_submitted', 0)}</p>
			<p><strong>Filas procesadas correctamente:</strong> {s.get('rows_processed', 0)}</p>
			<p><strong>Filas con error:</strong> {s.get('rows_with_errors', 0)}</p>
		</div>
		"""

		rows_html = ""
		if validation_errors:
			for e in validation_errors:
				row = e.get("row") if e.get("row") is not None else "—"
				msg = html.escape(str(e.get("message", "")))
				rows_html += f"""
				<tr style="border-bottom: 1px solid var(--border-color);">
					<td style="border: 1px solid var(--border-color); padding: 10px;">{row}</td>
					<td style="border: 1px solid var(--border-color); padding: 10px;">—</td>
					<td style="border: 1px solid var(--border-color); padding: 10px;">—</td>
					<td style="border: 1px solid var(--border-color); padding: 10px;">—</td>
					<td style="border: 1px solid var(--border-color); padding: 10px;">ErrorValidacion</td>
					<td style="border: 1px solid var(--border-color); padding: 10px;">{msg}</td>
				</tr>
				"""
		else:
			for r in results:
				row = r.get("row") if r.get("row") is not None else "—"
				student_id = html.escape(str(r.get("student_id") or r.get("student") or "—"))
				course_label = html.escape(str(r.get("course_input") or r.get("course") or "—"))
				term = html.escape(str(r.get("academic_term") or "—"))
				status = html.escape(str(r.get("status") or "—"))
				detail = html.escape(str(r.get("detail") or "—"))
				rows_html += f"""
				<tr style="border-bottom: 1px solid var(--border-color);">
					<td style="border: 1px solid var(--border-color); padding: 10px;">{row}</td>
					<td style="border: 1px solid var(--border-color); padding: 10px;">{student_id}</td>
					<td style="border: 1px solid var(--border-color); padding: 10px;">{course_label}</td>
					<td style="border: 1px solid var(--border-color); padding: 10px;">{term}</td>
					<td style="border: 1px solid var(--border-color); padding: 10px;">{status}</td>
					<td style="border: 1px solid var(--border-color); padding: 10px;">{detail}</td>
				</tr>
				"""

		table_html = f"""
		<table style="width: 100%; border-collapse: collapse; margin-top: 10px;
		              background-color: var(--bg-color); color: var(--text-color);">
			<thead style="background-color: var(--border-color); border-bottom: 2px solid var(--border-color);">
				<tr>
					<th style="border: 1px solid var(--border-color); padding: 12px; text-align: left;">Fila</th>
					<th style="border: 1px solid var(--border-color); padding: 12px; text-align: left;">Estudiante</th>
					<th style="border: 1px solid var(--border-color); padding: 12px; text-align: left;">Curso</th>
					<th style="border: 1px solid var(--border-color); padding: 12px; text-align: left;">Término</th>
					<th style="border: 1px solid var(--border-color); padding: 12px; text-align: left;">Estado</th>
					<th style="border: 1px solid var(--border-color); padding: 12px; text-align: left;">Detalle</th>
				</tr>
			</thead>
			<tbody>
				{rows_html or "<tr><td colspan='6' style='padding: 12px;'>Sin registros para mostrar.</td></tr>"}
			</tbody>
		</table>
		"""

		errors_html = ""
		if errors:
			error_items = "".join(
				f"<li>Fila {e.get('row') if e.get('row') is not None else '—'}: {html.escape(str(e.get('message', '')))}</li>"
				for e in errors
			)
			errors_html = f"""
			<div style="margin-top: 12px; background-color: var(--fg-color); border: 1px solid var(--border-color); padding: 10px; border-radius: 6px;">
				<strong>Errores detectados</strong>
				<ul style="margin-top: 8px;">{error_items}</ul>
			</div>
			"""

		self.result_summary = summary_html + table_html
		self.result_errors = errors_html
		self.flags.ignore_permissions = True
		self.save()

		has_issues = bool(result.get("validation_errors") or result.get("errors"))
		return {
			"success": bool(result.get("success", False)) and not has_issues,
			"validation_errors": result.get("validation_errors"),
			"summary": result.get("summary"),
			"errors": result.get("errors"),
			"message": "Importación finalizada. Revisa el bloque de resultados en el formulario.",
		}
