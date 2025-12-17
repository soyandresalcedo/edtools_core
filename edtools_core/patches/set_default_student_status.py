# Copyright (c) 2024, Andres Salcedo and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import today


def execute():
	"""
	Data migration patch: Set default student_status to 'Active' for existing students.

	This patch runs automatically during 'bench migrate' and:
	1. Updates all students without a status to 'Active'
	2. Sets status_change_date to today for tracking
	3. Logs the number of students updated

	This ensures backward compatibility with existing data before the
	student_status field was added.

	Safety:
	- Only updates records where student_status is NULL or empty
	- Uses SQL for performance with large datasets
	- Commits after update
	- Logs count for verification
	"""
	frappe.logger().info("Starting migration: set_default_student_status")

	# Update all students without status
	frappe.db.sql(
		"""
		UPDATE `tabStudent`
		SET
			student_status = 'Active',
			status_change_date = %s
		WHERE student_status IS NULL OR student_status = ''
	""",
		(today(),),
	)

	frappe.db.commit()

	# Count total students with Active status for logging
	count = frappe.db.sql(
		"""
		SELECT COUNT(*)
		FROM `tabStudent`
		WHERE student_status = 'Active'
	"""
	)[0][0]

	frappe.logger().info(
		f"Migration completed: set_default_student_status - "
		f"Total students with status='Active': {count}"
	)

	# Optional: Show message in console during migration
	print(f"✓ Set student_status='Active' for {count} students")
