# Copyright (c) EdTools
# Override de enroll_student con provisioning Azure @cucusa.org.
# Education es la única que crea Student y User en Frappe; aquí solo Azure + contraseña + correo de credenciales.

from __future__ import annotations

import string
from random import choice

import frappe
from frappe import _

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
	Flujo Azure: generar @cucusa.org → crear en Azure (o reusar) → asignar licencia →
	actualizar Applicant → Education enroll_student (crea Student + User, sin welcome) →
	update_password → enviar credenciales al correo personal.
	No creamos User en Frappe aquí; solo Education (Student.validate_user).
	"""
	if not is_provisioning_enabled():
		from education.education.api import enroll_student as _edu_enroll
		return _edu_enroll(source_name)

	print(f"[Azure] Iniciando provisioning para applicant {source_name}", flush=True)
	frappe.publish_realtime("enroll_student_progress", {"progress": [1, 6]}, user=frappe.session.user)

	applicant = frappe.get_doc("Student Applicant", source_name)
	personal_email = (applicant.get("personal_email") or applicant.student_email_id or "").strip()
	if not personal_email:
		frappe.throw(
			_("Para provisioning con Azure se requiere Correo personal (personal_email) o "
			  "Dirección de correo electrónico del estudiante en el Student Applicant.")
		)

	institutional_email = generate_cucusa_email(
		applicant.first_name,
		applicant.middle_name,
		applicant.last_name,
	)
	password = _generate_temp_password()

	frappe.publish_realtime("enroll_student_progress", {"progress": [2, 6]}, user=frappe.session.user)

	# Azure: crear usuario (o obtener id si ya existe) y asignar licencia
	user_id = create_azure_user(
		institutional_email,
		password,
		applicant.first_name or "",
		applicant.last_name or "",
		display_name=applicant.title or f"{applicant.first_name} {applicant.last_name}".strip(),
	)
	assign_microsoft_license(user_id)

	frappe.publish_realtime("enroll_student_progress", {"progress": [3, 6]}, user=frappe.session.user)

	# Actualizar Applicant para que el mapper copie @cucusa.org al Student
	frappe.db.set_value(
		"Student Applicant", source_name,
		{"student_email_id": institutional_email, "institutional_email": institutional_email},
	)
	frappe.db.commit()

	frappe.flags.azure_provisioning_enroll = True
	try:
		frappe.publish_realtime("enroll_student_progress", {"progress": [4, 6]}, user=frappe.session.user)

		# Education crea Student + User (validate_user crea User con send_welcome_email=0, sin enviar welcome)
		from education.education.api import enroll_student as _edu_enroll
		program_enrollment = _edu_enroll(source_name)

		frappe.publish_realtime("enroll_student_progress", {"progress": [5, 6]}, user=frappe.session.user)

		# Contraseña en Frappe (misma que en Azure) y correo de credenciales al personal
		from frappe.utils.password import update_password
		update_password(institutional_email, password, logout_all_sessions=False)
		frappe.db.commit()

		_send_credentials_email(
			recipient=personal_email,
			institutional_email=institutional_email,
			password=password,
			student_name=program_enrollment.student_name or applicant.title,
		)

		frappe.publish_realtime("enroll_student_progress", {"progress": [6, 6]}, user=frappe.session.user)
		return program_enrollment
	finally:
		frappe.flags.azure_provisioning_enroll = False


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

<p>Si no puedes acceder de inmediato, espera un momento e inténtalo de nuevo, o usa "¿Olvidaste tu contraseña?" con tu correo institucional.</p>

<p>Saludos,<br>
Equipo CUC University</p>
"""
	try:
		# print() para que aparezca en Railway Deploy Logs al hacer "Inscribir estudiantes"
		print(f"[Azure] Enviando correo de credenciales a {recipient}", flush=True)
		frappe.logger().info(f"[Azure] Enviando correo de credenciales a {recipient}")
		frappe.sendmail(
			recipients=[recipient],
			subject=subject,
			content=content,
			delayed=False,  # Enviar ya: en Railway el scheduler puede no procesar la cola
		)
		print(f"[Azure] Correo de credenciales enviado a {recipient}", flush=True)
		frappe.logger().info(f"[Azure] Correo de credenciales enviado a {recipient}")
	except Exception as e:
		frappe.log_error(
			title="Error enviando credenciales al estudiante",
			message=f"Recipient: {recipient}\nError: {e}\n{frappe.get_traceback()}",
		)
		raise
