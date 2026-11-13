import frappe


def execute():
	"""Equivalencias creadas con el campo único `student`: pasarlo a la tabla `students`."""
	dt = "EdTools Course Equivalence"
	if not frappe.db.table_exists(dt) or not frappe.db.has_column(dt, "student"):
		return
	for row in frappe.db.sql(
		f'select name, student from `tab{dt}` where coalesce(student, \'\') != \'\'', as_dict=True
	):
		doc = frappe.get_doc(dt, row.name)
		if not any(r.student == row.student for r in doc.students):
			doc.append("students", {"student": row.student})
		doc.flags.ignore_permissions = True
		doc.save()
