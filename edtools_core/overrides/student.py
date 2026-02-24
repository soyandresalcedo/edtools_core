# Copyright (c) EdTools
# Override de Student: durante Azure provisioning, no crear User duplicado.
# El User @cucusa.org ya se crea en enrollment.py; validate_user podría intentar crearlo de nuevo
# si frappe.db.exists falla por replicación/caché.

from __future__ import annotations

try:
    from education.education.education.doctype.student.student import Student as EducationStudent
except ImportError:
    from education.education.doctype.student.student import Student as EducationStudent

import frappe
from frappe import _

from edtools_core.azure_provisioning import generate_cucusa_email


class Student(EducationStudent):
    def validate_user(self):
        # Asegurar email desde Applicant si falta (evita AttributeError en User.autoname)
        if self.student_applicant and not self.student_email_id:
            email = frappe.db.get_value(
                "Student Applicant", self.student_applicant, "student_email_id"
            )
            if email:
                self.student_email_id = email
            else:
                # Generar correo institucional nombre.apellido1.apellido2@cucusa.org
                applicant = frappe.get_doc("Student Applicant", self.student_applicant)
                self.student_email_id = generate_cucusa_email(
                    applicant.first_name,
                    applicant.middle_name,
                    applicant.last_name,
                )
        # Dejar el Applicant con el mismo student_email_id (institucional) para que el formulario lo muestre
        if self.student_applicant and self.student_email_id:
            frappe.db.set_value(
                "Student Applicant",
                self.student_applicant,
                "student_email_id",
                self.student_email_id,
            )
        # Durante Azure provisioning, el User @cucusa.org ya fue creado en enrollment.py.
        if getattr(frappe.flags, "azure_provisioning_enroll", False) and self.student_email_id and self.student_email_id.endswith("@cucusa.org"):
            self.user = self.student_email_id
            return
        # User ya existe: solo enlazar
        if frappe.db.exists("User", self.student_email_id):
            self.user = self.student_email_id
            return
        # Omitir creación de User si está deshabilitada en Education Settings
        if frappe.db.get_single_value("Education Settings", "user_creation_skip"):
            super().validate_user()
            return
        # Obtener correo personal para enviar bienvenida ahí (no al @cucusa.org)
        personal_email = None
        if self.student_applicant:
            personal_email = (
                frappe.db.get_value("Student Applicant", self.student_applicant, "personal_email")
                or ""
            )
            if isinstance(personal_email, str):
                personal_email = personal_email.strip() or None
        if personal_email:
            # Crear User con correo institucional pero enviar bienvenida al correo personal
            student_user = frappe.get_doc(
                {
                    "doctype": "User",
                    "first_name": self.first_name,
                    "last_name": self.last_name,
                    "email": self.student_email_id,
                    "gender": self.gender,
                    "send_welcome_email": 0,
                    "user_type": "Website User",
                }
            )
            student_user.add_roles("Student")
            student_user.save(ignore_permissions=True)
            self.user = student_user.name
            # Enviar correo de bienvenida al correo personal (link de reset de contraseña)
            student_user.email = personal_email
            student_user.send_welcome_mail_to_user()
            return
        super().validate_user()
