# Copyright (c) EdTools Core
# License: MIT

import frappe
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()

	if filters.get("student_group"):
		result = get_data_by_student_group(filters.student_group)
	else:
		result = get_data_all_fees()

	return columns, result


def get_columns():
	return [
		{"fieldname": "student", "label": "Student", "fieldtype": "Link", "options": "Student", "width": 200},
		{"fieldname": "student_name", "label": "Student Name", "fieldtype": "Data", "width": 200},
		{"fieldname": "paid_amount", "label": "Paid Amount", "fieldtype": "Currency", "width": 150},
		{"fieldname": "outstanding_amount", "label": "Outstanding Amount", "fieldtype": "Currency", "width": 150},
		{"fieldname": "grand_total", "label": "Grand Total", "fieldtype": "Currency", "width": 150},
	]


def get_data_all_fees():
	"""Same as current Query Report: students with fees, aggregated by student (PostgreSQL-compatible)."""
	query = """
		SELECT
			student,
			student_name,
			SUM(grand_total) - SUM(outstanding_amount) AS paid_amount,
			SUM(outstanding_amount) AS outstanding_amount,
			SUM(grand_total) AS grand_total
		FROM "tabFees"
		WHERE docstatus = 1
		GROUP BY student, student_name
	"""
	return frappe.db.sql(query, as_dict=True)


def get_data_by_student_group(student_group):
	"""All students in the group; fee totals from Fees (docstatus=1), or 0 if no fees."""
	students = frappe.get_all(
		"Student Group Student",
		filters={"parent": student_group},
		fields=["student", "student_name"],
		order_by="group_roll_number",
	)
	if not students:
		return []

	# Aggregate fees by student (docstatus=1)
	student_ids = [s["student"] for s in students]
	placeholders = ", ".join(["%s"] * len(student_ids))
	query = """
		SELECT
			student,
			SUM(grand_total) - SUM(outstanding_amount) AS paid_amount,
			SUM(outstanding_amount) AS outstanding_amount,
			SUM(grand_total) AS grand_total
		FROM "tabFees"
		WHERE docstatus = 1 AND student IN ({0})
		GROUP BY student
	""".format(
		placeholders
	)
	rows = frappe.db.sql(query, tuple(student_ids), as_dict=True)
	fee_by_student = {r["student"]: r for r in rows}

	result = []
	for s in students:
		student = s["student"]
		student_name = s.get("student_name") or ""
		fee = fee_by_student.get(student)
		if fee:
			result.append({
				"student": student,
				"student_name": student_name,
				"paid_amount": flt(fee.get("paid_amount")),
				"outstanding_amount": flt(fee.get("outstanding_amount")),
				"grand_total": flt(fee.get("grand_total")),
			})
		else:
			result.append({
				"student": student,
				"student_name": student_name,
				"paid_amount": 0,
				"outstanding_amount": 0,
				"grand_total": 0,
			})
	return result
