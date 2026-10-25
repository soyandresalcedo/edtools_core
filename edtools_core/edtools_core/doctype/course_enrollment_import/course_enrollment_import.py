# Copyright (c) 2026, EdTools and contributors
# For license information, please see license.txt

from __future__ import annotations

import html
import os

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import format_datetime, now_datetime

from edtools_core.course_enrollment_import import coerce_enrollment_date_str, process_enrollments
from edtools_core.grade_import import _resolve_file_path

DOCTYPE = "Course Enrollment Import"

# El import corre en segundo plano, en una cola propia que atiende el worker de
# supervisord "frappe-worker-import" (ENABLE_WORKER=1). Un solo job_id por sitio:
# mientras haya uno en cola o corriendo no se puede lanzar otro.
QUEUE = "enrollment_import"
JOB_ID = "course_enrollment_import"
JOB_TIMEOUT = 7200  # 2 h; 400 filas tardan ~15 min (Moodle se llama por cada estudiante)
LOCK_NAME = "course_enrollment_import"

EVENT_PROGRESS = "course_enrollment_import_progress"
EVENT_DONE = "course_enrollment_import_done"


class CourseEnrollmentImport(Document):
	@frappe.whitelist()
	def clear_import_results(self):
		"""Limpia únicamente los campos de resultados de importación."""
		if _import_running():
			frappe.throw(_("Hay una importación en curso; espera a que termine para limpiar los resultados."))
		self.result_summary = ""
		self.result_errors = ""
		self.flags.ignore_permissions = True
		self.save()
		return {"ok": True}

	@frappe.whitelist()
	def process_import(self):
		"""Valida lo mínimo y encola el import; el resultado queda en el formulario al terminar."""
		file_url = (self.get("excel_file") or "").strip()
		if not file_url:
			frappe.throw(_("Por favor adjunta un archivo Excel (.xlsx) o CSV."))

		if not _resolve_file_path(file_url):
			frappe.throw(
				_(
					"No se encontró el archivo en el servidor. Si lo subiste como privado, se soporta; vuelve a intentar o recarga el archivo."
				)
			)

		if _import_running():
			frappe.throw(
				_("Ya hay una importación en curso. Espera a que termine; el resultado aparecerá en este formulario."),
				title=_("Importación en curso"),
			)

		if not _worker_available():
			frappe.throw(
				_(
					"No hay un proceso en segundo plano disponible para importar (cola {0}). "
					"Avisa a soporte: se activa con ENABLE_WORKER=1 en el servidor."
				).format(QUEUE),
				title=_("Importación no disponible"),
			)

		default_date = coerce_enrollment_date_str(self.get("enrollment_date"))
		user = frappe.session.user

		frappe.db.set_single_value(
			DOCTYPE,
			{
				"result_summary": _status_html(
					_("Importación en cola"),
					_("Lanzada por {0} el {1}. Puedes cerrar esta ventana: el resultado aparecerá aquí al terminar.").format(
						html.escape(user), format_datetime(now_datetime())
					),
				),
				"result_errors": "",
			},
		)
		# Guardar antes de encolar: así el trabajo no pisa su estado "en curso" con este
		# "en cola", y el control de duplicados de Frappe ve el job desde ya (doble clic).
		frappe.db.commit()

		job = frappe.enqueue(
			"edtools_core.edtools_core.doctype.course_enrollment_import.course_enrollment_import.run_import_job",
			queue=QUEUE,
			timeout=JOB_TIMEOUT,
			job_id=JOB_ID,
			deduplicate=True,
			file_url=file_url,
			default_enrollment_date=default_date,
		)
		if job is None:
			# Frappe no lo encoló porque ya había uno en cola o corriendo.
			frappe.throw(
				_("Ya hay una importación en curso. Espera a que termine; el resultado aparecerá en este formulario."),
				title=_("Importación en curso"),
			)

		return {
			"queued": True,
			"message": _("Importación en cola. Puedes cerrar esta ventana: el resultado aparecerá en el formulario al terminar."),
		}


@frappe.whitelist()
def get_import_status():
	"""Para el formulario: ¿hay una importación en cola o corriendo?"""
	frappe.has_permission(DOCTYPE, "read", throw=True)
	from frappe.utils.background_jobs import get_job_status

	status = get_job_status(JOB_ID)
	status = str(getattr(status, "value", status) or "")
	return {"running": status in ("queued", "started"), "status": status}


def run_import_job(file_url: str, default_enrollment_date: str | None = None):
	"""Trabajo en segundo plano. Corre como el usuario que lanzó el import."""
	from frappe.utils.file_lock import LockTimeoutError
	from frappe.utils.synchronization import filelock

	user = frappe.session.user

	def _progress(current, total, message):
		pct = min(100, round(100 * current / total, 1)) if total and total > 0 else 0
		frappe.publish_realtime(
			EVENT_PROGRESS,
			{"progress": pct, "current": current, "total": total, "message": message or ""},
			user=user,
		)

	try:
		# Segundo candado, por si alguna vez hay dos workers en la cola: el de Frappe
		# (job_id) evita encolar dos; este evita que dos corran a la vez.
		os.makedirs(frappe.get_site_path("locks"), exist_ok=True)
		with filelock(LOCK_NAME, timeout=5):
			frappe.db.set_single_value(
				DOCTYPE,
				"result_summary",
				_status_html(
					_("Importación en curso"),
					_("Empezó el {0}. El resultado aparecerá aquí al terminar.").format(
						format_datetime(now_datetime())
					),
				),
			)
			frappe.db.commit()

			file_path = _resolve_file_path(file_url)
			if not file_path:
				raise FileNotFoundError(_("No se encontró el archivo {0} en el servidor.").format(file_url))

			result = process_enrollments(
				file_path,
				default_enrollment_date=default_enrollment_date,
				progress_callback=_progress,
				commit_each_row=True,
			)

			summary_html, errors_html = build_results_html(result)
			frappe.db.set_single_value(
				DOCTYPE, {"result_summary": summary_html, "result_errors": errors_html}
			)
			frappe.db.commit()

			has_issues = bool(result.get("validation_errors") or result.get("errors"))
			frappe.publish_realtime(
				EVENT_DONE,
				{
					"ok": bool(result.get("success")) and not has_issues,
					"summary": result.get("summary"),
					"message": _("Importación finalizada. Revisa el bloque de resultados en el formulario."),
				},
				user=user,
			)
	except LockTimeoutError:
		# Otra importación tiene el candado: no tocar su resumen.
		frappe.db.rollback()
		frappe.publish_realtime(
			EVENT_DONE,
			{"ok": False, "message": _("Ya había otra importación corriendo; esta no se ejecutó.")},
			user=user,
		)
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(
			title="Course Enrollment Import — error no controlado",
			message=frappe.get_traceback(),
		)
		frappe.db.set_single_value(
			DOCTYPE,
			"result_summary",
			_status_html(
				_("La importación se detuvo por un error"),
				_(
					"Lo ya procesado quedó guardado. Puedes volver a lanzar el mismo archivo: "
					"las filas ya matriculadas salen como duplicadas. Detalle: {0}"
				).format(html.escape(str(e)[:300])),
			),
		)
		frappe.db.commit()
		frappe.publish_realtime(
			EVENT_DONE,
			{"ok": False, "message": _("La importación se detuvo por un error: {0}").format(str(e)[:200])},
			user=user,
		)


def _import_running() -> bool:
	from frappe.utils.background_jobs import is_job_enqueued

	return is_job_enqueued(JOB_ID)


def _worker_available() -> bool:
	"""True si algún worker escucha la cola del import."""
	from frappe.utils.background_jobs import generate_qname, get_workers

	qname = generate_qname(QUEUE)
	try:
		return any(qname in (w.queue_names() or []) for w in get_workers())
	except Exception:
		frappe.log_error(title="Course Enrollment Import — no se pudo consultar workers", message=frappe.get_traceback())
		return False


def _status_html(title: str, detail: str) -> str:
	return f"""
	<h4 style="margin-top: 10px; color: var(--text-color);">{title}</h4>
	<div style="background-color: var(--fg-color); padding: 14px; border-radius: 6px; margin-bottom: 12px;
	            border: 1px solid var(--border-color); color: var(--text-color);">
		<p>{detail}</p>
	</div>
	"""


def build_results_html(result: dict) -> tuple[str, str]:
	"""HTML del resumen, la tabla por fila y la lista de errores (igual que antes)."""
	s = result.get("summary") or {}
	validation_errors = result.get("validation_errors") or []
	results = result.get("results") or []
	errors = result.get("errors") or []

	summary_html = f"""
	<h4 style="margin-top: 10px; color: var(--text-color);">{_('Resultado del proceso')}</h4>
	<div style="background-color: var(--fg-color); padding: 14px; border-radius: 6px; margin-bottom: 12px;
	            border: 1px solid var(--border-color); color: var(--text-color);">
		<p><strong>{_('Terminó')}:</strong> {format_datetime(now_datetime())}</p>
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

	return summary_html + table_html, errors_html
