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


class Student(EducationStudent):
    def validate_user(self):
        # Durante Azure provisioning, el User @cucusa.org ya fue creado en enrollment.py.
        # Evitar DuplicateEntryError si validate_user intenta crearlo (exists puede fallar).
        if getattr(frappe.flags, "azure_provisioning_enroll", False) and self.student_email_id and self.student_email_id.endswith("@cucusa.org"):
            self.user = self.student_email_id
            return
        super().validate_user()
