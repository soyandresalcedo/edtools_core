# Copyright (c) EdTools
# Override de enroll_student con provisioning Azure @cucusa.org.
# Modo sandbox: simula Azure, crea Student/User/Program Enrollment reales.

from __future__ import annotations

import string
from random import choice

import frappe
from frappe.model.mapper import get_mapped_doc

from edtools_core.azure_provisioning import (
	assign_microsoft_license,
	create_azure_user,
	generate_cucusa_email,
	is_provisioning_enabled,
)


def _generate_temp_password(length: int = 12) -> str:
	"""Genera contraseña que cumple requisitos típicos: mayúscula, minúscula, número, símbolo."""
	symbols = "!@#$%&*"
	chars = []
	chars.append(choice(string.ascii_uppercase))
	chars.append(choice(string.ascii_lowercase))
	chars.append(choice(string.digits))
	chars.append(choice(symbols))
	for _ in range(length - 4):
		chars.append(choice(string.ascii_letters + string.digits + symbols))
	from random import shuffle
	shuffle(chars)
	return "".join(chars)


def enroll_student_with_azure_provisioning(source_name: str):
	"""
	Reemplaza education.education.api.enroll_student cuando Azure provisioning está habilitado.
	Flujo: generar @cucusa.org -> Azure (o sandbox) -> Student -> User -> Program Enrollment -> email credenciales.
	"""
	# Si no está habilitado, llamar al original de Education
	if not is_provisioning_enabled():
		from education.education.api import enroll_student as _edu_enroll
		return _edu_enroll(source_name)

	frappe.publish_realtime("enroll_student_progress", {"progress": [1, 6]}, user=frappe.session.user)

	applicant = frappe.get_doc("Student Applicant", source_name)
	# Correo personal para enviar credenciales
	personal_email = (applicant.get("personal_email") or applicant.student_email_id or "").strip()
	if not personal_email:
		frappe.throw(
			"Para provisioning con Azure se requiere Correo personal (personal_email) o "
			"Dirección de correo electrónico del estudiante en el Student Applicant."
		)

	# Generar email institucional
	institutional_email = generate_cucusa_email(
		applicant.first_name,
		applicant.middle_name,
		applicant.last_name,
	)
	password = _generate_temp_password()

	frappe.publish_realtime("enroll_student_progress", {"progress": [2, 6]}, user=frappe.session.user)

	# Azure (o sandbox)
	user_id = create_azure_user(
		institutional_email,
		password,
		applicant.first_name or "",
		applicant.last_name or "",
		display_name=applicant.title or f"{applicant.first_name} {applicant.last_name}".strip(),
	)
	assign_microsoft_license(user_id)

	frappe.publish_realtime("enroll_student_progress", {"progress": [3, 6]}, user=frappe.session.user)

	# Crear User en Frappe con @cucusa.org (evitar send_welcome_email)
	# Manejar DuplicateEntryError: User puede existir por intento previo o condición de carrera
	from frappe.utils.password import update_password

	def _ensure_user():
		if frappe.db.exists("User", institutional_email):
			return
		try:
			user = frappe.get_doc({
				"doctype": "User",
				"email": institutional_email,
				"first_name": applicant.first_name,
				"last_name": applicant.last_name,
				"user_type": "Website User",
				"send_welcome_email": 0,
			})
			user.add_roles("Student")
			user.insert(ignore_permissions=True)
		except frappe.DuplicateEntryError:
			frappe.db.rollback()

	_ensure_user()
	frappe.db.commit()
	update_password(institutional_email, password, logout_all_sessions=False)
	frappe.db.commit()

	# Verificar User: existe en DB (duplicate key) pero get_doc puede fallar si está "deleted" u otro estado.
	# Usar SQL directo para evitar la paradoja User-existe vs Frappe-no-lo-encuentra.
	frappe.clear_cache(doctype="User")
	user_exists_raw = frappe.db.sql(
		"SELECT 1 FROM `tabUser` WHERE name = %s LIMIT 1",
		(institutional_email,),
	)
	user_exists_in_db = bool(user_exists_raw)
	if not user_exists_in_db:
		frappe.throw(
			f"Usuario {institutional_email} no pudo ser creado. "
			"Verifique que no exista un User huérfano en la base de datos."
		)
	# Si existe en DB pero Frappe no lo carga bien, ignorar validación de links al guardar Student
	skip_link_validation = not frappe.db.exists("User", institutional_email)

	# Actualizar Applicant para que el mapper use @cucusa.org
	frappe.db.set_value(
		"Student Applicant", source_name,
		{"student_email_id": institutional_email, "institutional_email": institutional_email},
	)
	frappe.db.commit()

	frappe.publish_realtime("enroll_student_progress", {"progress": [4, 6]}, user=frappe.session.user)

	# Crear Student o reusar si ya existe (intento previo)
	existing_student = frappe.db.exists("Student", {"student_applicant": source_name})
	if existing_student:
		student = frappe.get_doc("Student", existing_student)
		student.user = institutional_email
		student.student_email_id = institutional_email
		if skip_link_validation:
			student.flags.ignore_links = True
		student.save()
	else:
		student = get_mapped_doc(
			"Student Applicant",
			source_name,
			{
				"Student Applicant": {
					"doctype": "Student",
					"field_map": {"name": "student_applicant"},
				}
			},
			ignore_permissions=True,
		)
		student.user = institutional_email
		student.student_email_id = institutional_email
		if skip_link_validation:
			student.flags.ignore_links = True
		student.save()

	student_applicant_data = frappe.db.get_value(
		"Student Applicant", source_name,
		["student_category", "program", "academic_year"],
		as_dict=True,
	)
	program_enrollment = frappe.new_doc("Program Enrollment")
	program_enrollment.student = student.name
	program_enrollment.student_category = student_applicant_data.student_category
	program_enrollment.student_name = student.student_name
	program_enrollment.program = student_applicant_data.program
	program_enrollment.academic_year = student_applicant_data.academic_year
	program_enrollment.save()

	frappe.publish_realtime("enroll_student_progress", {"progress": [5, 6]}, user=frappe.session.user)

	# Enviar credenciales al correo personal
	_send_credentials_email(
		recipient=personal_email,
		institutional_email=institutional_email,
		password=password,
		student_name=student.student_name or applicant.title,
	)

	frappe.publish_realtime("enroll_student_progress", {"progress": [6, 6]}, user=frappe.session.user)

	return program_enrollment


def _send_credentials_email(
	recipient: str,
	institutional_email: str,
	password: str,
	student_name: str,
) -> None:
	"""Envía email con credenciales al correo personal."""
	site_url = frappe.utils.get_url()
	portal_url = f"{site_url}/student-portal" if not site_url.endswith("/") else f"{site_url.rstrip('/')}/student-portal"

	subject = "Bienvenido - Tus credenciales para el Portal del Estudiante"
	content = f"""
<p>Hola {student_name},</p>

<p>Tu cuenta institucional ha sido creada. Puedes acceder al Portal del Estudiante con las siguientes credenciales:</p>

<ul>
<li><strong>Correo institucional:</strong> {institutional_email}</li>
<li><strong>Contraseña temporal:</strong> {password}</li>
</ul>

<p><a href="{portal_url}">{portal_url}</a></p>

<p><strong>Importante:</strong> Te recomendamos cambiar tu contraseña en el primer inicio de sesión por razones de seguridad.</p>

<p>Saludos,<br>
Equipo CUC University</p>
"""
	try:
		frappe.sendmail(
			recipients=[recipient],
			subject=subject,
			content=content,
		)
	except Exception as e:
		frappe.log_error(
			title="Error enviando credenciales al estudiante",
			message=f"Recipient: {recipient}\nError: {e}\n{frappe.get_traceback()}",
		)
