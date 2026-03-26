/**
 * Assessment Result (formulario): permite elegir la letra (Grado) en la tabla Detalles
 * y editar la puntuación; la letra y el número se mantienen alineados con la escala MsC.
 *
 * Requiere en servidor (Property Setter / patch):
 * - Assessment Result: campo tabla "details" con allow_on_submit = 1 (para que
 *   grid.display_status sea "Write" en docs enviados; sin eso el grid_form queda read-only).
 * - Assessment Result Detail: score, grade con allow_on_submit = 1.
 *
 * ScriptManager llama form_render como: handler(frm, doctype, name) — name = cdn de la fila.
 */

let _grade_ui_timer = null;

const _letterOptionsCache = Object.create(null);
const _pendingFetch = Object.create(null);
const _CACHE_TTL_MS = 5 * 60 * 1000;

function _schedule_grade_ui(frm) {
	if (_grade_ui_timer) clearTimeout(_grade_ui_timer);
	_grade_ui_timer = setTimeout(function () {
		_grade_ui_timer = null;
		setup_assessment_result_grade_ui(frm);
	}, 200);
}

function _is_cache_fresh(entry) {
	return !!entry && typeof entry.ts === 'number' && Date.now() - entry.ts < _CACHE_TTL_MS;
}

function _fetch_letter_intervals(gradingScale) {
	const scale = (gradingScale || '').toString().trim();
	if (!scale) return Promise.resolve([]);

	const cached = _letterOptionsCache[scale];
	if (_is_cache_fresh(cached)) return Promise.resolve(cached.intervals || []);

	if (_pendingFetch[scale]) return _pendingFetch[scale];

	_pendingFetch[scale] = new Promise(function (resolve) {
		frappe.call({
			method: 'edtools_core.api.get_grading_scale_letter_options_for_scale',
			args: { grading_scale: scale },
			callback: function (r) {
				const intervals = (r && r.message) || [];
				const optionsString = (intervals || [])
					.map(function (i) {
						return i.grade_code;
					})
					.filter(Boolean)
					.join('\n');

				_letterOptionsCache[scale] = { intervals: intervals || [], optionsString, ts: Date.now() };
				resolve(intervals || []);
			},
			error: function () {
				resolve([]);
			},
			always: function () {
				delete _pendingFetch[scale];
			},
		});
	});

	return _pendingFetch[scale];
}

function _schedule_grade_ui_retry(frm, remaining) {
	const left = remaining == null ? 8 : remaining;
	if (left <= 0) return;
	setTimeout(function () {
		setup_assessment_result_grade_ui(frm, { retry_left: left - 1 });
	}, 150);
}

function _sync_row_docfields_after_grid_meta_change(grid) {
	if (!grid || !grid.grid_rows) return;
	try {
		grid.grid_rows.forEach(function (row) {
			if (row && row.doc && row.set_docfields) {
				row.set_docfields(true);
			}
		});
	} catch (e) {
		/* ignore */
	}
}

function _apply_grade_to_grid_row(grid, cdn, props) {
	const row = grid.grid_rows_by_docname && grid.grid_rows_by_docname[cdn];
	if (!row || !row.set_field_property) return;
	try {
		if (props.read_only !== undefined) {
			row.set_field_property('grade', 'read_only', props.read_only ? 1 : 0);
		}
		if (props.fieldtype) {
			row.set_field_property('grade', 'fieldtype', props.fieldtype);
		}
		if (props.options !== undefined) {
			row.set_field_property('grade', 'options', props.options);
		}
		row.refresh_field && row.refresh_field('grade');
	} catch (e) {
		/* ignore */
	}
}

function _apply_grade_field_props(grid, props) {
	try {
		if (props.read_only !== undefined) grid.update_docfield_property('grade', 'read_only', props.read_only ? 1 : 0);
		if (props.fieldtype) grid.update_docfield_property('grade', 'fieldtype', props.fieldtype);
		if (props.options !== undefined) grid.update_docfield_property('grade', 'options', props.options);
	} catch (e) {
		/* ignore */
	}

	_sync_row_docfields_after_grid_meta_change(grid);

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

function _defer_refresh_details_grid(frm) {
	// En navegación SPA a veces el grid queda con display_status antiguo un frame.
	function tick() {
		const g = frm.fields_dict.details && frm.fields_dict.details.grid;
		if (g && g.refresh) g.refresh();
	}
	setTimeout(tick, 0);
	setTimeout(tick, 120);
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
		_defer_refresh_details_grid(frm);
		_schedule_grade_ui(frm);
		update_total_score_and_grade(frm);

		const gradingScale = (frm.doc.grading_scale || '').toString().trim();
		if (gradingScale) _fetch_letter_intervals(gradingScale);

		_schedule_grade_ui_retry(frm);
	},
	assessment_plan: function (frm) {
		_schedule_grade_ui(frm);
	},
	grading_scale: function (frm) {
		_schedule_grade_ui(frm);
		const gradingScale = (frm.doc.grading_scale || '').toString().trim();
		if (gradingScale) _fetch_letter_intervals(gradingScale);
	},
	onload_post_render: function (frm) {
		_defer_refresh_details_grid(frm);
		_schedule_grade_ui(frm);
		const gradingScale = (frm.doc.grading_scale || '').toString().trim();
		if (gradingScale) _fetch_letter_intervals(gradingScale);
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
		mode: null,
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

	_fetch_letter_intervals(gradingScale).then(function (intervals) {
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

		const cached = _letterOptionsCache[gradingScale];
		const options =
			(cached && cached.optionsString) ||
			intervals
				.map(function (i) {
					return i.grade_code;
				})
				.filter(Boolean)
				.join('\n');

		_apply_grade_field_props(grid, { read_only: false, fieldtype: 'Select', options: options });

		const already = state.scale === gradingScale && state.mode === 'select';
		state.scale = gradingScale;
		state.mode = 'select';
		if (!already) {
			if (grid.refresh) grid.refresh();
			frm.refresh_field('details');
		}
	});
}

frappe.ui.form.on('Assessment Result Detail', {
	form_render: function (frm, _doctype, cdn) {
		const grid = frm.fields_dict.details && frm.fields_dict.details.grid;
		const gradingScale = (frm.doc.grading_scale || '').toString().trim();
		if (!grid || !cdn || !gradingScale) {
			_schedule_grade_ui(frm);
			return;
		}

		_fetch_letter_intervals(gradingScale).then(function (intervals) {
			if (!intervals.length) {
				_apply_grade_to_grid_row(grid, cdn, { read_only: true, fieldtype: 'Data' });
				return;
			}
			const cached = _letterOptionsCache[gradingScale];
			const options =
				(cached && cached.optionsString) ||
				intervals
					.map(function (i) {
						return i.grade_code;
					})
					.filter(Boolean)
					.join('\n');
			_apply_grade_to_grid_row(grid, cdn, {
				read_only: false,
				fieldtype: 'Select',
				options: options,
			});
		});

		_schedule_grade_ui(frm);
		_schedule_grade_ui_retry(frm, 4);
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
