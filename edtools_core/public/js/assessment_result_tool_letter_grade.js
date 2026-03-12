/**
 * Assessment Result Tool - Letter grade input support (edtools_core)
 *
 * Replaces numeric score inputs with letter grade dropdowns when the
 * Assessment Plan uses a grading scale with letter-style intervals (e.g. MsC: A, A-, B+, etc).
 * The user selects a letter; we convert it to the corresponding numeric score and save.
 *
 * Also fixes "2 selects" issue: ensures student_group is fetched from Assessment Plan
 * and displayed read-only; prevents duplicate transforms when changing plans without refresh.
 */

// Debounce to avoid multiple transform runs (MutationObserver + setTimeout) causing "select dobles"
let _transformDebounceTimer = null;
const _TRANSFORM_DEBOUNCE_MS = 200;

function _schedule_transform(frm) {
	if (_transformDebounceTimer) clearTimeout(_transformDebounceTimer);
	_transformDebounceTimer = setTimeout(function () {
		_transformDebounceTimer = null;
		transform_inputs_to_letter_dropdown(frm);
	}, _TRANSFORM_DEBOUNCE_MS);
}

frappe.ui.form.on('Assessment Result Tool', {
	setup: function (frm) {
		if (frm.fields_dict.student_group) {
			frm.set_df_property('student_group', 'read_only', 1);
		}
	},

	refresh: function (frm) {
		if (frm.fields_dict.student_group) {
			frm.set_df_property('student_group', 'read_only', 1);
		}
		if (!frm.fields_dict.result_html) return;

		// Wrap get_marks - use debounce so we don't run transform multiple times
		if (frm.events.get_marks && !frm.events.get_marks._letterGradeWrapped) {
			const orig = frm.events.get_marks;
			frm.events.get_marks = function (frm, criteria_list) {
				orig(frm, criteria_list);
				_schedule_transform(frm);
			};
			frm.events.get_marks._letterGradeWrapped = true;
		}

		if (!frm.doc.assessment_plan) return;
		const wrapper = frm.fields_dict.result_html.wrapper;
		if (!wrapper || wrapper._letterGradeObserverSetup) return;

		const observer = new MutationObserver(function () {
			_schedule_transform(frm);
		});
		observer.observe(wrapper, { childList: true, subtree: true });
		wrapper._letterGradeObserverSetup = true;

		_schedule_transform(frm);
	},

	assessment_plan: function (frm) {
		if (frm.doc.assessment_plan && !frm.doc.student_group) {
			frappe.db.get_value('Assessment Plan', frm.doc.assessment_plan, 'student_group', function (r) {
				if (r && r.student_group) {
					frm.set_value('student_group', r.student_group);
					_load_assessment_students(frm);
				}
			});
		}
		if (frm.doc.assessment_plan && frm.doc.student_group) {
			_schedule_transform(frm);
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

	// Remove any existing letter selects to avoid duplicates when re-running (e.g. plan change)
	$(wrapper).find('.student-result-letter-select').remove();
	$(wrapper).find('.letter-grade-transformed').removeClass('letter-grade-transformed').show();
	$(wrapper).find('span.student-result-grade').show();

	const inputs = wrapper.querySelectorAll('input.student-result-data:not(.letter-grade-transformed)');
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
