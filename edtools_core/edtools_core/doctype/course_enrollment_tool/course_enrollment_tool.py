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
		
		# Asegurar que tenemos fecha, si no, usar hoy
		enroll_date = self.enrollment_date or nowdate()

		for idx, row in enumerate(self.students):
			frappe.msgprint(f"\n  [{idx + 1}/{len(self.students)}] Procesando: {row.student}")
			
			# Solo procesar los Pendientes o con Error previo
			if row.status == "Enrolled":
				frappe.msgprint(f"    ⏭️  Ya está inscrito, saltando...")
				continue

			try:
				# VALIDACIÓN 4: Verificar que el estudiante tiene Program Enrollment válido
				if not row.program_enrollment or row.program_enrollment.strip() == "":
					row.status = "Skipped"
					row.error_log = "Sin Program Enrollment"
					frappe.msgprint(f"    ⏭️  Saltado: sin Program Enrollment")
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
					frappe.msgprint(f"    ⚠️  Duplicado: {exists}")
					continue

				# B. Crear el documento Course Enrollment
				frappe.msgprint(
					f"    ↳ Creando Course Enrollment:\n"
					f"      • Curso: {self.course}\n"
					f"      • Program Enrollment: {row.program_enrollment}"
				)
				
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
				row.error_log = f"Creado: {enrollment.name}"
				count += 1
				frappe.msgprint(f"    ✅ Inscrito exitosamente: {enrollment.name}")

			except frappe.DuplicateEntryError as e:
				row.status = "Duplicate"
				row.error_log = "Inscripción duplicada"
				duplicates += 1
				frappe.msgprint(f"    ⚠️  Duplicado (excepción): {str(e)[:100]}")
				
			except frappe.ValidationError as e:
				row.status = "Error"
				error_msg = str(e)[:140]
				row.error_log = error_msg
				errors += 1
				frappe.msgprint(f"    ❌ Error de validación: {error_msg}")
				frappe.log_error(f"Validation error enrolling {row.student}: {str(e)}", "Course Enrollment Tool")
				
			except Exception as e:
				row.status = "Error"
				error_msg = str(e)[:140]
				row.error_log = error_msg
				errors += 1
				frappe.msgprint(f"    ❌ Error: {error_msg}")
				frappe.log_error(f"Error enrolling {row.student}: {str(e)}", "Course Enrollment Tool")

		# Guardamos el estado final (quién quedó inscrito y quién dio error)
		self.save()
		
		# Construcción del mensaje final
		message = (
			f"\n{'='*60}\n"
			f"📊 RESUMEN FINAL DE INSCRIPCIONES\n"
			f"{'='*60}\n"
			f"✅ Inscritos correctamente: {count}\n"
			f"⚠️  Duplicados encontrados: {duplicates}\n"
			f"❌ Errores: {errors}\n"
			f"📝 Total procesados: {len(self.students)}\n"
			f"{'='*60}"
		)
		
		if errors > 0:
			frappe.msgprint(message, indicator="orange")
		else:
			frappe.msgprint(message, indicator="green")

		return {
			"count": count,
			"errors": errors,
			"duplicates": duplicates,
			"total": len(self.students),
			"message": message
		}