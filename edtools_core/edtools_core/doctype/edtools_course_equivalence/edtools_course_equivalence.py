# Copyright (c) 2026, EdTools and contributors

import frappe
from frappe import _
from frappe.model.document import Document


class EdToolsCourseEquivalence(Document):
	"""Equivalencia interna autorizada por la dirección académica.

	Si el estudiante tiene nota en `equivalent_course`, el `course` del pensum de `program`
	se muestra como aprobado en el portal (pestaña Program), con la nota del equivalente.
	No cambia ni borra códigos de cursos ni notas.
	"""

	def validate(self):
		if self.course == self.equivalent_course:
			frappe.throw(_("El curso del plan y el curso equivalente deben ser distintos."))

		in_plan = frappe.db.exists(
			"Program Course", {"parent": self.program, "parenttype": "Program", "course": self.course}
		)
		if not in_plan:
			frappe.throw(
				_("El curso {0} no está en el pensum del programa {1}.").format(
					frappe.bold(self.course), frappe.bold(self.program)
				)
			)

		filters = {
			"program": self.program,
			"course": self.course,
			"equivalent_course": self.equivalent_course,
			"name": ("!=", self.name),
		}
		for other in frappe.get_all("EdTools Course Equivalence", filters=filters, fields=["name", "student"]):
			if (other.student or "") == (self.student or ""):
				frappe.throw(
					_("Ya existe esta equivalencia: {0}.").format(
						frappe.utils.get_link_to_form("EdTools Course Equivalence", other.name)
					)
				)
