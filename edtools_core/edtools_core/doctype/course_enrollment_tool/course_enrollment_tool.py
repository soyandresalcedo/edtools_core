# Copyright (c) 2026, EdTools and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, nowdate

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
		
		# 4. Guardamos el documento Single para que la tabla persista en BD
		self.save()
		
		return students_found

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
		
		return {
			"count": count,
			"errors": errors,
			"duplicates": duplicates,
			"total": len(self.students),
			"message": message
		}