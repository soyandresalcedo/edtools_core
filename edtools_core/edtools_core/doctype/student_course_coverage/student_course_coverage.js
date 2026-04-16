// Copyright (c) 2026, EdTools and contributors
// For license information, please see license.txt

frappe.ui.form.on('Student Course Coverage', {

	setup(frm) {
		frm.set_query('student_group', function () {
			const filters = {};
			if (frm.doc.program) {
				filters.program = frm.doc.program;
			}
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
			frappe.confirm(
				__('Clear the coverage results from this page?'),
				function () {
					frm.get_field('results_html').$wrapper.html('');
				}
			);
		});
	},

	selection_mode(frm) {
		frm.set_value('student', '');
		frm.set_value('student_group', '');
		frm.clear_table('students');
		frm.refresh_fields();
		frm.get_field('results_html').$wrapper.html('');
	},

	generate_coverage(frm) {
		const mode = frm.doc.selection_mode;
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
			},
		});
	},
});


/* ── Rendering (solo expediente + plan) ─────────────────────────── */

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
		html += render_student_block_history(sid, s, student_ids.length > 1, idx);
	});

	html += `</div>`;
	html += render_styles();
	$wrapper.html(html);

	$wrapper.off('click.covce').on('click.covce', '.cov-ce-link', function (e) {
		e.preventDefault();
		const name = $(this).text().trim();
		if (name) {
			frappe.set_route('Form', 'Course Enrollment', name);
		}
	});

	$wrapper.off('click.covar').on('click.covar', '.cov-ar-link', function (e) {
		e.preventDefault();
		const name = $(this).text().trim();
		if (name) {
			frappe.set_route('Form', 'Assessment Result', name);
		}
	});

	$wrapper.find('.cov-header').on('click', function () {
		const $body = $(this).next('.cov-body');
		$body.slideToggle(200);
		$(this).find('.cov-chevron').toggleClass('rotated');
	});
}

function render_legend() {
	return `
	<div class="cov-legend" style="margin-bottom:16px;display:flex;gap:16px;flex-wrap:wrap;align-items:center;">
		<span class="cov-badge cov-graded">${__('Graded')}</span>
		<span class="cov-badge cov-plan-ip">${__('Enrolled (plan)')}</span>
		<span class="cov-badge cov-plan-pending">${__('Pending (plan)')}</span>
		<span style="color:var(--text-muted);font-size:12px;margin-left:auto;">
			${__('Plan courses in progress below are omitted from the history table.')}
		</span>
	</div>`;
}

function render_student_block_history(sid, s, collapsible, idx) {
	const kpis = s.kpis || {};
	const warning = s.warning || '';
	const open = idx === 0 ? '' : 'style="display:none"';

	const header_class = collapsible ? 'cov-header cov-clickable' : 'cov-header';
	const chevron = collapsible
		? `<span class="cov-chevron ${idx === 0 ? 'rotated' : ''}">&#9654;</span> `
		: '';

	let html = `<div class="cov-student" data-student="${frappe.utils.escape_html(sid)}">`;

	html += `<div class="${header_class}">`;
	html += `${chevron}<strong>${frappe.utils.escape_html(s.student_name || sid)}</strong>`;
	html += `<span class="text-muted" style="margin-left:8px;">${frappe.utils.escape_html(sid)}</span>`;
	html += `</div>`;

	html += `<div class="cov-body" ${open}>`;

	if (warning) {
		html += `<div class="alert alert-warning" style="margin:8px 0;">${frappe.utils.escape_html(warning)}</div>`;
		html += `</div></div>`;
		return html;
	}

	html += `<div class="cov-kpis">`;
	html += kpi_card(__('Enrollments / rows'), kpis.enrollments, 'var(--text-color)');
	html += kpi_card(__('Graded'), kpis.graded, 'var(--green-600)');
	if ((kpis.plan_total || 0) > 0) {
		html += kpi_card(__('Plan courses'), kpis.plan_total, 'var(--text-color)');
		html += kpi_card(__('Plan: in progress'), kpis.plan_in_progress || 0, 'var(--orange-600)');
		html += kpi_card(__('Plan: pending'), kpis.plan_pending || 0, 'var(--red-600)');
	}
	html += `</div>`;

	const courses = s.courses || [];
	if (courses.length) {
		html += `<h4 class="cov-subtable-title">${__('Academic history')}</h4>`;
		html += `<table class="table table-bordered cov-table">
			<thead><tr>
				<th style="width:32%">${__('Course')}</th>
				<th style="width:14%">${__('Program')}</th>
				<th style="width:14%">${__('Period')}</th>
				<th style="width:12%">${__('Status')}</th>
				<th style="width:10%">${__('Grade')}</th>
				<th style="width:18%">${__('Records')}</th>
			</tr></thead><tbody>`;

		courses.forEach(function (c) {
			const code = (c.course || '').trim();
			const name = (c.course_name || '').trim();
			let displayCourse = code;
			if (name) {
				const codeLower = code.toLowerCase();
				const nameLower = name.toLowerCase();
				const isDuplicate = nameLower === codeLower || nameLower.startsWith(codeLower + ' - ');
				displayCourse = isDuplicate ? name : `${code} — ${name}`;
			}

			let badge_cls = 'cov-inprogress';
			let label = __('In progress');
			if (c.status === 'graded') {
				badge_cls = 'cov-graded';
				label = __('Graded');
			}

			const prog = (c.program || '').trim();
			const period = (c.period_label || '').trim();
			const grade = (c.grade || '').trim();
			const recordCell = format_history_record_cell(c);

			html += `<tr class="cov-row-${c.status || 'in_progress'}">
				<td>${frappe.utils.escape_html(displayCourse)}</td>
				<td class="text-muted">${frappe.utils.escape_html(prog)}</td>
				<td class="text-muted">${frappe.utils.escape_html(period)}</td>
				<td><span class="cov-badge ${badge_cls}">${label}</span></td>
				<td>${frappe.utils.escape_html(grade)}</td>
				<td class="text-muted cov-detail-cell">${recordCell}</td>
			</tr>`;
		});

		html += `</tbody></table>`;
	}

	const focus = s.plan_focus_rows || [];
	if (focus.length) {
		html += `<h4 class="cov-subtable-title" style="margin-top:20px;">${__('Plan: currently enrolled & pending')}</h4>`;
		html += `<table class="table table-bordered cov-table">
			<thead><tr>
				<th style="width:32%">${__('Course')}</th>
				<th style="width:14%">${__('Program')}</th>
				<th style="width:14%">${__('Period')}</th>
				<th style="width:12%">${__('Status')}</th>
				<th style="width:10%">${__('Grade')}</th>
				<th style="width:18%">${__('Records')}</th>
			</tr></thead><tbody>`;
		focus.forEach(function (c) {
			const code = (c.course || '').trim();
			const name = (c.course_name || '').trim();
			let displayCourse = code;
			if (name) {
				const codeLower = code.toLowerCase();
				const nameLower = name.toLowerCase();
				const isDuplicate = nameLower === codeLower || nameLower.startsWith(codeLower + ' - ');
				displayCourse = isDuplicate ? name : `${code} — ${name}`;
			}
			let badge_cls = 'cov-plan-pending';
			let label = __('Pending (plan)');
			if (c.focus_status === 'enrolled_in_progress') {
				badge_cls = 'cov-plan-ip';
				label = __('Enrolled (in progress)');
			}
			const prog = (c.program || '').trim();
			const period = (c.period_label || '').trim();
			const grade = (c.grade || '').trim();
			const recordCell = format_history_record_cell(c);
			html += `<tr class="cov-row-${c.status || 'plan_pending'}">
				<td>${frappe.utils.escape_html(displayCourse)}</td>
				<td class="text-muted">${frappe.utils.escape_html(prog)}</td>
				<td class="text-muted">${frappe.utils.escape_html(period)}</td>
				<td><span class="cov-badge ${badge_cls}">${label}</span></td>
				<td>${frappe.utils.escape_html(grade)}</td>
				<td class="text-muted cov-detail-cell">${recordCell}</td>
			</tr>`;
		});
		html += `</tbody></table>`;
	}

	html += `</div></div>`;
	return html;
}

function format_history_record_cell(c) {
	const esc = frappe.utils.escape_html;
	if (c.detail_kind === 'assessment_result') {
		const ar = (c.detail || c.assessment_result || '').trim();
		if (!ar) return '';
		return `<a href="#" class="cov-ar-link">${esc(ar)}</a>`;
	}
	const parts = [];
	if (c.detail) {
		parts.push(`<a href="#" class="cov-ce-link">${esc((c.detail || '').trim())}</a>`);
	}
	const ar = (c.assessment_result || '').trim();
	if (ar && ar !== (c.detail || '').trim()) {
		parts.push(`<a href="#" class="cov-ar-link">${esc(ar)}</a>`);
	}
	return parts.join(' <span class="text-muted">·</span> ') || '';
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
.cov-graded { background: var(--green-100); color: var(--green-700); }
.cov-inprogress { background: var(--orange-100); color: var(--orange-800); }
.cov-plan-ip { background: var(--blue-100, #cfe2ff); color: var(--blue-800, #084298); }
.cov-plan-pending { background: var(--red-100); color: var(--red-700); }
.cov-subtable-title { font-size: 13px; font-weight: 600; margin: 0 0 8px; color: var(--text-muted); }
.cov-row-missing td:first-child { font-weight: 600; }
</style>`;
}
