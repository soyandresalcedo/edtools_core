// Copyright (c) 2026, EdTools
// Asistente de admisiones: cohorte → grupos → planes → Enrollment Agreements.
// Backend: edtools_core/admissions_wizard.py

const AW_API = 'edtools_core.admissions_wizard.';
const AW_STEPS = [__('Cohorte'), __('Grupos'), __('Planes'), __('Crear y descargar EA')];

frappe.pages['admissions-wizard'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Asistente de admisiones'),
		single_column: true,
	});
	wrapper.admissions_wizard = new AdmissionsWizard(page);
};

class AdmissionsWizard {
	constructor(page) {
		this.page = page;
		this.state = {
			step: 0,
			terms: [],
			term: null,
			termInfo: null,
			enrollments: [],
			drafts: [],
			showWithPlan: false,
			selected: new Set(),
			options: {},
			startDate: null,
			interest: 0,
			rows: {}, // pe -> {fee_structure, installments, start_date, customDate}
			sims: {}, // clave de simulación -> resultado
			results: {}, // pe -> {status, detail, ea_fee}
			running: false,
			done: false,
		};
		this.$root = $('<div class="aw"></div>').appendTo(page.main);
		this.inject_styles();
		this.load_terms();
	}

	// ------------------------------------------------------------------ utilidades

	call(method, args) {
		return frappe.call({ method: AW_API + method, args }).then((r) => r.message);
	}

	esc(v) {
		return frappe.utils.escape_html(v == null ? '' : String(v));
	}

	money(v) {
		return format_currency(v || 0, 'USD');
	}

	selectedEnrollments() {
		return this.state.enrollments.filter((e) => this.state.selected.has(e.program_enrollment));
	}

	programsOf(list) {
		return [...new Set(list.map((e) => e.program))];
	}

	// ------------------------------------------------------------------ render principal

	render() {
		const s = this.state;
		const stepper = AW_STEPS.map((label, i) => {
			const cls = i === s.step ? 'is-active' : i < s.step ? 'is-done' : '';
			const icon = i < s.step ? frappe.utils.icon('tick', 'xs') : `<span class="aw-num">${i + 1}</span>`;
			return `<button class="aw-step ${cls}" data-step="${i}" ${i > s.step || s.running ? 'disabled' : ''}>${icon}<span>${label}</span></button>`;
		}).join('');

		this.$root.html(`
			<div class="aw-stepper">${stepper}</div>
			<div class="aw-body"></div>
			<div class="aw-footer">
				<button class="btn btn-default btn-sm aw-prev">${__('Atrás')}</button>
				<span class="aw-footer-hint text-muted small"></span>
				<button class="btn btn-primary btn-sm aw-next">${__('Continuar')}</button>
			</div>`);

		this.$root.find('.aw-step').on('click', (e) => this.go(+$(e.currentTarget).data('step')));
		this.$root.find('.aw-prev').toggle(s.step > 0 && !s.running).on('click', () => this.go(s.step - 1));
		this.$root.find('.aw-next').toggle(s.step < 3).on('click', () => this.next());

		const $body = this.$root.find('.aw-body');
		[this.render_cohort, this.render_groups, this.render_plans, this.render_create][s.step].call(this, $body);
	}

	go(step) {
		if (this.state.running) return;
		this.state.step = step;
		this.render();
		if (step === 2) this.prepare_plans();
	}

	next() {
		const s = this.state;
		if (s.step === 0 && !s.selected.size) {
			this.hint(__('Selecciona al menos un estudiante.'));
			return;
		}
		if (s.step === 2) {
			const missing = this.selectedEnrollments().filter((e) => !e.has_plan && !(s.rows[e.program_enrollment] || {}).fee_structure);
			if (missing.length) {
				this.hint(__('{0} estudiante(s) sin beca asignada.', [missing.length]));
				return;
			}
		}
		this.go(s.step + 1);
	}

	hint(msg) {
		this.$root.find('.aw-footer-hint').html(`<span class="text-danger">${this.esc(msg)}</span>`);
	}

	// ------------------------------------------------------------------ paso 1: cohorte

	load_terms() {
		this.call('get_terms').then((terms) => {
			this.state.terms = terms || [];
			// Por defecto el periodo más próximo que aún no ha empezado (o el más reciente).
			const today = frappe.datetime.get_today();
			const upcoming = this.state.terms.filter((t) => t.term_start_date >= today);
			const pick = upcoming.length ? upcoming[upcoming.length - 1] : this.state.terms[0];
			if (pick) this.load_cohort(pick.name);
			else this.render();
		});
	}

	load_cohort(term) {
		const s = this.state;
		s.term = term;
		s.done = false;
		s.results = {};
		this.$root.find('.aw-body').html(`<div class="aw-empty">${__('Cargando matrículas…')}</div>`);
		this.call('get_cohort', { academic_term: term }).then((data) => {
			s.termInfo = data.term;
			s.enrollments = data.enrollments;
			s.drafts = data.drafts;
			s.selected = new Set(data.enrollments.filter((e) => !e.has_plan).map((e) => e.program_enrollment));
			s.rows = {};
			s.options = {};
			s.startDate = null;
			this.render();
		});
	}

	render_cohort($body) {
		const s = this.state;
		const termOptions = s.terms
			.map((t) => `<option value="${this.esc(t.name)}" ${t.name === s.term ? 'selected' : ''}>${this.esc(t.name)}</option>`)
			.join('');
		const visible = s.enrollments.filter((e) => s.showWithPlan || !e.has_plan);
		const withPlan = s.enrollments.filter((e) => e.has_plan).length;
		const noGroup = s.enrollments.filter((e) => !e.in_group && !e.has_plan).length;

		let html = `
			<div class="aw-card aw-filters">
				<label>${__('Periodo')}<select class="form-control input-sm aw-term">${termOptions}</select></label>
				<label class="aw-check"><input type="checkbox" class="aw-show-plan" ${s.showWithPlan ? 'checked' : ''}> ${__('Mostrar también los que ya tienen plan')}</label>
			</div>
			<div class="aw-metrics">
				${this.metric(__('Matrículas validadas'), s.enrollments.length)}
				${this.metric(__('Sin plan'), s.enrollments.length - withPlan)}
				${this.metric(__('Sin grupo'), noGroup)}
				${this.metric(__('En borrador'), s.drafts.length, s.drafts.length ? 'warning' : '')}
			</div>`;

		if (s.drafts.length) {
			html += `
				<div class="aw-banner is-warning">
					<div>${frappe.utils.icon('solid-warning', 'sm')}
					${__('{0} matrícula(s) de este periodo siguen en borrador y no entran al asistente hasta validarlas.', [s.drafts.length])}
					<span class="text-muted">${s.drafts.map((d) => this.esc(d.student_name)).join(', ')}</span></div>
					<button class="btn btn-default btn-xs aw-validate">${__('Validar {0}', [s.drafts.length])}</button>
				</div>`;
		}

		if (!visible.length) {
			html += `<div class="aw-empty">${s.enrollments.length ? __('Todos los estudiantes de este periodo ya tienen plan.') : __('No hay matrículas validadas en este periodo.')}</div>`;
		}

		const byProgram = {};
		visible.forEach((e) => (byProgram[e.program] = byProgram[e.program] || []).push(e));
		Object.keys(byProgram).forEach((program) => {
			const list = byProgram[program];
			const allSel = list.every((e) => s.selected.has(e.program_enrollment));
			html += `
				<div class="aw-card">
					<div class="aw-card-head">
						<label class="aw-check"><input type="checkbox" class="aw-sel-program" data-program="${this.esc(program)}" ${allSel ? 'checked' : ''}>
						<b>${this.esc(program)}</b></label>
						<span class="text-muted small">${__('{0} estudiante(s)', [list.length])}</span>
					</div>
					${list
						.map(
							(e) => `
						<label class="aw-row aw-check">
							<input type="checkbox" class="aw-sel" data-pe="${this.esc(e.program_enrollment)}" ${s.selected.has(e.program_enrollment) ? 'checked' : ''}>
							<span class="aw-grow">${this.esc(e.student_name)} <span class="text-muted small">${this.esc(e.student)}</span></span>
							${e.in_group ? `<span class="indicator-pill blue">${__('En grupo')}</span>` : ''}
							${e.has_plan ? `<span class="indicator-pill green">${__('Con plan')}</span>` : ''}
						</label>`
						)
						.join('')}
				</div>`;
		});

		$body.html(html);
		$body.find('.aw-term').on('change', (e) => this.load_cohort($(e.target).val()));
		$body.find('.aw-show-plan').on('change', (e) => {
			s.showWithPlan = e.target.checked;
			this.render();
		});
		$body.find('.aw-sel').on('change', (e) => {
			const pe = $(e.target).data('pe');
			e.target.checked ? s.selected.add(pe) : s.selected.delete(pe);
			this.render();
		});
		$body.find('.aw-sel-program').on('change', (e) => {
			const program = $(e.target).data('program');
			visible
				.filter((x) => x.program === program)
				.forEach((x) => (e.target.checked ? s.selected.add(x.program_enrollment) : s.selected.delete(x.program_enrollment)));
			this.render();
		});
		$body.find('.aw-validate').on('click', () => this.validate_drafts());
		this.$root.find('.aw-footer-hint').text(__('{0} seleccionado(s)', [s.selected.size]));
	}

	metric(label, value, tone) {
		return `<div class="aw-metric ${tone ? 'is-' + tone : ''}"><span>${this.esc(label)}</span><b>${value}</b></div>`;
	}

	validate_drafts() {
		const names = this.state.drafts.map((d) => d.name);
		frappe.confirm(__('¿Validar {0} matrícula(s) en borrador?', [names.length]), () => {
			frappe.dom.freeze(__('Validando matrículas…'));
			this.call('validate_enrollments', { names })
				.then((res) => {
					const failed = (res || []).filter((r) => !r.ok);
					if (failed.length) {
						frappe.msgprint({
							title: __('Algunas matrículas no se pudieron validar'),
							indicator: 'orange',
							message: failed.map((f) => `<b>${this.esc(f.name)}</b>: ${this.esc(f.error)}`).join('<br>'),
						});
					}
					this.load_cohort(this.state.term);
				})
				.always(() => frappe.dom.unfreeze());
		});
	}

	// ------------------------------------------------------------------ paso 2: grupos

	render_groups($body) {
		const s = this.state;
		const groups = {};
		this.selectedEnrollments().forEach((e) => (groups[e.group] = groups[e.group] || []).push(e));

		let html = `<p class="text-muted">${__('Formato: <b>Programa - Periodo</b>. Los grupos que no existan se crean y se agregan los estudiantes cuya matrícula coincide. Nada se guarda hasta el último paso.')}</p>`;
		Object.keys(groups).forEach((name) => {
			const list = groups[name];
			const toAdd = list.filter((e) => !e.in_group);
			const exists = this.groupExists(name);
			html += `
				<div class="aw-card">
					<div class="aw-card-head">
						<span>${frappe.utils.icon('users', 'md')} <b>${this.esc(name)}</b></span>
						<span class="indicator-pill ${exists ? 'blue' : 'green'}">${exists ? __('Existe') : __('Nuevo')}</span>
					</div>
					<div class="text-muted small">${__('{0} se agregan · {1} ya están en el grupo', [toAdd.length, list.length - toAdd.length])}</div>
					<details class="aw-details"><summary>${__('Ver estudiantes')}</summary>
						${list.map((e) => `<div class="aw-row"><span class="aw-grow">${this.esc(e.student_name)}</span>${e.in_group ? `<span class="text-muted small">${__('ya en el grupo')}</span>` : `<span class="text-success small">+ ${__('se agrega')}</span>`}</div>`).join('')}
					</details>
				</div>`;
		});
		$body.html(html);
	}

	groupExists(name) {
		// Si algún estudiante (de cualquier selección) ya figura en el grupo, el grupo existe.
		// Para el resto se consulta una vez y se guarda en caché.
		this._groupCache = this._groupCache || {};
		if (this.state.enrollments.some((e) => e.group === name && e.in_group)) return true;
		if (!(name in this._groupCache)) {
			this._groupCache[name] = false;
			frappe.db.exists('Student Group', name).then((ok) => {
				if (ok) {
					this._groupCache[name] = true;
					if (this.state.step === 1) this.render();
				}
			});
		}
		return this._groupCache[name];
	}

	// ------------------------------------------------------------------ paso 3: planes

	prepare_plans() {
		const s = this.state;
		const list = this.selectedEnrollments();
		const programs = this.programsOf(list).filter((p) => !s.options[p]);
		const year = (s.termInfo || {}).academic_year;
		const pDate = s.startDate
			? Promise.resolve(s.startDate)
			: this.call('default_start_date', { academic_term: s.term });
		const pOpts = programs.length
			? this.call('get_plan_options', { programs, academic_year: year })
			: Promise.resolve({});

		Promise.all([pDate, pOpts]).then(([date, opts]) => {
			s.startDate = s.startDate || date;
			Object.assign(s.options, opts || {});
			list.forEach((e) => {
				const opt = s.options[e.program] || { fee_structures: [], default_installments: 12 };
				const row = s.rows[e.program_enrollment] || {};
				if (!row.fee_structure && opt.fee_structures.length === 1) row.fee_structure = opt.fee_structures[0].name;
				row.installments = row.installments || opt.default_installments;
				if (!row.customDate) row.start_date = s.startDate;
				s.rows[e.program_enrollment] = row;
			});
			if (s.step === 2) this.render();
		});
	}

	simKey(row) {
		return [row.fee_structure, row.installments, row.start_date, this.state.interest].join('|');
	}

	render_plans($body) {
		const s = this.state;
		const all = this.selectedEnrollments();
		const list = all.filter((e) => !e.has_plan);
		if (!s.startDate) {
			$body.html(`<div class="aw-empty">${__('Cargando becas…')}</div>`);
			return;
		}
		const termStart = (s.termInfo || {}).term_start_date;

		let html = `
			<div class="aw-card aw-filters">
				<label>${__('Inicio del plan (Inscripción)')}
					<input type="date" class="form-control input-sm aw-start" value="${this.esc(s.startDate)}"></label>
				<label class="aw-check"><input type="checkbox" class="aw-interest" ${s.interest ? 'checked' : ''}> ${__('Con interés')}</label>
				<div class="text-muted small aw-grow">${__('Por defecto 2 meses antes del inicio del periodo ({0}): Inscripción, Traducción y equivalencia, y la cuota 1 cae al iniciar clases. Cámbiala para planes atrasados.', [frappe.datetime.str_to_user(termStart)])}</div>
			</div>`;
		if (all.length > list.length) {
			html += `<p class="text-muted small">${__('{0} estudiante(s) ya tienen plan: no se les crea otro.', [all.length - list.length])}</p>`;
		}

		const byProgram = {};
		list.forEach((e) => (byProgram[e.program] = byProgram[e.program] || []).push(e));

		Object.keys(byProgram).forEach((program) => {
			const opt = s.options[program] || { fee_structures: [], default_installments: 12 };
			const fsOptions = (selected) =>
				`<option value="">${__('Elegir beca…')}</option>` +
				opt.fee_structures
					.map((f) => `<option value="${this.esc(f.name)}" ${f.name === selected ? 'selected' : ''}>${this.esc(f.label)}</option>`)
					.join('');
			const mix = {};
			byProgram[program].forEach((e) => {
				const fs = (s.rows[e.program_enrollment] || {}).fee_structure;
				const label = fs ? (opt.fee_structures.find((f) => f.name === fs) || {}).label : __('Sin beca');
				mix[label] = (mix[label] || 0) + 1;
			});

			html += `<div class="aw-card">
				<div class="aw-card-head">
					<span><b>${this.esc(program)}</b> <span class="text-muted small">${opt.level || ''} · ${__('{0} cuotas por defecto', [opt.default_installments])}</span></span>
					<span class="aw-mix">${Object.entries(mix).map(([k, v]) => `<span class="indicator-pill gray">${v} × ${this.esc(k)}</span>`).join(' ')}</span>
				</div>`;

			if (!opt.fee_structures.length) {
				html += `<div class="aw-banner is-danger">${__('No hay Fee Structures validadas para este programa en {0}. Créalas antes de continuar.', [this.esc((s.termInfo || {}).academic_year)])}</div></div>`;
				return;
			}

			html += `
				<div class="aw-bulk">
					<span class="text-muted small">${__('Asignar a los marcados:')}</span>
					<select class="form-control input-xs aw-bulk-fs" data-program="${this.esc(program)}">${fsOptions('')}</select>
					<input type="number" min="1" max="60" class="form-control input-xs aw-bulk-inst" placeholder="${__('Cuotas')}" data-program="${this.esc(program)}">
					<button class="btn btn-default btn-xs aw-bulk-apply" data-program="${this.esc(program)}">${__('Aplicar')}</button>
				</div>
				<table class="aw-table">
					<thead><tr>
						<th><input type="checkbox" class="aw-mark-all" data-program="${this.esc(program)}"></th>
						<th>${__('Estudiante')}</th><th>${__('Beca')}</th><th>${__('Cuotas')}</th><th>${__('Inicio')}</th><th class="text-right">${__('Simulación')}</th>
					</tr></thead><tbody>`;

			byProgram[program].forEach((e) => {
				const pe = e.program_enrollment;
				const row = s.rows[pe] || {};
				const isException = row.installments && +row.installments !== +opt.default_installments;
				html += `<tr data-pe="${this.esc(pe)}">
					<td><input type="checkbox" class="aw-mark" data-program="${this.esc(program)}"></td>
					<td>${this.esc(e.student_name)}</td>
					<td><select class="form-control input-xs aw-fs">${fsOptions(row.fee_structure)}</select></td>
					<td><input type="number" min="1" max="60" class="form-control input-xs aw-inst" value="${row.installments || ''}">
						${isException ? `<span class="text-warning small">${__('Excepción')}</span>` : ''}</td>
					<td><input type="date" class="form-control input-xs aw-date" value="${this.esc(row.start_date || '')}"></td>
					<td class="text-right aw-sim">${this.simCell(row)}</td>
				</tr>`;
			});
			html += `</tbody></table></div>`;
		});

		$body.html(html);
		this.bind_plans($body);
		this.refresh_sims();
	}

	simCell(row) {
		if (!row.fee_structure) return `<span class="text-muted small">—</span>`;
		const sim = this.state.sims[this.simKey(row)];
		if (!sim) return `<span class="text-muted small">${__('Calculando…')}</span>`;
		if (sim.error) return `<span class="text-danger small">${__('No se pudo simular')}</span>`;
		return `<b>${sim.installments} × ${this.money(sim.installment_amount)}</b>
			<div class="text-muted small">${__('Total')} ${this.money(sim.total)} · <a class="aw-schedule">${__('ver calendario')}</a></div>`;
	}

	bind_plans($body) {
		const s = this.state;
		const rowOf = (el) => s.rows[$(el).closest('tr').data('pe')];
		$body.find('.aw-start').on('change', (e) => {
			s.startDate = e.target.value;
			Object.values(s.rows).forEach((r) => !r.customDate && (r.start_date = s.startDate));
			this.render();
		});
		$body.find('.aw-interest').on('change', (e) => {
			s.interest = e.target.checked ? 1 : 0;
			this.render();
		});
		$body.find('.aw-fs').on('change', (e) => {
			rowOf(e.target).fee_structure = e.target.value;
			this.render();
		});
		$body.find('.aw-inst').on('change', (e) => {
			rowOf(e.target).installments = Math.max(1, cint(e.target.value));
			this.render();
		});
		$body.find('.aw-date').on('change', (e) => {
			const r = rowOf(e.target);
			r.start_date = e.target.value || s.startDate;
			r.customDate = !!e.target.value && e.target.value !== s.startDate;
			this.render();
		});
		$body.find('.aw-mark-all').on('change', (e) => {
			$body.find(`.aw-mark[data-program="${CSS.escape($(e.target).data('program'))}"]`).prop('checked', e.target.checked);
		});
		$body.find('.aw-bulk-apply').on('click', (e) => {
			const program = $(e.target).data('program');
			const sel = CSS.escape(program);
			const fs = $body.find(`.aw-bulk-fs[data-program="${sel}"]`).val();
			const inst = cint($body.find(`.aw-bulk-inst[data-program="${sel}"]`).val());
			const $marked = $body.find(`.aw-mark[data-program="${sel}"]:checked`);
			if (!$marked.length) {
				frappe.show_alert({ message: __('Marca al menos un estudiante'), indicator: 'orange' });
				return;
			}
			$marked.each((_, el) => {
				const r = rowOf(el);
				if (fs) r.fee_structure = fs;
				if (inst > 0) r.installments = inst;
			});
			this.render();
		});
		$body.find('.aw-schedule').on('click', (e) => this.show_schedule(rowOf(e.target)));
	}

	refresh_sims() {
		const s = this.state;
		const pending = {};
		this.selectedEnrollments().forEach((e) => {
			const row = s.rows[e.program_enrollment];
			if (row && row.fee_structure && row.installments && row.start_date) {
				const key = this.simKey(row);
				if (!(key in s.sims)) pending[key] = row;
			}
		});
		Object.entries(pending).forEach(([key, row]) => {
			s.sims[key] = null;
			this.call('simulate_plan', {
				fee_structure: row.fee_structure,
				installments: row.installments,
				start_date: row.start_date,
				apply_interest: s.interest,
			}).then((sim) => {
				s.sims[key] = sim || { error: true };
				if (s.step !== 2) return;
				this.$root.find('tr[data-pe]').each((_, tr) => {
					const r = s.rows[$(tr).data('pe')];
					if (r && this.simKey(r) === key) {
						$(tr).find('.aw-sim').html(this.simCell(r));
						$(tr).find('.aw-schedule').on('click', () => this.show_schedule(r));
					}
				});
			}).catch(() => {
				s.sims[key] = { error: true };
				if (s.step === 2) this.render();
			});
		});
	}

	show_schedule(row) {
		const sim = this.state.sims[this.simKey(row)];
		if (!sim) return;
		const d = new frappe.ui.Dialog({ title: __('Calendario · {0}', [sim.beca]), size: 'large' });
		d.$body.html(`
			<div class="aw-metrics">
				${this.metric(__('Costo de programa'), this.money(sim.program_cost))}
				${this.metric(__('Beca'), this.money(sim.discount))}
				${this.metric(__('Cuota'), this.money(sim.installment_amount))}
				${this.metric(__('Total del plan'), this.money(sim.total))}
			</div>
			<table class="aw-table"><thead><tr><th>${__('Concepto')}</th><th>${__('Vence')}</th><th class="text-right">${__('Monto')}</th></tr></thead>
			<tbody>${sim.schedule.map((r) => `<tr><td>${this.esc(r.term)}</td><td>${frappe.datetime.str_to_user(r.due_date)}</td><td class="text-right">${this.money(r.amount)}</td></tr>`).join('')}</tbody></table>`);
		d.show();
	}

	// ------------------------------------------------------------------ paso 4: crear y EA

	render_create($body) {
		const s = this.state;
		const list = this.selectedEnrollments();
		const groups = [...new Set(list.map((e) => e.group))];
		const toCreate = list.filter((e) => !e.has_plan).length;

		let html = '';
		if (!s.done && !s.running) {
			html += `<div class="aw-card">
				<p>${__('Se van a crear o actualizar <b>{0} grupo(s)</b> y crear <b>{1} plan(es)</b> (Fee Schedule y Fees). Al terminar podrás descargar los Enrollment Agreements.', [groups.length, toCreate])}</p>
				${list.length - toCreate ? `<p class="text-muted small">${__('{0} estudiante(s) ya tienen plan: no se les crea otro, solo se incluye su EA.', [list.length - toCreate])}</p>` : ''}
				<button class="btn btn-primary btn-sm aw-run">${__('Crear grupos y planes')}</button>
			</div>`;
		} else {
			const done = Object.keys(s.results).length;
			const pct = Math.round((done / list.length) * 100);
			const ok = Object.values(s.results).filter((r) => r.ea_fee).length;
			html += `<div class="aw-card">
				<div class="aw-card-head">
					<span>${s.running ? __('Creando planes… {0} de {1}', [done, list.length]) : __('Listo: {0} de {1} con Enrollment Agreement', [ok, list.length])}</span>
					${!s.running && ok ? `<button class="btn btn-primary btn-sm aw-download-all">${frappe.utils.icon('down-arrow', 'sm')} ${__('Descargar todos (un PDF)')}</button>` : ''}
				</div>
				<div class="progress" style="height:6px;margin:0"><div class="progress-bar" style="width:${pct}%"></div></div>
			</div>`;
		}

		html += `<div class="aw-card"><table class="aw-table"><thead><tr>
			<th>${__('Estudiante')}</th><th>${__('Programa')}</th><th>${__('Beca')}</th><th>${__('Estado')}</th><th class="text-right">EA</th>
		</tr></thead><tbody>`;
		list.forEach((e) => {
			const r = s.results[e.program_enrollment];
			const row = s.rows[e.program_enrollment] || {};
			const opt = s.options[e.program] || { fee_structures: [] };
			const beca = (opt.fee_structures.find((f) => f.name === row.fee_structure) || {}).label || '—';
			let status = `<span class="indicator-pill gray">${__('Pendiente')}</span>`;
			if (r && r.status === 'ok') status = `<span class="indicator-pill green">${__('Plan creado')}</span>`;
			if (r && r.status === 'skipped') status = `<span class="indicator-pill blue">${__('Ya tenía plan')}</span>`;
			if (r && r.status === 'error') status = `<span class="indicator-pill red" title="${this.esc(r.detail)}">${__('Error')}</span><div class="text-danger small">${this.esc(r.detail)}</div>`;
			html += `<tr><td>${this.esc(e.student_name)}</td><td class="small">${this.esc(e.program)}</td><td>${this.esc((r && r.status === 'skipped') || (!r && e.has_plan) ? '—' : beca)}</td><td>${status}</td>
				<td class="text-right">${r && r.ea_fee ? `<a class="btn btn-default btn-xs" target="_blank" href="${this.pdfUrl([r.ea_fee])}">PDF</a>` : ''}</td></tr>`;
		});
		html += `</tbody></table></div>`;

		$body.html(html);
		$body.find('.aw-run').on('click', () => this.run());
		$body.find('.aw-download-all').on('click', () => {
			const fees = Object.values(s.results).map((r) => r.ea_fee).filter(Boolean);
			window.open(this.pdfUrl(fees));
		});
	}

	pdfUrl(fees) {
		const format = encodeURIComponent('Matrícula');
		if (fees.length === 1) {
			return `/api/method/frappe.utils.print_format.download_pdf?doctype=Fees&name=${encodeURIComponent(fees[0])}&format=${format}`;
		}
		return `/api/method/frappe.utils.print_format.download_multi_pdf?doctype=Fees&name=${encodeURIComponent(JSON.stringify(fees))}&format=${format}`;
	}

	async run() {
		const s = this.state;
		const list = this.selectedEnrollments();
		s.running = true;
		s.results = {};
		this.render();
		try {
			await this.call('ensure_groups', {
				academic_term: s.term,
				program_enrollments: list.map((e) => e.program_enrollment),
			});
			list.forEach((e) => (e.in_group = true));
		} catch (err) {
			s.running = false;
			this.render();
			return;
		}

		for (const e of list) {
			const row = s.rows[e.program_enrollment] || {};
			try {
				s.results[e.program_enrollment] = await this.call('generate_plan', {
					program_enrollment: e.program_enrollment,
					fee_structure: row.fee_structure,
					installments: row.installments,
					start_date: row.start_date,
					apply_interest: s.interest,
				});
				if (s.results[e.program_enrollment].ea_fee) e.has_plan = true;
			} catch (err) {
				s.results[e.program_enrollment] = { status: 'error', detail: __('Revisa el Error Log') };
			}
			this.render();
		}
		s.running = false;
		s.done = true;
		this.render();
	}

	// ------------------------------------------------------------------ estilos

	inject_styles() {
		if (document.getElementById('aw-styles')) return;
		$(`<style id="aw-styles">
			.aw { max-width: 1100px; margin: 0 auto; padding-bottom: 2rem; }
			.aw-stepper { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin: 8px 0 16px; }
			.aw-step { display: flex; align-items: center; gap: 8px; padding: 10px 12px; border-radius: var(--border-radius-md); border: 1px solid var(--border-color); background: var(--card-bg); color: var(--text-muted); text-align: left; font-size: var(--text-sm); }
			.aw-step.is-active { border-color: var(--primary); color: var(--text-color); font-weight: 600; }
			.aw-step.is-done { color: var(--green-600); }
			.aw-step:disabled { opacity: 1; cursor: default; }
			.aw-num { display: inline-flex; width: 20px; height: 20px; border-radius: 50%; align-items: center; justify-content: center; background: var(--control-bg); font-size: 11px; }
			.aw-card { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: var(--border-radius-lg); padding: 14px 16px; margin-bottom: 12px; }
			.aw-card-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
			.aw-filters { display: flex; align-items: flex-end; gap: 16px; flex-wrap: wrap; }
			.aw-filters label { margin: 0; font-size: var(--text-sm); color: var(--text-muted); }
			.aw-filters select, .aw-filters input[type=date] { min-width: 200px; margin-top: 4px; }
			.aw-check { display: flex; align-items: center; gap: 8px; margin: 0; cursor: pointer; font-weight: normal; }
			.aw-row { display: flex; align-items: center; gap: 10px; padding: 7px 0; border-top: 1px solid var(--border-color); }
			.aw-grow { flex: 1; }
			.aw-metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 12px; }
			.aw-metric { background: var(--control-bg); border-radius: var(--border-radius-md); padding: 10px 14px; font-size: var(--text-sm); color: var(--text-muted); }
			.aw-metric b { display: block; font-size: 20px; color: var(--text-color); font-weight: 600; }
			.aw-metric.is-warning b { color: var(--orange-600); }
			.aw-banner { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 14px; border-radius: var(--border-radius-md); margin-bottom: 12px; font-size: var(--text-sm); }
			.aw-banner.is-warning { background: var(--bg-orange); color: var(--text-on-orange); }
			.aw-banner.is-danger { background: var(--bg-red); color: var(--text-on-red); margin: 0; }
			.aw-empty { padding: 32px; text-align: center; color: var(--text-muted); }
			.aw-details summary { cursor: pointer; font-size: var(--text-sm); color: var(--text-muted); margin-top: 6px; }
			.aw-bulk { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
			.aw-bulk select { width: 180px; } .aw-bulk input { width: 90px; }
			.aw-table { width: 100%; font-size: var(--text-sm); }
			.aw-table th { color: var(--text-muted); font-weight: normal; padding: 6px; border-bottom: 1px solid var(--border-color); }
			.aw-table td { padding: 6px; border-bottom: 1px solid var(--border-color); vertical-align: middle; }
			.aw-table td input[type=number] { width: 70px; display: inline-block; }
			.aw-table td input[type=date] { width: 140px; }
			.aw-table td select { min-width: 140px; }
			.aw-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding-top: 8px; }
			.aw-schedule { cursor: pointer; }
			@media (max-width: 768px) { .aw-stepper { grid-template-columns: repeat(2, minmax(0, 1fr)); } .aw-table { display: block; overflow-x: auto; } }
		</style>`).appendTo(document.head);
	}
}
