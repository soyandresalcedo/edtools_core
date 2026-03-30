// Copyright (c) 2026, EdTools and contributors
// For license information, please see license.txt

frappe.ui.form.on('Student Course Coverage', {

	setup(frm) {
		frm.set_query('academic_term', function () {
			if (!frm.doc.academic_year) return { filters: [] };
			return { filters: { academic_year: frm.doc.academic_year } };
		});

		frm.set_query('student_group', function () {
			let filters = {};
			if (frm.doc.academic_year) filters.academic_year = frm.doc.academic_year;
			if (frm.doc.program) filters.program = frm.doc.program;
			return { filters };
		});
	},

	refresh(frm) {
		frm.disable_save();
		frm.page.clear_user_actions();

		frm.add_custom_button(__('Generate'), function () {
			frm.trigger('generate_coverage');
		}).addClass('btn-primary');

		frm.add_custom_button(__('Clear'), function () {
			frm.get_field('results_html').$wrapper.html('');
		});
	},

	academic_year(frm) {
		frm.set_value('academic_term', '');
	},

	selection_mode(frm) {
		frm.set_value('student', '');
		frm.set_value('student_group', '');
		frm.clear_table('students');
		frm.refresh_fields();
		frm.get_field('results_html').$wrapper.html('');
	},

	generate_coverage(frm) {
		if (!frm.doc.academic_year || !frm.doc.academic_term) {
			frappe.msgprint(__('Please select Academic Year and Academic Term.'));
			return;
		}

		let mode = frm.doc.selection_mode;
		if (mode === 'Single Student' && !frm.doc.student) {
			frappe.msgprint(__('Please select a Student.'));
			return;
		}
		if (mode === 'Student Group' && !frm.doc.student_group) {
			frappe.msgprint(__('Please select a Student Group.'));
			return;
		}
		if (mode === 'Manual List' && (!frm.doc.students || frm.doc.students.length === 0)) {
			frappe.msgprint(__('Please add at least one student to the table.'));
			return;
		}

		frm.call({
			method: 'get_coverage',
			doc: frm.doc,
			freeze: true,
			freeze_message: __('Analyzing course coverage…'),
			callback(r) {
				if (r.message) {
					render_coverage(frm, r.message);
				}
			}
		});
	}
});


/* ── Rendering ────────────────────────────────────────────────── */

function render_coverage(frm, data) {
	const $wrapper = frm.get_field('results_html').$wrapper;
	$wrapper.empty();

	const students = data.students || {};
	const student_ids = Object.keys(students);
	if (!student_ids.length) {
		$wrapper.html('<p class="text-muted">' + __('No results.') + '</p>');
		return;
	}

	let html = `<div class="coverage-container">`;
	html += render_legend();

	student_ids.forEach(function (sid, idx) {
		const s = students[sid];
		html += render_student_block(sid, s, student_ids.length > 1, idx);
	});

	html += `</div>`;
	html += render_styles();
	$wrapper.html(html);

	// Accordion toggle
	$wrapper.find('.cov-header').on('click', function () {
		const $body = $(this).next('.cov-body');
		$body.slideToggle(200);
		$(this).find('.cov-chevron').toggleClass('rotated');
	});
}

function render_legend() {
	return `
	<div class="cov-legend" style="margin-bottom:16px;display:flex;gap:16px;flex-wrap:wrap;align-items:center;">
		<span class="cov-badge cov-current">${__('Current Period')}</span>
		<span class="cov-badge cov-history">${__('History')}</span>
		<span class="cov-badge cov-missing">${__('Not Enrolled')}</span>
		<span style="color:var(--text-muted);font-size:12px;margin-left:auto;">
			<strong>M</strong> = ${__('Mandatory')}
		</span>
	</div>`;
}

function render_student_block(sid, s, collapsible, idx) {
	const kpis = s.kpis || {};
	const warning = s.warning || '';
	const open = idx === 0 ? '' : 'style="display:none"';

	let header_class = collapsible ? 'cov-header cov-clickable' : 'cov-header';
	let chevron = collapsible
		? `<span class="cov-chevron ${idx === 0 ? 'rotated' : ''}">&#9654;</span> `
		: '';

	let html = `<div class="cov-student" data-student="${frappe.utils.escape_html(sid)}">`;

	// Header
	html += `<div class="${header_class}">`;
	html += `${chevron}<strong>${frappe.utils.escape_html(s.student_name || sid)}</strong>`;
	html += `<span class="text-muted" style="margin-left:8px;">${frappe.utils.escape_html(sid)}</span>`;
	html += `</div>`;

	// Body
	html += `<div class="cov-body" ${open}>`;

	if (warning) {
		html += `<div class="alert alert-warning" style="margin:8px 0;">${frappe.utils.escape_html(warning)}</div>`;
		html += `</div></div>`;
		return html;
	}

	// KPIs
	html += `<div class="cov-kpis">`;
	html += kpi_card(__('Plan Total'), kpis.total, 'var(--text-color)');
	html += kpi_card(__('Current Period'), kpis.current, 'var(--green-600)');
	html += kpi_card(__('History'), kpis.history, 'var(--gray-600)');
	html += kpi_card(__('Not Enrolled'), kpis.missing, 'var(--red-600)');
	html += kpi_card(__('Not Enrolled (M)'), kpis.missing_mandatory, 'var(--orange-600)');
	html += `</div>`;

	// Table
	const courses = s.courses || [];
	if (courses.length) {
		html += `<table class="table table-bordered cov-table">
			<thead><tr>
				<th style="width:40%">${__('Course')}</th>
				<th style="width:10%;text-align:center">${__('M')}</th>
				<th style="width:20%">${__('Status')}</th>
				<th style="width:30%">${__('Detail')}</th>
			</tr></thead><tbody>`;

		courses.forEach(function (c) {
			let badge_cls = 'cov-missing';
			let label = __('Not Enrolled');
			if (c.status === 'current_period') { badge_cls = 'cov-current'; label = __('Current Period'); }
			else if (c.status === 'history') { badge_cls = 'cov-history'; label = __('History'); }

			const code = (c.course || '').trim();
			const name = (c.course_name || '').trim();
			let displayCourse = code;
			if (name) {
				// Avoid duplicated rendering like "MAR 520 - X — MAR 520 - X"
				const codeLower = code.toLowerCase();
				const nameLower = name.toLowerCase();
				const isDuplicate = nameLower === codeLower || nameLower.startsWith(codeLower + ' - ');
				displayCourse = isDuplicate ? name : `${code} — ${name}`;
			}

			html += `<tr class="cov-row-${c.status}">
				<td>${frappe.utils.escape_html(displayCourse)}</td>
				<td style="text-align:center">${c.mandatory ? '&#10003;' : ''}</td>
				<td><span class="cov-badge ${badge_cls}">${label}</span></td>
				<td class="text-muted">${frappe.utils.escape_html(c.detail || '')}</td>
			</tr>`;
		});

		html += `</tbody></table>`;
	}

	html += `</div></div>`;
	return html;
}

function kpi_card(label, value, color) {
	return `<div class="cov-kpi">
		<div class="cov-kpi-value" style="color:${color}">${value ?? 0}</div>
		<div class="cov-kpi-label">${label}</div>
	</div>`;
}

function render_styles() {
	return `<style>
.coverage-container { padding: 0 4px; }
.cov-legend .cov-badge { font-size: 12px; }
.cov-student { border: 1px solid var(--border-color); border-radius: 8px; margin-bottom: 12px; overflow: hidden; }
.cov-header { padding: 12px 16px; background: var(--subtle-fg); font-size: 14px; display: flex; align-items: center; }
.cov-clickable { cursor: pointer; }
.cov-clickable:hover { background: var(--subtle-accent); }
.cov-chevron { display: inline-block; transition: transform 0.2s; margin-right: 8px; font-size: 10px; }
.cov-chevron.rotated { transform: rotate(90deg); }
.cov-body { padding: 12px 16px; }
.cov-kpis { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
.cov-kpi { flex: 1; min-width: 100px; text-align: center; padding: 12px 8px; border-radius: 8px; background: var(--subtle-fg); }
.cov-kpi-value { font-size: 24px; font-weight: 700; line-height: 1.2; }
.cov-kpi-label { font-size: 11px; color: var(--text-muted); margin-top: 4px; }
.cov-table { font-size: 13px; }
.cov-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 500; }
.cov-current { background: var(--green-100); color: var(--green-700); }
.cov-history { background: var(--gray-200); color: var(--gray-700); }
.cov-missing { background: var(--red-100); color: var(--red-700); }
.cov-row-missing td:first-child { font-weight: 600; }
</style>`;
}
