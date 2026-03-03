# Copyright (c) 2026, EdTools and contributors
# Extiende Student Group de Education: Año académico, programa, término, etc. opcionales.
# Permite grupos flexibles (ej. por año sin programa, o sin año para grupos manuales).

from __future__ import annotations

import frappe
from frappe import _

try:
    from education.education.education.doctype.student_group.student_group import (
        StudentGroup as EducationStudentGroup,
    )
except ImportError:
    from education.education.doctype.student_group.student_group import (
        StudentGroup as EducationStudentGroup,
    )


def get_program_enrollment(
    academic_year=None,
    academic_term=None,
    program=None,
    batch=None,
    student_category=None,
    course=None,
):
    """
    Obtiene inscripciones de programa. academic_year es opcional (EdTools).
    Si academic_year es None, devuelve inscripciones de cualquier año.
    """
    condition1 = " "
    condition2 = " "
    params = {}
    if academic_year:
        condition1 += " and pe.academic_year = %(academic_year)s"
        params["academic_year"] = academic_year
    if academic_term:
        condition1 += " and pe.academic_term = %(academic_term)s"
        params["academic_term"] = academic_term
    if program:
        condition1 += " and pe.program = %(program)s"
        params["program"] = program
    if batch:
        condition1 += " and pe.student_batch_name = %(batch)s"
        params["batch"] = batch
    if student_category:
        condition1 += " and pe.student_category = %(student_category)s"
        params["student_category"] = student_category
    if course:
        condition1 += " and pe.name = pec.parent and pec.course = %(course)s"
        condition2 = ", `tabProgram Enrollment Course` pec"
        params["course"] = course
    return frappe.db.sql(
        """
        select pe.student, pe.student_name
        from `tabProgram Enrollment` pe {condition2}
        where pe.docstatus = 1 {condition1}
        order by pe.student_name asc
        """.format(condition1=condition1, condition2=condition2),
        params,
        as_dict=1,
    )


@frappe.whitelist()
def get_students(
    academic_year=None,
    group_based_on=None,
    academic_term=None,
    program=None,
    batch=None,
    student_category=None,
    course=None,
):
    """Get Students con academic_year opcional (EdTools)."""
    enrolled_students = get_program_enrollment(
        academic_year, academic_term, program, batch, student_category, course
    )
    if enrolled_students:
        student_list = []
        for s in enrolled_students:
            if frappe.db.get_value("Student", s.student, "enabled"):
                s.update({"active": 1})
            else:
                s.update({"active": 0})
            student_list.append(s)
        return student_list
    frappe.msgprint(_("No students found"))
    return []


class StudentGroup(EducationStudentGroup):
    """
    Override de Student Group: validación flexible.
    Año académico opcional; solo Course requiere course cuando group_based_on=Course.
    """

    def validate_mandatory_fields(self):
        if self.group_based_on == "Course" and not self.course:
            frappe.throw(_("Please select Course"))
        # Año académico, programa, término, lote, etc. son opcionales

    def validate_students(self):
        """Usa get_program_enrollment con academic_year opcional."""
        program_enrollment = get_program_enrollment(
            self.academic_year,
            self.academic_term,
            self.program,
            self.batch,
            self.student_category,
            self.course,
        )
        students = [d.student for d in program_enrollment] if program_enrollment else []
        for d in self.students:
            if (
                not frappe.db.get_value("Student", d.student, "enabled")
                and d.active
                and not self.disabled
            ):
                frappe.throw(
                    _("{0} - {1} is inactive student").format(d.group_roll_number, d.student_name)
                )
            if (
                (self.group_based_on == "Batch")
                and frappe.utils.cint(frappe.defaults.get_defaults().validate_batch)
                and d.student not in students
            ):
                frappe.throw(
                    _("{0} - {1} is not enrolled in the Batch {2}").format(
                        d.group_roll_number, d.student_name, self.batch
                    )
                )
            if (
                (self.group_based_on == "Course")
                and frappe.utils.cint(frappe.defaults.get_defaults().validate_course)
                and d.student not in students
            ):
                frappe.throw(
                    _("{0} - {1} is not enrolled in the Course {2}").format(
                        d.group_roll_number, d.student_name, self.course
                    )
                )
