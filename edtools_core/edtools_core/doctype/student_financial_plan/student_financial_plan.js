// Copyright (c) 2026, EdTools and contributors
// For license information, please see license.txt

const SFP_API = 'edtools_core.edtools_core.doctype.student_financial_plan.student_financial_plan';

function _flt(v) {
	return typeof flt === 'function' ? flt(v) : parseFloat(v) || 0;
}
function _cint(v) {
	return typeof cint === 'function' ? cint(v) : parseInt(v, 10) || 0;
}

frappe.ui.form.on('Student Financial Plan', {
	setup(frm) {
		frm.set_query('student_group', function () {
			return { filters: {} };
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

	selection_mode(frm) {
		frm.set_value('student', '');
		frm.set_value('student_group', '');
		frm.clear_table('students');
		frm.refresh_fields();
		frm.get_field('results_html').$wrapper.html('');
	},

	generate_financial_plan(frm) {
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
			},
		});
	},
});

function fmt_money_plain(val, currency) {
	if (val === undefined || val === null) val = 0;
	const c = currency || frappe.boot.sysdefaults.currency || 'USD';
	if (typeof format_currency === 'function') {
		return format_currency(val, c);
	}
	try {
		const raw = frappe.format(val, { fieldtype: 'Currency', options: c });
		const tmp = document.createElement('div');
		tmp.innerHTML = raw;
		return tmp.textContent || tmp.innerText || String(val);
	} catch (e) {
		return String(val);
	}
}

function fmt_date(d) {
	if (!d) return '';
	return frappe.datetime.str_to_user(d);
}

function fee_is_paid_row(f) {
	if (f.edtools_manual_paid) return true;
	if (_cint(f.docstatus) === 1 && _flt(f.outstanding_amount) <= 0) return true;
	return false;
}

function render_financial_plan(frm, data) {
	const $wrapper = frm.get_field('results_html').$wrapper;
	$wrapper.empty();

	const students = data.students || {};
	const hasManualPaid = !!data.has_manual_paid_field;
	const student_ids = Object.keys(students);
	if (!student_ids.length) {
		$wrapper.html('<p class="text-muted">' + __('No results.') + '</p>');
		return;
	}

	let html = `<div class="sfp-container" data-has-manual-paid="${hasManualPaid ? 1 : 0}">`;
	html += render_financial_legend();

	student_ids.forEach(function (sid, idx) {
		const s = students[sid];
		html += render_financial_student_block(sid, s, student_ids.length > 1, idx, hasManualPaid);
	});

	html += `</div>`;
	html += render_financial_styles();
	$wrapper.html(html);

	$wrapper.find('.sfp-header').on('click', function () {
		const $body = $(this).next('.sfp-body');
		$body.slideToggle(200);
		$(this).find('.sfp-chevron').toggleClass('rotated');
	});

	bind_sfp_fee_links($wrapper);
	bind_sfp_actions(frm, $wrapper, hasManualPaid);
}

function bind_sfp_fee_links($wrapper) {
	$wrapper.find('.sfp-fee-cell a').on('click', function (e) {
		e.preventDefault();
		const name = $(this).text().trim();
		if (name) frappe.set_route('Form', 'Fees', name);
	});
	$wrapper.find('.sfp-fs-cell a').on('click', function (e) {
		e.preventDefault();
		const name = $(this).text().trim();
		if (name) frappe.set_route('Form', 'Fee Schedule', name);
	});
}

function bind_sfp_actions(frm, $wrapper, hasManualPaid) {
	$wrapper.find('.sfp-btn-add-fee').on('click', function () {
		const student = $(this).data('student');
		open_add_fee_dialog(frm, student, $wrapper);
	});

	$wrapper.find('.sfp-btn-edit-fee').on('click', function () {
		const name = $(this).data('fee');
		const student = $(this).data('student');
		open_edit_fee_dialog(frm, name, student, $wrapper);
	});

	$wrapper.find('.sfp-btn-delete-fee').on('click', function () {
		const name = $(this).data('fee');
		frappe.confirm(__('Delete this fee? Draft only.'), function () {
			frappe.call({
				method: SFP_API + '.sfp_delete_fee',
				args: { fee_name: name },
				callback(r) {
					if (!r.exc) {
						frappe.show_alert({ message: __('Fee removed'), indicator: 'green' });
						frm.trigger('generate_financial_plan');
					}
				},
			});
		});
	});

	if (hasManualPaid) {
		$wrapper.find('.sfp-paid-check').on('change', function () {
			const name = $(this).data('fee');
			const val = $(this).is(':checked') ? 1 : 0;
			frappe.call({
				method: SFP_API + '.sfp_set_manual_paid',
				args: { fee_name: name, value: val },
				callback(r) {
					if (!r.exc) {
						frappe.show_alert({ message: __('Saved'), indicator: 'green' });
						frm.trigger('generate_financial_plan');
					}
				},
			});
		});
	}
}

function open_add_fee_dialog(frm, student, $wrapper) {
	let componentRows = [];

	frappe.call({
		method: SFP_API + '.sfp_get_program_enrollments',
		args: { student: student },
		callback(r0) {
			const pe_list = r0.message || [];
			if (!pe_list.length) {
				frappe.msgprint(
					__('No submitted Program Enrollment for this student. Create one first.')
				);
				return;
			}

			const d = new frappe.ui.Dialog({
				title: __('Add fee'),
				fields: [
					{
						fieldname: 'program_enrollment',
						fieldtype: 'Link',
						label: __('Program Enrollment'),
						options: 'Program Enrollment',
						reqd: 1,
						get_query: function () {
							return { filters: { student: student, docstatus: 1 } };
						},
					},
					{
						fieldname: 'fee_component',
						fieldtype: 'Select',
						label: __('Component'),
						options: '',
						reqd: 1,
						description: __(
							'One line from a Fee Structure for this program/period (e.g. Registro, Inscripción). Not the whole structure.'
						),
					},
					{ fieldname: 'sec', fieldtype: 'Section Break' },
					{ fieldname: 'due_date', fieldtype: 'Date', label: __('Due Date'), reqd: 1 },
					{ fieldname: 'amount', fieldtype: 'Currency', label: __('Amount'), reqd: 1 },
					{
						fieldname: 'description',
						fieldtype: 'Small Text',
						label: __('Description'),
					},
				],
				primary_action_label: __('Create'),
				primary_action(values) {
					const pe = values.program_enrollment;
					const sel = values.fee_component;
					const m = sel && sel.match(/^\[(\d+)\]/);
					if (!pe || !m) {
						frappe.msgprint(__('Select Program Enrollment and a component.'));
						return;
					}
					const idx = parseInt(m[1], 10);
					const row = componentRows[idx];
					if (!row) {
						frappe.msgprint(__('Invalid component selection.'));
						return;
					}
					frappe.call({
						method: SFP_API + '.sfp_create_fee',
						args: {
							program_enrollment: pe,
							fee_structure: row.fee_structure,
							fees_category: row.fees_category,
							due_date: values.due_date,
							amount: values.amount,
							description:
								(values.description && values.description.trim()) ||
								row.description ||
								'',
						},
						freeze: true,
						callback(r) {
							if (!r.exc) {
								d.hide();
								frappe.show_alert({ message: __('Fee created'), indicator: 'green' });
								frm.trigger('generate_financial_plan');
							}
						},
					});
				},
			});

			function load_components_for_pe(pe) {
				d.set_value('fee_component', '');
				d.set_df_property('fee_component', 'options', '');
				componentRows = [];
				if (!pe) {
					return;
				}
				frappe.call({
					method: SFP_API + '.sfp_get_fee_components_for_enrollment',
					args: { program_enrollment: pe },
					callback(r) {
						componentRows = r.message || [];
						if (!componentRows.length) {
							frappe.msgprint(
								__(
									'No Fee Structure components for this enrollment period. Create or submit a Fee Structure first.'
								)
							);
							return;
						}
						const labels = componentRows.map(function (c, i) {
							return (
								'[' +
								i +
								'] ' +
								c.fees_category +
								' — ' +
								c.fee_structure +
								' (' +
								fmt_money_plain(c.amount) +
								')'
							);
						});
						d.set_df_property('fee_component', 'options', labels.join('\n'));
						if (componentRows.length === 1) {
							d.set_value('fee_component', labels[0]);
							d.set_value('amount', componentRows[0].amount);
							if (componentRows[0].description) {
								d.set_value('description', componentRows[0].description);
							}
						}
					},
				});
			}

			d.fields_dict.program_enrollment.df.onchange = function () {
				load_components_for_pe(d.get_value('program_enrollment'));
			};

			d.fields_dict.fee_component.df.onchange = function () {
				const sel = d.get_value('fee_component');
				const m = sel && sel.match(/^\[(\d+)\]/);
				if (!m) return;
				const idx = parseInt(m[1], 10);
				const row = componentRows[idx];
				if (row) {
					d.set_value('amount', row.amount);
					if (row.description) {
						d.set_value('description', row.description);
					}
				}
			};

			d.show();

			if (pe_list.length === 1) {
				d.set_value('program_enrollment', pe_list[0].name);
				load_components_for_pe(pe_list[0].name);
			}
		},
	});
}

function open_edit_fee_dialog(frm, feeName, student, $wrapper) {
	frappe.call({
		method: 'frappe.client.get',
		args: { doctype: 'Fees', name: feeName },
		callback(r) {
			if (!r.message || r.message.docstatus !== 0) {
				frappe.msgprint(__('Only draft fees can be edited here.'));
				return;
			}
			const doc = r.message;
			const row0 = (doc.components && doc.components[0]) || {};
			const d = new frappe.ui.Dialog({
				title: __('Edit fee') + ' ' + feeName,
				fields: [
					{ fieldname: 'due_date', fieldtype: 'Date', label: __('Due Date'), default: doc.due_date, reqd: 1 },
					{
						fieldname: 'amount',
						fieldtype: 'Currency',
						label: __('Amount'),
						default: row0.amount,
						reqd: 1,
					},
					{
						fieldname: 'description',
						fieldtype: 'Small Text',
						label: __('Description'),
						default: row0.description,
					},
				],
				primary_action_label: __('Save'),
				primary_action(values) {
					frappe.call({
						method: SFP_API + '.sfp_update_fee',
						args: {
							fee_name: feeName,
							due_date: values.due_date,
							amount: values.amount,
							description: values.description,
						},
						freeze: true,
						callback(res) {
							if (!res.exc) {
								d.hide();
								frappe.show_alert({ message: __('Fee updated'), indicator: 'green' });
								frm.trigger('generate_financial_plan');
							}
						},
					});
				},
			});
			d.show();
		},
	});
}

function render_financial_legend() {
	return `
	<div class="sfp-legend" style="margin-bottom:12px;color:var(--text-muted);font-size:12px;">
		${__('Fees from all submitted Program Enrollments for the selected student(s). Use Add fee to create draft fees linked to an enrollment.')}
	</div>`;
}

function render_financial_student_block(sid, s, collapsible, idx, hasManualPaid) {
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
	html += `<button type="button" class="btn btn-xs btn-default sfp-btn-add-fee" style="margin-left:auto" data-student="${frappe.utils.escape_html(
		sid
	)}">${__('Add fee')}</button>`;
	html += `</div>`;

	html += `<div class="sfp-body" ${open}>`;

	if (warning) {
		html += `<div class="alert alert-warning" style="margin:8px 0;">${frappe.utils.escape_html(warning)}</div>`;
		html += `</div></div>`;
		return html;
	}

	html += `<div class="sfp-kpis">`;
	html += kpi_card(__('Fee documents'), String(kpis.count || 0), 'var(--text-color)', false);
	html += kpi_card(__('Total billed'), fmt_money_plain(kpis.total_billed), 'var(--blue-600)', true);
	html += kpi_card(__('Outstanding'), fmt_money_plain(kpis.total_outstanding), 'var(--orange-600)', true);
	html += kpi_card(__('Paid installments'), String(kpis.paid_count || 0), 'var(--green-600)', false);
	html += `</div>`;

	const fees = s.fees || [];
	if (fees.length) {
		html += `<table class="table table-bordered sfp-table">
			<thead><tr>
				<th style="width:14%">${__('Fee')}</th>
				<th style="width:9%">${__('Due date')}</th>
				<th style="width:9%">${__('Grand total')}</th>
				<th style="width:9%">${__('Outstanding')}</th>
				<th style="width:8%">${__('Status')}</th>
				<th style="width:8%">${__('Paid')}</th>
				<th style="width:11%">${__('Fee Schedule')}</th>
				<th style="width:18%">${__('Description')}</th>
				<th style="width:14%">${__('Actions')}</th>
			</tr></thead><tbody>`;

		fees.forEach(function (f) {
			const cur = f.currency || 'USD';
			const fee_link = `<a href="#" class="sfp-link">${frappe.utils.escape_html(f.name)}</a>`;
			const fs = f.fee_schedule
				? `<a href="#" class="sfp-link-fs">${frappe.utils.escape_html(f.fee_schedule)}</a>`
				: '';
			const desc = f.components_description || '';
			const paid = fee_is_paid_row(f);
			let paidCell = '';
			if (hasManualPaid) {
				const ch = f.edtools_manual_paid ? ' checked' : '';
				paidCell = `<input type="checkbox" class="sfp-paid-check" data-fee="${frappe.utils.escape_html(
					f.name
				)}"${ch} />`;
			} else {
				paidCell = paid ? `<span class="indicator-pill green">${__('Yes')}</span>` : `<span class="indicator-pill orange">${__('No')}</span>`;
			}
			const canEdit = _cint(f.docstatus) === 0;
			let actions = '';
			if (canEdit) {
				actions = `<button type="button" class="btn btn-xs btn-default sfp-btn-edit-fee" data-fee="${frappe.utils.escape_html(
					f.name
				)}" data-student="${frappe.utils.escape_html(sid)}">${__('Edit')}</button> `;
				actions += `<button type="button" class="btn btn-xs btn-default sfp-btn-delete-fee" data-fee="${frappe.utils.escape_html(
					f.name
				)}">${__('Delete')}</button>`;
			} else {
				actions = `<span class="text-muted">${__('Open form to cancel')}</span>`;
			}
			html += `<tr>
				<td class="sfp-fee-cell">${fee_link}</td>
				<td>${frappe.utils.escape_html(fmt_date(f.due_date))}</td>
				<td class="sfp-num">${frappe.utils.escape_html(fmt_money_plain(f.grand_total, cur))}</td>
				<td class="sfp-num">${frappe.utils.escape_html(fmt_money_plain(f.outstanding_amount, cur))}</td>
				<td><span class="sfp-badge">${frappe.utils.escape_html(f.docstatus_label || '')}</span></td>
				<td class="sfp-paid-cell">${paidCell}</td>
				<td class="sfp-fs-cell">${fs}</td>
				<td class="text-muted" style="font-size:12px;">${frappe.utils.escape_html(desc)}</td>
				<td>${actions}</td>
			</tr>`;
		});

		html += `</tbody></table>`;
	} else {
		html += `<p class="text-muted">${__('No Fee documents for this enrollment.')}</p>`;
	}

	html += `</div></div>`;
	return html;
}

function kpi_card(label, value, color, isMoney) {
	const cls = isMoney ? 'sfp-kpi-value sfp-kpi-money' : 'sfp-kpi-value';
	return `<div class="sfp-kpi">
		<div class="${cls}" style="color:${color}">${value ?? 0}</div>
		<div class="sfp-kpi-label">${label}</div>
	</div>`;
}

function render_financial_styles() {
	return `<style>
.sfp-container { padding: 0 4px; }
.sfp-student { border: 1px solid var(--border-color); border-radius: 8px; margin-bottom: 12px; overflow: hidden; }
.sfp-header { padding: 12px 16px; background: var(--subtle-fg); font-size: 14px; display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.sfp-clickable { cursor: pointer; }
.sfp-clickable:hover { background: var(--subtle-accent); }
.sfp-chevron { display: inline-block; transition: transform 0.2s; margin-right: 8px; font-size: 10px; }
.sfp-chevron.rotated { transform: rotate(90deg); }
.sfp-body { padding: 12px 16px; }
.sfp-kpis { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
.sfp-kpi { flex: 1; min-width: 100px; text-align: center; padding: 12px 8px; border-radius: 8px; background: var(--subtle-fg); }
.sfp-kpi-value { font-size: 22px; font-weight: 700; line-height: 1.2; text-align: center; width: 100%; }
.sfp-kpi-money { display: block; text-align: center !important; }
.sfp-kpi-label { font-size: 11px; color: var(--text-muted); margin-top: 4px; text-align: center; }
.sfp-table { font-size: 13px; }
.sfp-table td.sfp-num { text-align: right; }
.sfp-badge { font-size: 12px; }
.sfp-paid-cell { text-align: center; vertical-align: middle; }
</style>`;
}
