# Copyright (c) 2026, EdTools and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate
from frappe.model.document import Document
from frappe.utils import nowdate

class CourseEnrollmentTool(Document):
	
	@frappe.whitelist()
	def get_students_from_group(self):
		"""
		Busca estudiantes del grupo y valida su matrícula en el programa.
		"""
		if not self.student_group or not self.program:
			frappe.throw("Por favor selecciona un Grupo de Estudiantes y un Programa.")

		# 1. Limpiar tabla actual
		self.set("students", [])

		# 2. Obtener estudiantes del grupo (Tabla: Student Group Student)
		# Nota: Ignoramos permisos para asegurar traer todo
		group_students = frappe.get_all("Student Group Student", 
									  filters={"parent": self.student_group, "active": 1},
									  fields=["student", "student_name"])

		if not group_students:
			frappe.msgprint("No se encontraron estudiantes activos en este grupo.", alert=True)
			return

		students_found = 0

		for gs in group_students:
			# 3. Buscar Program Enrollment ACTIVO y SUBMITTED (docstatus=1)
			# Es vital vincular la inscripción al curso con una matrícula de programa real.
			prog_enrollment = frappe.db.get_value("Program Enrollment", {
				"student": gs.student,
				"program": self.program,
				"docstatus": 1
			}, "name")

			if prog_enrollment:
				# Agregamos a la tabla usando el nombre de variable corregido (student_full_name)
				self.append("students", {
					"student": gs.student,
					"student_full_name": gs.student_name, 
					"program_enrollment": prog_enrollment,
					"status": "Pending"
				})
				students_found += 1
		
		# 4. Guardamos el documento Single para que la tabla persista en BD dsdsd
		self.save()
		
		return students_found
	
	@frappe.whitelist()
	def reset_tool(self):
		"""
		Borra todos los campos y guarda el Single DocType vacío,
		ignorando la restricción de campos obligatorios.
		"""
		self.academic_year = None
		self.academic_term = None
		self.student_group = None
		self.course = None
		self.enrollment_date = None
		self.set("students", [])
		
		# ¡ESTA ES LA CLAVE! ignore_mandatory=True permite guardar campos vacíos
		self.flags.ignore_mandatory = True 
		self.save(ignore_permissions=True)


	@frappe.whitelist()
	def enroll_students(self):
		"""
		Recorre la tabla y crea los Course Enrollments con validaciones robustas.
		
		Validaciones:
		- El curso debe estar definido
		- El curso debe existir en el sistema
		- Cada estudiante debe tener un Program Enrollment válido
		- Se evitan duplicados
		"""
		# ------------------------------------------------------------------
		# MOODLE: asegurar categoría padre del Academic Year (fase 1)
		# ------------------------------------------------------------------
		# Requisito: evitar duplicados por idnumber.
		# - Academic Year (padre): idnumber == name == academic_year, parent == 0
		# - Academic Term (hija): idnumber == academic_term_label, name == YYYYMM, parent == moodle_year_category_id
		if not self.academic_year:
			frappe.throw("❌ Academic Year es obligatorio para sincronizar con Moodle")
		if not self.academic_term:
			frappe.throw("❌ Academic Term es obligatorio para sincronizar con Moodle")
		try:
			from edtools_core.moodle_integration import (
				ensure_course,
				ensure_academic_term_category,
				ensure_academic_year_category,
				get_term_category_name,
			)

			moodle_year_category_id = ensure_academic_year_category(str(self.academic_year))
			frappe.msgprint(
				f"🎓 Moodle OK: categoría Academic Year '{self.academic_year}' (id={moodle_year_category_id})",
				indicator="blue",
			)

			moodle_term_category_id = ensure_academic_term_category(
				academic_term_label=str(self.academic_term),
				parent_year_category_id=moodle_year_category_id,
			)
			frappe.msgprint(
				f"📚 Moodle OK: categoría Academic Term '{self.academic_term}' (id={moodle_term_category_id})",
				indicator="blue",
			)

			# ------------------------------------------------------------------
			# MOODLE: asegurar Course dentro de la categoría hija (fase 2)
			# ------------------------------------------------------------------
			# Validación por idnumber (único): Course.course_name
			course_doc = frappe.get_doc("Course", self.course)
			course_name = (course_doc.course_name or self.course or "").strip()
			course_shortname = (getattr(course_doc, "short_name", None) or "").strip()
			if not course_shortname:
				# Fallback: derivar de la parte izquierda de " - "
				course_shortname = course_name.split(" - ", 1)[0].strip()

			# Título (parte derecha) para el fullname en Moodle
			course_title = course_name.split(" - ", 1)[1].strip() if " - " in course_name else course_name

			term_start_date = frappe.db.get_value("Academic Term", self.academic_term, "term_start_date")
			if not term_start_date:
				frappe.throw("No se encontró term_start_date para el Academic Term seleccionado")
			term_start_date = getdate(term_start_date)
			term_start_date_str = f"{term_start_date.month}/{term_start_date.day}/{str(term_start_date.year)[2:]}"

			term_end_date = frappe.db.get_value("Academic Term", self.academic_term, "term_end_date")
			if not term_end_date:
				frappe.throw("No se encontró term_end_date para el Academic Term seleccionado")
			term_end_date = getdate(term_end_date)

			# Convertir a Unix timestamp para Moodle (sumar 12h para evitar desfase de zona horaria)
			import datetime
			import calendar
			term_start_date_noon = datetime.datetime.combine(term_start_date, datetime.time(12, 0))
			term_end_date_noon = datetime.datetime.combine(term_end_date, datetime.time(12, 0))
			startdate_timestamp = int(calendar.timegm(term_start_date_noon.timetuple()))
			enddate_timestamp = int(calendar.timegm(term_end_date_noon.timetuple()))

			term_category_name = get_term_category_name(str(self.academic_term))
			term_idnumber = str(self.academic_term)

			# Idnumber debe ser único por PERIODO para permitir el mismo curso en distintos términos.
			moodle_course_idnumber = f"{term_category_name}::{course_name}"

			# Formato cliente (core_course_create_courses): fullname = nombre categoría hija, short_name, 1, nombre del curso, idnumber categoría hija, fecha inicio término
			# Ej: "202601,STA 530, 1, RESEARCH 2026 (Spring A) 1/5/26"
			moodle_fullname = f"{term_category_name},{course_shortname}, 1, {course_title} {term_idnumber} {term_start_date_str}"

			# Shortname mismo formato (único por periodo para evitar "nombre corto ya utilizado" en Moodle)
			moodle_course_shortname = moodle_fullname

			moodle_course_id = ensure_course(
				category_id=moodle_term_category_id,
				term_category_name=term_category_name,
				term_idnumber=term_idnumber,
				term_start_date_str=term_start_date_str,
				course_fullname=moodle_fullname,
				course_shortname=moodle_course_shortname,
				course_idnumber=moodle_course_idnumber,
				startdate=startdate_timestamp,
				enddate=enddate_timestamp,
			)
			frappe.msgprint(
				f"🎯 Moodle OK: Course '{course_name}' (id={moodle_course_id})",
				indicator="blue",
			)
		except Exception as e:
			frappe.throw(
				f"❌ Error sincronizando Moodle (categorías/curso): {str(e)}"
			)

		# ✅ VALIDACIÓN 1: Curso obligatorio
		if not self.course or self.course.strip() == "":
			frappe.throw(
				"❌ El curso no está definido en el formulario. "
				"Por favor, selecciona un curso antes de inscribir estudiantes."
			)
		
		# ✅ VALIDACIÓN 2: Verificar que el curso existe
		if not frappe.db.exists("Course", self.course):
			frappe.throw(
				f"❌ El curso '{self.course}' no existe en el sistema. "
				"Por favor, verifica que el curso es válido."
			)
		
		# ✅ VALIDACIÓN 3: Verificar que hay estudiantes
		if not self.students or len(self.students) == 0:
			frappe.throw("❌ No hay estudiantes en la tabla para inscribir.")
		
		frappe.msgprint(
			f"✅ Iniciando inscripción de {len(self.students)} estudiante(s) al curso {self.course}",
			indicator="blue"
		)
		
		count = 0
		errors = 0
		duplicates = 0
		results = []  # Para almacenar resultados
		
		# Asegurar que tenemos fecha, si no, usar hoy
		enroll_date = self.enrollment_date or nowdate()

		for idx, row in enumerate(self.students):
			# Solo procesar los Pendientes o con Error previo
			if row.status == "Enrolled":
				continue

			try:
				# VALIDACIÓN 4: Verificar que el estudiante tiene Program Enrollment válido
				if not row.program_enrollment or row.program_enrollment.strip() == "":
					row.status = "Skipped"
					row.error_log = "Sin Program Enrollment"
					results.append({
						"student": row.student,
						"status": "⏭️ Saltado",
						"message": "Sin Program Enrollment"
					})
					continue
				
				# A. Verificar si ya existe la inscripción (Evitar duplicados)
				exists = frappe.db.exists("Course Enrollment", {
					"student": row.student,
					"course": self.course,
					"program_enrollment": row.program_enrollment,
					"docstatus": 1 # Solo si está validado
				})

				if exists:
					row.status = "Duplicate"
					row.error_log = f"Ya inscrito: {exists}"
					duplicates += 1
					results.append({
						"student": row.student,
						"status": "⚠️ Duplicado",
						"message": exists
					})
					continue

				# A.1 Sincronizar con Moodle: usuario (crear si no existe) y matrícula en el curso
				try:
					from edtools_core.moodle_sync import sync_student_enrollment_to_moodle
					sync_student_enrollment_to_moodle(
						student=row.student,
						academic_year=self.academic_year,
						academic_term=self.academic_term,
						course=self.course,
					)
				except Exception as moodle_err:
					row.status = "Error"
					error_msg = str(moodle_err)[:140]
					row.error_log = error_msg
					errors += 1
					results.append({
						"student": row.student,
						"status": "❌ Error Moodle",
						"message": error_msg
					})
					frappe.log_error(
						f"Moodle sync failed for {row.student}: {moodle_err}",
						"Course Enrollment Tool - Moodle",
					)
					continue

				# B. Crear el documento Course Enrollment
				# Obtener el programa desde el Program Enrollment
				program_enrollment_doc = frappe.get_doc("Program Enrollment", row.program_enrollment)
				program = program_enrollment_doc.program
				
				enrollment = frappe.get_doc({
					"doctype": "Course Enrollment",
					"student": row.student,
					"program": program,
					"course": self.course,
					"program_enrollment": row.program_enrollment,
					"enrollment_date": enroll_date,
					"custom_academic_year": self.academic_year,
					"custom_academic_term": self.academic_term
				})
				
				enrollment.insert(ignore_permissions=True)
				enrollment.submit()
				
				row.status = "Enrolled"
				row.error_log = f"Creado: {enrollment.name}"
				count += 1
				results.append({
					"student": row.student,
					"status": "✅ Inscrito",
					"message": enrollment.name
				})

			except frappe.DuplicateEntryError as e:
				row.status = "Duplicate"
				row.error_log = "Inscripción duplicada"
				duplicates += 1
				results.append({
					"student": row.student,
					"status": "⚠️ Duplicado",
					"message": str(e)[:100]
				})
				
			except frappe.ValidationError as e:
				row.status = "Error"
				error_msg = str(e)[:140]
				row.error_log = error_msg
				errors += 1
				results.append({
					"student": row.student,
					"status": "❌ Error",
					"message": error_msg
				})
				frappe.log_error(f"Validation error enrolling {row.student}: {str(e)}", "Course Enrollment Tool")
				
			except Exception as e:
				row.status = "Error"
				error_msg = str(e)[:140]
				row.error_log = error_msg
				errors += 1
				results.append({
					"student": row.student,
					"status": "❌ Error",
					"message": error_msg
				})
				frappe.log_error(f"Error enrolling {row.student}: {str(e)}", "Course Enrollment Tool")

		# Guardamos el estado final (quién quedó inscrito y quién dio error)
		self.save()
		
		# Construcción de la tabla HTML adaptable al tema
		html_table = f"""
		<table style="width: 100%; border-collapse: collapse; margin-top: 15px; 
		              background-color: var(--bg-color); color: var(--text-color);">
			<thead style="background-color: var(--border-color); border-bottom: 2px solid var(--border-color);">
				<tr>
					<th style="border: 1px solid var(--border-color); padding: 12px; text-align: left; font-weight: 600;">Estudiante</th>
					<th style="border: 1px solid var(--border-color); padding: 12px; text-align: left; font-weight: 600;">Estado</th>
					<th style="border: 1px solid var(--border-color); padding: 12px; text-align: left; font-weight: 600;">Detalle</th>
				</tr>
			</thead>
			<tbody>
		"""
		
		for result in results:
			html_table += f"""
				<tr style="border-bottom: 1px solid var(--border-color);">
					<td style="border: 1px solid var(--border-color); padding: 10px;">{result['student']}</td>
					<td style="border: 1px solid var(--border-color); padding: 10px;">{result['status']}</td>
					<td style="border: 1px solid var(--border-color); padding: 10px;">{result['message']}</td>
				</tr>
			"""
		
		html_table += """
			</tbody>
		</table>
		"""
		
		# Mensaje final con resumen adaptable al tema
		message = f"""
		<h4 style="margin-top: 15px; color: var(--text-color);">📊 RESUMEN FINAL DE INSCRIPCIONES</h4>
		<div style="background-color: var(--fg-color); padding: 15px; border-radius: 5px; margin-bottom: 15px;
		            border: 1px solid var(--border-color); color: var(--text-color);">
			<p><strong>✅ Inscritos correctamente:</strong> {count}/{len(self.students)}</p>
			<p><strong>⚠️ Duplicados encontrados:</strong> {duplicates}</p>
			<p><strong>❌ Errores:</strong> {errors}</p>
		</div>
		{html_table}
		"""
		
		frappe.msgprint(message, indicator="green" if errors == 0 else "orange")
		
		# LIMPIEZA FINAL (Solución Single DocType)
		# ------------------------------------------------------------------
		
		# 1. Vaciar la tabla de estudiantes (lo que ya tenías)
		self.set("students", [])
		self.program = None
		self.academic_year = None
		self.academic_term = None
		self.student_group = None
		self.course = None

		self.flags.ignore_mandatory = True
		self.save(ignore_permissions=True)
		# ------------------------------------------------------------------
		return {
			"count": count,
			"errors": errors,
			"duplicates": duplicates,
			"total": len(self.students),
			"message": message
		}
