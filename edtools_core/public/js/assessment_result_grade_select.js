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

function _schedule_grade_ui_retry(frm, remaining) {
	const left = remaining == null ? 8 : remaining;
	if (left <= 0) return;
	setTimeout(function () {
		setup_assessment_result_grade_ui(frm, { retry_left: left - 1 });
	}, 150);
}

function _apply_grade_field_props(grid, props) {
	try {
		if (props.read_only !== undefined) grid.update_docfield_property('grade', 'read_only', props.read_only ? 1 : 0);
		if (props.fieldtype) grid.update_docfield_property('grade', 'fieldtype', props.fieldtype);
		if (props.options !== undefined) grid.update_docfield_property('grade', 'options', props.options);
	} catch (e) {
		/* ignore - grid aún no listo */
	}

	// Cuando se abre "Editando fila #n", Frappe usa un grid_form con su propio DF.
	// Si no lo actualizamos, puede quedar en Data/read-only hasta re-entrar o recargar.
	try {
		const gf = grid.grid_form;
		const gradeField = gf && gf.fields_dict && gf.fields_dict.grade;
		if (gradeField && gradeField.df) {
			if (props.read_only !== undefined) gradeField.df.read_only = props.read_only ? 1 : 0;
			if (props.fieldtype) gradeField.df.fieldtype = props.fieldtype;
			if (props.options !== undefined) gradeField.df.options = props.options;
			if (gf.refresh_field) gf.refresh_field('grade');
		}
	} catch (e2) {
		/* ignore */
	}
}

function _num(v) {
	const n = parseFloat(v);
	return Number.isFinite(n) ? n : 0;
}

function update_total_score_and_grade(frm) {
	const gradingScale = (frm.doc.grading_scale || '').toString().trim();
	if (!frm.doc.details || !frm.doc.details.length || !gradingScale || !frm.doc.maximum_score) {
		return;
	}
	let total = 0;
	frm.doc.details.forEach(function (row) {
		const sc = _num(row.score);
		total += sc;
	});
	const pct = frm.doc.maximum_score > 0 ? (total / frm.doc.maximum_score) * 100 : 0;
	frappe.call({
		method: 'education.education.api.get_grade',
		args: {
			grading_scale: gradingScale,
			percentage: pct,
		},
		callback: function (r) {
			if (r.message != null) {
				frm.set_value('total_score', total);
				frm.set_value('grade', r.message);
			}
		},
	});
}

frappe.ui.form.on('Assessment Result', {
	refresh: function (frm) {
		_schedule_grade_ui(frm);
		update_total_score_and_grade(frm);

		// En navegación SPA, el grid puede renderizarse después del refresh.
		// Reintenta unos ciclos para evitar que el usuario tenga que recargar manualmente.
		_schedule_grade_ui_retry(frm);
	},
	assessment_plan: function (frm) {
		_schedule_grade_ui(frm);
	},
	grading_scale: function (frm) {
		_schedule_grade_ui(frm);
	},
	onload_post_render: function (frm) {
		// Hook post-render: cuando el formulario ya pintó campos, es buen momento para ajustar la grilla.
		_schedule_grade_ui(frm);
	},
});

function setup_assessment_result_grade_ui(frm, opts) {
	const grid = frm.fields_dict.details && frm.fields_dict.details.grid;
	if (!grid || !grid.update_docfield_property) {
		_schedule_grade_ui_retry(frm, opts && opts.retry_left);
		return;
	}

	const gradingScale = (frm.doc.grading_scale || '').toString().trim();
	const state = (frm._edtools_assessment_result_grade_ui_state ||= {
		scale: null,
		mode: null, // 'select' | 'data'
	});
	if (!gradingScale) {
		if (state.scale === gradingScale && state.mode === 'data') return;
		_apply_grade_field_props(grid, { read_only: true, fieldtype: 'Data', options: '' });
		state.scale = gradingScale;
		state.mode = 'data';
		if (grid.refresh) grid.refresh();
		frm.refresh_field('details');
		return;
	}

	// En algunos casos el grid existe pero aún no ha terminado de renderizar columnas;
	// evitamos "cachear" el estado demasiado pronto.

	frappe.call({
		method: 'edtools_core.api.get_grading_scale_letter_options_for_scale',
		args: { grading_scale: gradingScale },
		callback: function (r) {
			const intervals = r.message || [];
			if (!intervals.length) {
				_apply_grade_field_props(grid, { read_only: true, fieldtype: 'Data' });
				if (state.scale !== gradingScale || state.mode !== 'data') {
					state.scale = gradingScale;
					state.mode = 'data';
					if (grid.refresh) grid.refresh();
					frm.refresh_field('details');
				}
				return;
			}

			const options = intervals
				.map(function (i) {
					return i.grade_code;
				})
				.filter(Boolean)
				.join('\n');

			_apply_grade_field_props(grid, { read_only: false, fieldtype: 'Select', options: options });

			// Si ya estábamos en modo select con esta escala, evitamos refrescar en bucle.
			const already = state.scale === gradingScale && state.mode === 'select';
			state.scale = gradingScale;
			state.mode = 'select';
			if (!already) {
				if (grid.refresh) grid.refresh();
				frm.refresh_field('details');
			}
		},
	});
}

// Cuando el usuario abre una fila del child table, este evento es el más confiable
// para asegurar que el campo grade ya esté en Select y editable.
frappe.ui.form.on('Assessment Result Detail', {
	form_render: function (frm) {
		_schedule_grade_ui(frm);
		_schedule_grade_ui_retry(frm, 6);
	},
});

frappe.ui.form.on('Assessment Result Detail', {
	score: function (frm) {
		update_total_score_and_grade(frm);
	},
	grade: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const gradingScale = (frm.doc.grading_scale || '').toString().trim();
		if (!gradingScale || !row.maximum_score) {
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
				grading_scale: gradingScale,
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
						grading_scale: gradingScale,
						grade_code: row.grade,
						maximum_score: row.maximum_score,
					},
					callback: function (r2) {
						if (r2.message !== undefined && r2.message !== null) {
							frappe.model.set_value(cdt, cdn, 'score', r2.message);
							update_total_score_and_grade(frm);
						}
					},
				});
			},
		});
	},
});
