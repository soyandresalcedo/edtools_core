// Copyright (c) 2026, EdTools and contributors
// For license information, please see license.txt

frappe.ui.form.on('Student Financial Plan', {
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
			frm.trigger('generate_financial_plan');
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

	generate_financial_plan(frm) {
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
			method: 'get_financial_plan',
			doc: frm.doc,
			freeze: true,
			freeze_message: __('Loading financial plan…'),
			callback(r) {
				if (r.message) {
					render_financial_plan(frm, r.message);
				}
			}
		});
	}
});

function fmt_money(val, currency) {
	if (val === undefined || val === null) val = 0;
	let c = currency || frappe.boot.sysdefaults.currency || 'USD';
	try {
		return frappe.format(val, { fieldtype: 'Currency', options: c });
	} catch (e) {
		return String(val);
	}
}

function fmt_date(d) {
	if (!d) return '';
	return frappe.datetime.str_to_user(d);
}

function render_financial_plan(frm, data) {
	const $wrapper = frm.get_field('results_html').$wrapper;
	$wrapper.empty();

	const students = data.students || {};
	const student_ids = Object.keys(students);
	if (!student_ids.length) {
		$wrapper.html('<p class="text-muted">' + __('No results.') + '</p>');
		return;
	}

	let html = `<div class="sfp-container">`;
	html += render_financial_legend();

	student_ids.forEach(function (sid, idx) {
		const s = students[sid];
		html += render_financial_student_block(sid, s, student_ids.length > 1, idx);
	});

	html += `</div>`;
	html += render_financial_styles();
	$wrapper.html(html);

	$wrapper.find('.sfp-header').on('click', function () {
		const $body = $(this).next('.sfp-body');
		$body.slideToggle(200);
		$(this).find('.sfp-chevron').toggleClass('rotated');
	});
}

function render_financial_legend() {
	return `
	<div class="sfp-legend" style="margin-bottom:12px;color:var(--text-muted);font-size:12px;">
		${__('Fees linked to Program Enrollment for the selected program and academic period.')}
	</div>`;
}

function render_financial_student_block(sid, s, collapsible, idx) {
	const kpis = s.kpis || {};
	const warning = s.warning || '';
	const open = idx === 0 ? '' : 'style="display:none"';

	let header_class = collapsible ? 'sfp-header sfp-clickable' : 'sfp-header';
	let chevron = collapsible
		? `<span class="sfp-chevron ${idx === 0 ? 'rotated' : ''}">&#9654;</span> `
		: '';

	let html = `<div class="sfp-student" data-student="${frappe.utils.escape_html(sid)}">`;

	html += `<div class="${header_class}">`;
	html += `${chevron}<strong>${frappe.utils.escape_html(s.student_name || sid)}</strong>`;
	html += `<span class="text-muted" style="margin-left:8px;">${frappe.utils.escape_html(sid)}</span>`;
	html += `</div>`;

	html += `<div class="sfp-body" ${open}>`;

	if (warning) {
		html += `<div class="alert alert-warning" style="margin:8px 0;">${frappe.utils.escape_html(warning)}</div>`;
		html += `</div></div>`;
		return html;
	}

	html += `<div class="sfp-kpis">`;
	html += kpi_card(__('Fee documents'), kpis.count || 0, 'var(--text-color)');
	html += kpi_card(__('Total billed'), fmt_money(kpis.total_billed), 'var(--blue-600)');
	html += kpi_card(__('Outstanding'), fmt_money(kpis.total_outstanding), 'var(--orange-600)');
	html += kpi_card(__('Paid installments'), kpis.paid_count || 0, 'var(--green-600)');
	html += `</div>`;

	const fees = s.fees || [];
	if (fees.length) {
		html += `<table class="table table-bordered sfp-table">
			<thead><tr>
				<th style="width:18%">${__('Fee')}</th>
				<th style="width:11%">${__('Due date')}</th>
				<th style="width:11%">${__('Grand total')}</th>
				<th style="width:11%">${__('Outstanding')}</th>
				<th style="width:10%">${__('Status')}</th>
				<th style="width:15%">${__('Fee Schedule')}</th>
				<th style="width:24%">${__('Description')}</th>
			</tr></thead><tbody>`;

		fees.forEach(function (f) {
			const cur = f.currency || 'USD';
			const fee_link = `<a href="#" class="sfp-link">${frappe.utils.escape_html(f.name)}</a>`;
			const fs = f.fee_schedule
				? `<a href="#" class="sfp-link-fs">${frappe.utils.escape_html(f.fee_schedule)}</a>`
				: '';
			const desc = f.components_description || '';
			html += `<tr>
				<td class="sfp-fee-cell">${fee_link}</td>
				<td>${frappe.utils.escape_html(fmt_date(f.due_date))}</td>
				<td>${frappe.utils.escape_html(fmt_money(f.grand_total, cur))}</td>
				<td>${frappe.utils.escape_html(fmt_money(f.outstanding_amount, cur))}</td>
				<td><span class="sfp-badge">${frappe.utils.escape_html(f.docstatus_label || '')}</span></td>
				<td class="sfp-fs-cell">${fs}</td>
				<td class="text-muted" style="font-size:12px;">${frappe.utils.escape_html(desc)}</td>
			</tr>`;
		});

		html += `</tbody></table>`;
	} else {
		html += `<p class="text-muted">${__('No Fee documents for this enrollment.')}</p>`;
	}

	html += `</div></div>`;
	return html;
}

function kpi_card(label, value, color) {
	return `<div class="sfp-kpi">
		<div class="sfp-kpi-value" style="color:${color}">${value ?? 0}</div>
		<div class="sfp-kpi-label">${label}</div>
	</div>`;
}

function render_financial_styles() {
	return `<style>
.sfp-container { padding: 0 4px; }
.sfp-student { border: 1px solid var(--border-color); border-radius: 8px; margin-bottom: 12px; overflow: hidden; }
.sfp-header { padding: 12px 16px; background: var(--subtle-fg); font-size: 14px; display: flex; align-items: center; }
.sfp-clickable { cursor: pointer; }
.sfp-clickable:hover { background: var(--subtle-accent); }
.sfp-chevron { display: inline-block; transition: transform 0.2s; margin-right: 8px; font-size: 10px; }
.sfp-chevron.rotated { transform: rotate(90deg); }
.sfp-body { padding: 12px 16px; }
.sfp-kpis { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
.sfp-kpi { flex: 1; min-width: 100px; text-align: center; padding: 12px 8px; border-radius: 8px; background: var(--subtle-fg); }
.sfp-kpi-value { font-size: 22px; font-weight: 700; line-height: 1.2; }
.sfp-kpi-label { font-size: 11px; color: var(--text-muted); margin-top: 4px; }
.sfp-table { font-size: 13px; }
.sfp-badge { font-size: 12px; }
</style>`;
}

frappe.ready(function () {
	$(document).on('click', '.sfp-fee-cell a', function (e) {
		e.preventDefault();
		const name = $(this).text().trim();
		if (name) frappe.set_route('Form', 'Fees', name);
	});
	$(document).on('click', '.sfp-fs-cell a', function (e) {
		e.preventDefault();
		const name = $(this).text().trim();
		if (name) frappe.set_route('Form', 'Fee Schedule', name);
	});
});
