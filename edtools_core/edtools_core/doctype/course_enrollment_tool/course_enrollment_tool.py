# Copyright (c) 2026, EdTools and contributors
# For license information, please see license.txt

import frappe
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
	def check_student_group_has_instructors(self, student_group=None):
		"""
		Retorna si el Student Group tiene al menos un instructor.
		Usado en el cliente para mostrar aviso de confirmación al inscribir.
		"""
		sg = student_group or getattr(self, "student_group", None)
		if not sg:
			return {"has_instructors": False, "count": 0}
		group = frappe.get_doc("Student Group", sg)
		instructors = group.get("instructors") or []
		count = sum(1 for r in instructors if r.get("instructor"))
		return {"has_instructors": count > 0, "count": count}

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
			from edtools_core.course_enrollment_moodle import (
				enroll_moodle_instructors_from_student_group,
				prepare_moodle_course_for_enrollment_tool,
			)

			moodle_course_id = prepare_moodle_course_for_enrollment_tool(
				str(self.academic_year),
				str(self.academic_term),
				self.course,
				show_progress_msgs=True,
			)
		except Exception as e:
			frappe.throw(
				f"❌ Error sincronizando Moodle (categorías/curso): {str(e)}"
			)

		already_enrolled_instructors, enrolled_ids = enroll_moodle_instructors_from_student_group(
			self.student_group,
			moodle_course_id,
			log_context="Course Enrollment Tool",
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
		already_enrolled_students = []  # Usuarios que ya estaban matriculados en Moodle

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
				
				# A. Verificar si ya existe la inscripción en el MISMO periodo (evitar duplicados)
				# Permite el mismo curso en distintos periodos (como en Moodle): duplicado solo si
				# mismo estudiante + mismo curso + mismo academic_term.
				filters = {
					"student": row.student,
					"course": self.course,
					"docstatus": 1,
				}
				ce_meta = frappe.get_meta("Course Enrollment")
				if self.academic_term and ce_meta.has_field("custom_academic_term"):
					filters["custom_academic_term"] = self.academic_term
				else:
					filters["program_enrollment"] = row.program_enrollment
				exists = frappe.db.exists("Course Enrollment", filters)

				if exists:
					row.status = "Duplicate"
					row.error_log = f"Ya inscrito en este periodo: {exists}"
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
					sync_result = sync_student_enrollment_to_moodle(
						student=row.student,
						academic_year=self.academic_year,
						academic_term=self.academic_term,
						course=self.course,
					)
					if sync_result.get("already_enrolled"):
						already_enrolled_students.append(
							getattr(row, "student_full_name", None) or row.student
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
						"CET Moodle Sync",
						f"Moodle sync failed for {row.student}: {moodle_err}",
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
				frappe.log_error(
					"CET Enroll Error",
					f"Validation error enrolling {row.student}: {str(e)}",
				)
				
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
				frappe.log_error(
					"CET Enroll Error",
					f"Error enrolling {row.student}: {str(e)}",
				)

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

		# Bloque: usuarios que ya estaban matriculados en Moodle
		already_block = ""
		if already_enrolled_instructors or already_enrolled_students:
			lines = []
			if already_enrolled_instructors:
				lines.append("<strong>Instructores:</strong> " + ", ".join(already_enrolled_instructors))
			if already_enrolled_students:
				lines.append("<strong>Estudiantes:</strong> " + ", ".join(already_enrolled_students))
			already_block = f"""
		<div style="background-color: var(--fg-color); padding: 12px; border-radius: 5px; margin-bottom: 15px;
		            border: 1px solid var(--border-color); color: var(--text-color);">
			<p><strong>ℹ️ Ya estaban matriculados en Moodle:</strong></p>
			<p>{'<br>'.join(lines)}</p>
		</div>
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
		{already_block}
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
