/**
 * Assessment Result Tool - Letter grade input support (edtools_core)
 *
 * Replaces numeric score inputs with letter grade dropdowns when the
 * Assessment Plan uses a grading scale with letter-style intervals (e.g. MsC: A, A-, B+, etc).
 * The user selects a letter; we convert it to the corresponding numeric score and save.
 *
 * Also fixes "2 selects" issue: ensures student_group is fetched from Assessment Plan
 * and displayed read-only, so only assessment_plan appears as an editable select.
 */

frappe.ui.form.on('Assessment Result Tool', {
	setup: function (frm) {
		// student_group always comes from assessment_plan - keep it read-only (avoids "2 selects")
		if (frm.fields_dict.student_group) {
			frm.set_df_property('student_group', 'read_only', 1);
		}
	},

	refresh: function (frm) {
		if (frm.fields_dict.student_group) {
			frm.set_df_property('student_group', 'read_only', 1);
		}
		if (!frm.fields_dict.result_html) return;

		// Wrap get_marks so we run our transform right after the table is rendered
		if (frm.events.get_marks && !frm.events.get_marks._letterGradeWrapped) {
			const orig = frm.events.get_marks;
			frm.events.get_marks = function (frm, criteria_list) {
				orig(frm, criteria_list);
				setTimeout(function () {
					transform_inputs_to_letter_dropdown(frm);
				}, 150);
			};
			frm.events.get_marks._letterGradeWrapped = true;
		}

		// Fallback: observer for table added after initial load
		if (!frm.doc.assessment_plan) return;
		const wrapper = frm.fields_dict.result_html.wrapper;
		if (!wrapper || wrapper._letterGradeObserverSetup) return;

		const observer = new MutationObserver(function () {
			transform_inputs_to_letter_dropdown(frm);
		});
		observer.observe(wrapper, { childList: true, subtree: true });
		wrapper._letterGradeObserverSetup = true;

		setTimeout(function () {
			transform_inputs_to_letter_dropdown(frm);
		}, 800);
	},

	assessment_plan: function (frm) {
		// Fix "2 selects": when assessment_plan is set but student_group empty (add_fetch failed/delayed),
		// fetch student_group from Assessment Plan and load students. Education handler returns early
		// when student_group is empty, so we handle that case here.
		if (frm.doc.assessment_plan && !frm.doc.student_group) {
			frappe.db.get_value('Assessment Plan', frm.doc.assessment_plan, 'student_group', function (r) {
				if (r && r.student_group) {
					frm.set_value('student_group', r.student_group);
					_load_assessment_students(frm);
				}
			});
		}
		// When plan changes and table will be re-rendered, get_marks wrap handles it.
		if (frm.doc.assessment_plan && frm.doc.student_group) {
			setTimeout(function () {
				transform_inputs_to_letter_dropdown(frm);
			}, 1200);
		}
	},
});

function _load_assessment_students(frm) {
	frm.doc.show_submit = false;
	frappe.call({
		method: 'education.education.api.get_assessment_students',
		args: {
			assessment_plan: frm.doc.assessment_plan,
			student_group: frm.doc.student_group,
		},
		callback: function (r) {
			if (r.message) {
				frm.doc.students = r.message;
				frm.events.render_table(frm);
				for (let i = 0; i < r.message.length; i++) {
					if (!r.message[i].docstatus) {
						frm.doc.show_submit = true;
						break;
					}
				}
				frm.events.submit_result(frm);
			}
		},
	});
}

function transform_inputs_to_letter_dropdown(frm) {
	const wrapper = frm.fields_dict.result_html?.wrapper;
	if (!wrapper) return;

	const inputs = wrapper.querySelectorAll(
		'input.student-result-data:not(.letter-grade-transformed)'
	);
	if (inputs.length === 0) return;

	frappe.call({
		method: 'edtools_core.api.get_grading_scale_letter_options',
		args: { assessment_plan: frm.doc.assessment_plan },
		callback: function (r) {
			const options = r.message || [];
			if (options.length === 0) return;

			inputs.forEach(function (input) {
				replace_with_letter_select(input, options);
			});
		},
	});
}

function replace_with_letter_select(input, letter_options) {
	const $input = $(input);
	const max_score = parseFloat($input.data('max-score')) || 100;
	const criteria = $input.data('criteria');
	const student = $input.data('student');
	const current_val = parseFloat($input.val()) || '';
	const disabled = input.disabled;

	// Build options: empty + each letter with score = (threshold/100) * max_score
	const $select = $('<select class="form-control student-result-letter-select"></select>')
		.attr('data-student', student)
		.attr('data-criteria', criteria)
		.attr('data-max-score', max_score)
		.css({ width: '85%', float: 'right' });

	if (disabled) {
		$select.prop('disabled', true);
	}

	$select.append($('<option value="">—</option>'));

	let selected = false;
	letter_options.forEach(function (opt) {
		const threshold = parseFloat(opt.threshold) || 0;
		const score = Math.round((threshold / 100) * max_score * 100) / 100;
		const $opt = $('<option></option>').attr('value', score).text(opt.grade_code);

		// Pre-select: first (highest) letter where percentage >= threshold
		if (!selected && current_val !== '' && !isNaN(parseFloat(current_val))) {
			const pct = (parseFloat(current_val) / max_score) * 100;
			if (pct >= threshold) {
				$opt.prop('selected', true);
				selected = true;
			}
		}
		$select.append($opt);
	});

	// Hide original input and the grade badge (select shows the value)
	const $cell = $input.closest('td');
	$cell.find('span.student-result-grade').hide();
	$input.addClass('letter-grade-transformed').hide().after($select);

	$select.on('change', function () {
		const val = $(this).val();
		$input.val(val === '' ? '' : val);
		$input.trigger('change');
	});
}
