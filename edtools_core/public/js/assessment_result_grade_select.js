/**
 * Assessment Result (formulario): permite elegir la letra (Grado) en la tabla Detalles
 * y editar la puntuación; la letra y el número se mantienen alineados con la escala MsC.
 *
 * - Convierte la columna "grade" en Select cuando hay Grading Scale con intervalos.
 * - Si el usuario cambia solo la puntuación, Education recalcula la letra (comportamiento estándar).
 * - Si el usuario elige otra letra distinta a la que implica la puntuación actual,
 *   se ajusta la puntuación al umbral mínimo de esa letra (misma lógica que Assessment Result Tool).
 */

let _grade_ui_timer = null;

function _schedule_grade_ui(frm) {
	if (_grade_ui_timer) clearTimeout(_grade_ui_timer);
	_grade_ui_timer = setTimeout(function () {
		_grade_ui_timer = null;
		setup_assessment_result_grade_ui(frm);
	}, 200);
}

function _num(v) {
	const n = parseFloat(v);
	return Number.isFinite(n) ? n : 0;
}

frappe.ui.form.on('Assessment Result', {
	refresh: function (frm) {
		_schedule_grade_ui(frm);
	},
	assessment_plan: function (frm) {
		_schedule_grade_ui(frm);
	},
	grading_scale: function (frm) {
		_schedule_grade_ui(frm);
	},
});

function setup_assessment_result_grade_ui(frm) {
	const grid = frm.fields_dict.details && frm.fields_dict.details.grid;
	if (!grid || !grid.update_docfield_property) {
		return;
	}

	if (!frm.doc.grading_scale) {
		try {
			grid.update_docfield_property('grade', 'read_only', 1);
			grid.update_docfield_property('grade', 'fieldtype', 'Data');
			grid.update_docfield_property('grade', 'options', '');
		} catch (e) {
			/* grid vacío al inicio */
		}
		return;
	}

	frappe.call({
		method: 'edtools_core.api.get_grading_scale_letter_options_for_scale',
		args: { grading_scale: frm.doc.grading_scale },
		callback: function (r) {
			const intervals = r.message || [];
			if (!intervals.length) {
				try {
					grid.update_docfield_property('grade', 'read_only', 1);
					grid.update_docfield_property('grade', 'fieldtype', 'Data');
				} catch (e2) {
					/* ignore */
				}
				return;
			}

			const options = intervals
				.map(function (i) {
					return i.grade_code;
				})
				.filter(Boolean)
				.join('\n');

			try {
				grid.update_docfield_property('grade', 'read_only', 0);
				grid.update_docfield_property('grade', 'fieldtype', 'Select');
				grid.update_docfield_property('grade', 'options', options);
			} catch (e3) {
				console.error('assessment_result_grade_select: grid update failed', e3);
			}
		},
	});
}

frappe.ui.form.on('Assessment Result Detail', {
	grade: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!frm.doc.grading_scale || !row.maximum_score) {
			return;
		}
		if (row.grade === '' || row.grade == null || row.grade === undefined) {
			return;
		}

		const max_sc = _num(row.maximum_score);
		const sc = _num(row.score);
		const pct = max_sc > 0 ? (sc / max_sc) * 100 : 0;

		frappe.call({
			method: 'education.education.api.get_grade',
			args: {
				grading_scale: frm.doc.grading_scale,
				percentage: pct,
			},
			callback: function (r) {
				const implied = (r.message || '').toString().trim();
				const chosen = (row.grade || '').toString().trim();
				if (implied === chosen) {
					return;
				}
				frappe.call({
					method: 'edtools_core.api.get_score_for_grade_code',
					args: {
						grading_scale: frm.doc.grading_scale,
						grade_code: row.grade,
						maximum_score: row.maximum_score,
					},
					callback: function (r2) {
						if (r2.message !== undefined && r2.message !== null) {
							frappe.model.set_value(cdt, cdn, 'score', r2.message);
						}
					},
				});
			},
		});
	},
});
