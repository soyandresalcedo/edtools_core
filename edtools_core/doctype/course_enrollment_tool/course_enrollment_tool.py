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
		Recorre la tabla y crea los Course Enrollments.
		"""
		count = 0
		errors = 0
		
		# Asegurar que tenemos fecha, si no, usar hoy
		enroll_date = self.enrollment_date or nowdate()

		for row in self.students:
			# Solo procesar los Pendientes o con Error previo
			if row.status == "Enrolled":
				continue

			try:
				# A. Verificar si ya existe la inscripción (Evitar duplicados)
				exists = frappe.db.exists("Course Enrollment", {
					"student": row.student,
					"course": self.course,
					"program_enrollment": row.program_enrollment,
					"docstatus": 1 # Solo si está validado
				})

				if exists:
					row.status = "Enrolled"
					row.error_log = "Already enrolled (Skipped)"
					continue

				# B. Crear el documento Course Enrollment
				enrollment = frappe.get_doc({
					"doctype": "Course Enrollment",
					"student": row.student,
					"program": self.program,
					"course": self.course,
					"program_enrollment": row.program_enrollment,
					"enrollment_date": enroll_date,
					"academic_year": self.academic_year,
					"academic_term": self.academic_term
				})
				
				enrollment.insert(ignore_permissions=True)
				enrollment.submit() # Validar inmediatamente
				
				row.status = "Enrolled"
				row.error_log = f"Created: {enrollment.name}"
				count += 1

			except Exception as e:
				row.status = "Error"
				# Recortamos el error para que quepa en el campo Small Text
				row.error_log = str(e)[:140]
				errors += 1
				frappe.log_error(f"Error enrolling {row.student}", "Course Enrollment Tool")

		# Guardamos el estado final (quién quedó inscrito y quién dio error)
		self.save()
		
		message = f"Proceso finalizado. Inscritos: {count}. Errores: {errors}."
		if errors > 0:
			frappe.msgprint(message, indicator="orange")
		else:
			frappe.msgprint(message, indicator="green")

		return count