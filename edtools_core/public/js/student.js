// Copyright (c) 2024, Andres Salcedo and contributors
// For license information, please see license.txt

/**
 * Custom client-side logic for Student DocType
 *
 * Provides visual indicators and alerts for student status changes
 */

frappe.ui.form.on('Student', {
	refresh: function(frm) {
		// Add visual indicator for student status
		add_status_indicator(frm);

		// Show alert if account is disabled
		show_disabled_alert(frm);
	},

	student_status: function(frm) {
		// Alert when changing to non-Active status
		if (frm.doc.student_status && frm.doc.student_status !== 'Active') {
			frappe.show_alert({
				message: __('Student will not be able to enroll in new programs with status: {0}', [frm.doc.student_status]),
				indicator: 'orange'
			}, 5);
		}
	},

	enabled: function(frm) {
		// Alert when disabling student account
		if (!frm.doc.enabled) {
			frappe.show_alert({
				message: __('Student account is disabled. Student cannot access system or enroll.'),
				indicator: 'red'
			}, 5);
		}
	}
});

/**
 * Add colored status indicator to dashboard based on student status
 */
function add_status_indicator(frm) {
	if (!frm.doc.student_status || frm.doc.student_status === 'Active') {
		return; // No indicator needed for active students
	}

	let color = get_status_color(frm.doc.student_status);
	let message = get_status_message(frm.doc.student_status);

	frm.dashboard.add_comment(
		__(message, [frm.doc.student_status]),
		color,
		true
	);
}

/**
 * Show alert if student account is disabled
 */
function show_disabled_alert(frm) {
	if (!frm.doc.enabled) {
		frm.dashboard.add_comment(
			__('Student account is <strong>disabled</strong>. Cannot access system or enroll in programs.'),
			'red',
			true
		);
	}
}

/**
 * Get color for status indicator
 */
function get_status_color(status) {
	const colors = {
		'LOA': 'yellow',
		'Graduated': 'blue',
		'Suspended': 'red',
		'Withdrawn': 'grey',
		'Transferred': 'grey',
		'Inactive': 'grey'
	};
	return colors[status] || 'orange';
}

/**
 * Get message for status indicator
 */
function get_status_message(status) {
	const messages = {
		'LOA': 'Student is on Leave of Absence ({0}). Cannot enroll in programs.',
		'Graduated': 'Student has graduated ({0}). Cannot enroll in new programs.',
		'Suspended': 'Student is suspended ({0}). Cannot enroll in programs.',
		'Withdrawn': 'Student has withdrawn ({0}). Cannot enroll in programs.',
		'Transferred': 'Student has transferred ({0}). Cannot enroll in programs.',
		'Inactive': 'Student is inactive ({0}). Cannot enroll in programs.'
	};
	return messages[status] || 'Student status is {0}. Cannot enroll in programs.';
}
