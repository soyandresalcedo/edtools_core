# Copyright (c) 2026, EdTools and contributors
# Asistente de admisiones: cohorte → grupos → planes financieros → Enrollment Agreements.
# Lo usa la página /app/admissions-wizard. Reutiliza la lógica de la Student Financial Tool
# (calculate_special_plan + generate_batch_records) para no duplicar el cálculo de planes.

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import add_months, cint, cstr, flt, getdate

from edtools_core.api import (
	CAPITAL_CATEGORIES,
	CAT_COSTO_PROGRAMA,
	CAT_GRADUACION,
	CAT_INSCRIPCION,
	CAT_INTERESES,
	CAT_TRADUCCION,
	_classify_fee_components,
	calculate_special_plan,
	generate_batch_records,
)

EA_PRINT_FORMAT = "Matrícula"

# Cuotas de capital por defecto según el nivel del programa (se pueden cambiar por estudiante).
DEFAULT_INSTALLMENTS = {"MS": 14, "AS": 21, "BS": 40}
FALLBACK_INSTALLMENTS = 12

# El plan arranca 2 meses antes del periodo: Inscripción (mes 0), TyE (mes 1), cuota 1 = inicio del periodo.
MONTHS_BEFORE_TERM = 2


def _parse(val):
	if isinstance(val, str):
		return json.loads(val) if val.strip() else None
	return val


# Programas cuyo nombre no lleva el prefijo (MS)/(AS)/(BS).
PROGRAM_LEVEL_OVERRIDES = {
	"Marketing and Mass Media Communication": "MS",
	"MARKETING": "MS",
}


def _program_level(program: str) -> str | None:
	if program in PROGRAM_LEVEL_OVERRIDES:
		return PROGRAM_LEVEL_OVERRIDES[program]
	text = cstr(program).lower()
	if text.startswith("(ms)") or "master" in text or "mba" in text or "maestr" in text:
		return "MS"
	if text.startswith("(as)") or "associate" in text or "técnico" in text:
		return "AS"
	if text.startswith("(bs)") or "bachelor" in text or "licenciatura" in text:
		return "BS"
	return None


def group_name_for(program: str, academic_term: str) -> str:
	return f"{program} - {academic_term}"


def _has_plan(program_enrollment: str) -> bool:
	return bool(
		frappe.db.exists("Fees", {"program_enrollment": program_enrollment, "docstatus": 1})
	)


# ---------------------------------------------------------------------------
# Paso 1: cohorte
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_terms():
	return frappe.get_all(
		"Academic Term",
		fields=["name", "academic_year", "term_start_date", "term_end_date"],
		order_by="term_start_date desc",
		limit_page_length=40,
	)


@frappe.whitelist()
def get_cohort(academic_term: str):
	"""Matrículas del periodo: validadas (con estado de grupo/plan) y borradores pendientes."""
	frappe.only_for(("System Manager", "Education Manager", "Academics User", "Accounts User"))
	term = frappe.db.get_value(
		"Academic Term", academic_term, ["name", "academic_year", "term_start_date"], as_dict=True
	)
	if not term:
		frappe.throw(_("Academic Term {0} not found").format(academic_term))

	rows = frappe.get_all(
		"Program Enrollment",
		filters={"academic_term": academic_term, "docstatus": ["<", 2]},
		fields=["name", "student", "student_name", "program", "academic_year", "docstatus"],
		order_by="program asc, student_name asc",
		limit_page_length=0,
	)

	group_names = {group_name_for(r.program, academic_term) for r in rows}
	members = {}
	if group_names:
		for m in frappe.get_all(
			"Student Group Student",
			filters={"parent": ["in", list(group_names)], "active": 1},
			fields=["parent", "student"],
			limit_page_length=0,
		):
			members.setdefault(m.parent, set()).add(m.student)

	enrollments, drafts = [], []
	for r in rows:
		if r.docstatus == 0:
			drafts.append({"name": r.name, "student_name": r.student_name, "program": r.program})
			continue
		group = group_name_for(r.program, academic_term)
		enrollments.append(
			{
				"program_enrollment": r.name,
				"student": r.student,
				"student_name": r.student_name,
				"program": r.program,
				"academic_year": r.academic_year,
				"group": group,
				"in_group": r.student in members.get(group, set()),
				"has_plan": _has_plan(r.name),
			}
		)

	return {"term": term, "enrollments": enrollments, "drafts": drafts}


@frappe.whitelist()
def validate_enrollments(names):
	"""Valida (submit) matrículas en borrador. Devuelve el resultado por matrícula."""
	frappe.only_for(("System Manager", "Education Manager", "Academics User"))
	results = []
	for name in _parse(names) or []:
		try:
			doc = frappe.get_doc("Program Enrollment", name)
			if doc.docstatus == 0:
				doc.submit()
				frappe.db.commit()
			results.append({"name": name, "ok": True})
		except Exception as e:
			frappe.db.rollback()
			results.append({"name": name, "ok": False, "error": cstr(e)[:300]})
	return results


# ---------------------------------------------------------------------------
# Paso 2: grupos
# ---------------------------------------------------------------------------


@frappe.whitelist()
def ensure_groups(academic_term: str, program_enrollments):
	"""Crea (si no existen) los grupos «Programa - Periodo» y agrega a los estudiantes que falten."""
	frappe.only_for(("System Manager", "Education Manager", "Academics User"))
	pes = frappe.get_all(
		"Program Enrollment",
		filters={"name": ["in", _parse(program_enrollments) or []], "docstatus": 1},
		fields=["name", "student", "student_name", "program", "academic_year"],
		order_by="student_name asc",
		limit_page_length=0,
	)
	by_group = {}
	for pe in pes:
		by_group.setdefault(group_name_for(pe.program, academic_term), []).append(pe)

	summary = []
	for group_name, members in by_group.items():
		created = not frappe.db.exists("Student Group", group_name)
		if created:
			sg = frappe.new_doc("Student Group")
			sg.student_group_name = group_name
			sg.group_based_on = "Batch"
			sg.program = members[0].program
			sg.academic_year = members[0].academic_year
			sg.academic_term = academic_term
		else:
			sg = frappe.get_doc("Student Group", group_name)

		current = {d.student for d in sg.students}
		added = 0
		for pe in members:
			if pe.student in current:
				continue
			sg.append(
				"students",
				{
					"student": pe.student,
					"student_name": pe.student_name,
					"group_roll_number": len(sg.students) + 1,
					"active": 1,
				},
			)
			added += 1
		try:
			if created or added:
				sg.save(ignore_permissions=True)
			frappe.db.commit()
			summary.append({"group": group_name, "created": created, "added": added})
		except Exception as e:
			frappe.db.rollback()
			frappe.log_error(title=f"Asistente de admisiones - grupo {group_name}", message=frappe.get_traceback())
			frappe.clear_messages()
			summary.append({"group": group_name, "error": _clean_error(e), "students": [m.name for m in members]})

	frappe.db.commit()
	return summary


# ---------------------------------------------------------------------------
# Paso 3: becas (Fee Structures) y simulación
# ---------------------------------------------------------------------------


def _beca_label(fs_doc) -> str:
	for field in ("beca", "custom_beca"):
		if fs_doc.get(field):
			return cstr(fs_doc.get(field))
	for c in fs_doc.components:
		if flt(c.amount) < 0:
			return cstr(c.fees_category)
	return _("Sin beca")


@frappe.whitelist()
def get_plan_options(programs, academic_year: str):
	"""Por programa: Fee Structures con costo de programa (una por beca) y cuotas por defecto."""
	out = {}
	for program in _parse(programs) or []:
		options = []
		for name in frappe.get_all(
			"Fee Structure",
			filters={"program": program, "academic_year": academic_year, "docstatus": 1},
			pluck="name",
			order_by="name asc",
		):
			fs = frappe.get_doc("Fee Structure", name)
			if not any(c.fees_category in CAPITAL_CATEGORIES for c in fs.components):
				continue  # p. ej. «Certificado de estudios»: no es un plan de matrícula
			options.append(
				{
					"name": fs.name,
					"label": _beca_label(fs),
					"total": flt(sum(flt(c.amount) for c in fs.components), 2),
				}
			)
		level = _program_level(program)
		options.sort(key=lambda o: o["label"])
		out[program] = {
			"level": level,
			"default_installments": DEFAULT_INSTALLMENTS.get(level, FALLBACK_INSTALLMENTS),
			"fee_structures": options,
		}
	return out


def _legacy_schedule(components, installments: int, start_date):
	"""Plan antiguo de la CUC: capital + Traducción y equivalencia + Graduación repartidos en
	partes iguales en las N cuotas (sin interés). La Inscripción sigue aparte en el mes 0.
	Ej.: MS $13,440 con beca 90% → 1,344 + 120 + 200 + 200 = 1,864 / 14 = $133.14."""
	insc, tye, grad, capital, optional = _classify_fee_components(components)
	n = cint(installments)
	if n < 1:
		frappe.throw(_("El número de cuotas debe ser al menos 1."))
	start_date = getdate(start_date)
	schedule = []
	if insc > 0:
		schedule.append({"term": "Pago Inicial 1 (Inscripción)", "due_date": start_date, "amount": flt(insc, 2), "type": "Inscripcion"})
	for cat, desc, amount in optional:
		if amount > 0:
			schedule.append({
				"term": desc or cat, "due_date": add_months(start_date, MONTHS_BEFORE_TERM), "amount": flt(amount, 2),
				"type": "Otros", "fees_category": cat, "description": desc or cat,
			})

	buckets = [(CAT_COSTO_PROGRAMA, capital), (CAT_TRADUCCION, tye), (CAT_GRADUACION, grad)]
	total = flt(capital + tye + grad, 2)
	if total <= 0:
		return schedule
	cuota = flt(total / n, 2)
	assigned = {cat: 0.0 for cat, _x in buckets}
	for i in range(1, n + 1):
		is_last = i == n
		amount = flt(total - cuota * (n - 1), 2) if is_last else cuota
		parts, used = [], 0.0
		for j, (cat, cat_total) in enumerate(buckets):
			if cat_total <= 0:
				continue
			if is_last:
				part = flt(cat_total - assigned[cat], 2)
			elif j == len(buckets) - 1 or all(t <= 0 for _c, t in buckets[j + 1 :]):
				part = flt(amount - used, 2)
			else:
				part = flt(amount * cat_total / total, 2)
			assigned[cat] += part
			used += part
			parts.append({"fees_category": cat, "amount": part})
		schedule.append({
			"term": f"Cuota {i}/{n}", "due_date": add_months(start_date, MONTHS_BEFORE_TERM + i - 1),
			"amount": amount, "type": "Mixta", "parts": parts,
		})
	return schedule


CAPITAL_TYPES = ("Capital", "Capital+Graduacion", "Mixta")
SCHEDULE_TYPES = ("Inscripcion", "Traduccion", "Otros") + CAPITAL_TYPES


def _schedule_sums(schedule) -> dict:
	"""Total por categoría de un calendario (para cuadrar los componentes del Fee Schedule)."""
	sums = {}

	def add(cat, amount):
		sums[cat] = flt(sums.get(cat, 0) + flt(amount), 2)

	for r in schedule:
		t = r.get("type")
		if t == "Inscripcion":
			add(CAT_INSCRIPCION, r["amount"])
		elif t == "Traduccion":
			add(CAT_TRADUCCION, r["amount"])
		elif t == "Otros":
			add(r.get("fees_category") or "Otros", r["amount"])
		elif t == "Capital+Graduacion":
			add(CAT_GRADUACION, r.get("graduacion_amount"))
			add(CAT_COSTO_PROGRAMA, flt(r["amount"]) - flt(r.get("graduacion_amount")))
		elif t == "Mixta":
			for part in r.get("parts") or []:
				add(part.get("fees_category"), part.get("amount"))
		else:
			add(CAT_COSTO_PROGRAMA, r["amount"])
	return sums


def _normalize_custom_schedule(rows) -> list:
	"""Valida el calendario editado en la página: fechas, montos y tipos conocidos."""
	if not rows:
		frappe.throw(_("El calendario personalizado quedó vacío."))
	out = []
	for i, r in enumerate(rows, 1):
		t = cstr(r.get("type"))
		amount = flt(r.get("amount"), 2)
		if t not in SCHEDULE_TYPES:
			frappe.throw(_("Fila {0}: tipo de cuota no válido.").format(i))
		if not r.get("due_date"):
			frappe.throw(_("Fila {0}: falta la fecha.").format(i))
		if amount <= 0:
			frappe.throw(_("Fila {0}: el monto debe ser mayor que cero.").format(i))
		row = {"term": cstr(r.get("term")) or f"Cuota {i}", "due_date": getdate(r.get("due_date")), "amount": amount, "type": t}
		if t == "Otros":
			row["fees_category"] = cstr(r.get("fees_category")) or "Otros"
			row["description"] = cstr(r.get("description")) or row["term"]
		if t == "Capital+Graduacion":
			grad = min(flt(r.get("graduacion_amount"), 2), amount)
			if grad > 0:
				row["graduacion_amount"] = grad
			else:  # sin graduación: cuota normal (si no, generate_batch_records pondría 200 por defecto)
				row["type"] = "Capital"
				row["term"] = row["term"].replace(" + Graduación", "")
		if t == "Mixta":
			parts = [p for p in (r.get("parts") or []) if flt(p.get("amount")) > 0]
			base = sum(flt(p.get("amount")) for p in parts)
			if base <= 0:
				parts = [{"fees_category": CAT_COSTO_PROGRAMA, "amount": amount}]
			else:  # el monto cambió: repartir proporcionalmente; el redondeo va a la última parte
				scaled, used = [], 0.0
				for k, p in enumerate(parts):
					part = flt(amount - used, 2) if k == len(parts) - 1 else flt(amount * flt(p.get("amount")) / base, 2)
					used += part
					scaled.append({"fees_category": cstr(p.get("fees_category")), "amount": part})
				parts = scaled
			row["parts"] = parts
		out.append(row)
	if not any(r["type"] in CAPITAL_TYPES for r in out):
		frappe.throw(_("El plan debe tener al menos una cuota."))
	return sorted(out, key=lambda r: r["due_date"])


def _build_plan(fee_structure: str, installments, start_date, apply_interest, legacy=0, custom_schedule=None):
	fs = frappe.get_doc("Fee Structure", fee_structure)
	components = [
		{"fees_category": c.fees_category, "description": c.description, "amount": flt(c.amount)}
		for c in fs.components
	]
	if cint(legacy):
		schedule, interest = _legacy_schedule(components, installments, start_date), 0.0
	else:
		plan = calculate_special_plan(components, cint(installments), getdate(start_date), cint(apply_interest))
		schedule, interest = plan["schedule"], flt(plan.get("total_interest"))
	# Igual que la Student Financial Tool: el componente «Intereses» lleva el interés calculado.
	row = next((c for c in components if c["fees_category"] == CAT_INTERESES), None)
	if row:
		row["amount"] = interest
	elif interest > 0:
		components.append({"fees_category": CAT_INTERESES, "description": "Financial Interest", "amount": interest})

	if custom_schedule:
		custom = _normalize_custom_schedule(_parse(custom_schedule))
		# Cuadrar los componentes con lo que realmente se cobra (cuota eliminada, monto editado, etc.).
		before, after = _schedule_sums(schedule), _schedule_sums(custom)
		for cat in set(before) | set(after):
			delta = flt(after.get(cat, 0) - before.get(cat, 0), 2)
			if not delta:
				continue
			comp = next((c for c in components if c["fees_category"] == cat), None)
			if comp:
				comp["amount"] = flt(comp["amount"] + delta, 2)
			else:
				components.append({"fees_category": cat, "description": cat, "amount": delta})
		schedule = custom
	return fs, components, schedule


@frappe.whitelist()
def simulate_plan(fee_structure: str, installments, start_date, apply_interest=0, legacy=0):
	fs, components, schedule = _build_plan(fee_structure, installments, start_date, apply_interest, legacy)
	program_cost = sum(flt(c["amount"]) for c in components if c["fees_category"] == CAT_COSTO_PROGRAMA)
	discount = sum(flt(c["amount"]) for c in components if flt(c["amount"]) < 0)
	capital = [r for r in schedule if r["type"] in CAPITAL_TYPES]
	return {
		"beca": _beca_label(fs),
		"program_cost": flt(program_cost, 2),
		"discount": flt(discount, 2),
		"installment_amount": flt(capital[0]["amount"], 2) if capital else 0,
		"installments": len(capital),
		"first_due": schedule[0]["due_date"] if schedule else None,
		"last_due": schedule[-1]["due_date"] if schedule else None,
		"total": flt(sum(flt(r["amount"]) for r in schedule), 2),
		"schedule": schedule,
	}


@frappe.whitelist()
def default_start_date(academic_term: str):
	start = frappe.db.get_value("Academic Term", academic_term, "term_start_date")
	return add_months(getdate(start), -MONTHS_BEFORE_TERM) if start else None


# ---------------------------------------------------------------------------
# Paso 4: generar planes y Enrollment Agreements
# ---------------------------------------------------------------------------


@frappe.whitelist()
def generate_plan(
	program_enrollment: str, fee_structure: str, installments, start_date, apply_interest=0, legacy=0, schedule=None
):
	"""Crea el plan de un estudiante (Fee Schedule + Fees). Se llama una vez por estudiante
	desde la página para mostrar progreso y no pasar el timeout de Gunicorn con planes de 40 cuotas."""
	frappe.only_for(("System Manager", "Education Manager", "Accounts User"))
	try:
		return _generate_plan(program_enrollment, fee_structure, installments, start_date, apply_interest, legacy, schedule)
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(title=f"Asistente de admisiones - {program_enrollment}", message=frappe.get_traceback())
		frappe.db.commit()  # conservar el Error Log
		frappe.clear_messages()
		return {"status": "error", "detail": _clean_error(e)}


def _clean_error(e) -> str:
	from frappe.utils import strip_html

	return strip_html(cstr(e)).strip()[:300] or _("Error inesperado. Revisa el Error Log.")


def _generate_plan(program_enrollment, fee_structure, installments, start_date, apply_interest, legacy=0, schedule=None):
	if not fee_structure:
		frappe.throw(_("Falta la beca."))
	if not start_date:
		frappe.throw(_("Falta la fecha de inicio."))
	if not 1 <= cint(installments) <= 60:
		frappe.throw(_("Las cuotas deben estar entre 1 y 60."))
	pe = frappe.db.get_value(
		"Program Enrollment",
		program_enrollment,
		["name", "student", "program", "academic_year", "academic_term", "docstatus"],
		as_dict=True,
	)
	if not pe or pe.docstatus != 1:
		frappe.throw(_("La matrícula {0} no está validada.").format(program_enrollment))
	if _has_plan(pe.name):
		return {"status": "skipped", "detail": _("Ya tiene plan"), "ea_fee": first_fee(pe.name)}

	fs = frappe.db.get_value("Fee Structure", fee_structure, ["program", "academic_year", "docstatus"], as_dict=True)
	if not fs or fs.docstatus != 1:
		frappe.throw(_("La beca {0} no existe o no está validada.").format(fee_structure))
	if fs.program != pe.program:
		frappe.throw(_("La beca {0} no corresponde al programa {1}.").format(fee_structure, pe.program))
	if fs.academic_year != pe.academic_year:
		frappe.throw(
			_("La beca es del año {0} y la matrícula del año {1}.").format(fs.academic_year, pe.academic_year)
		)

	group = group_name_for(pe.program, pe.academic_term)
	if not frappe.db.exists("Student Group Student", {"parent": group, "student": pe.student, "active": 1}):
		frappe.throw(_("El estudiante no está en el grupo {0}.").format(group))

	_fs, components, plan_rows = _build_plan(fee_structure, installments, start_date, apply_interest, legacy, schedule)
	res = generate_batch_records(group, fee_structure, components, plan_rows, students=[pe.student])
	row = (res.get("results") or [{}])[0]
	if row.get("status_key") != "ok":
		frappe.db.rollback()
		return {"status": "error", "detail": row.get("detail") or _("Error desconocido")}
	frappe.db.commit()
	return {"status": "ok", "detail": row.get("detail"), "ea_fee": first_fee(pe.name)}


@frappe.whitelist()
def first_fee(program_enrollment: str):
	"""La Fee que se imprime como Enrollment Agreement (cualquiera del plan sirve: el formato
	lee el Fee Schedule); se toma la primera por fecha."""
	names = frappe.get_all(
		"Fees",
		filters={"program_enrollment": program_enrollment, "docstatus": 1},
		pluck="name",
		order_by="due_date asc, creation asc",
		limit_page_length=1,
	)
	return names[0] if names else None


@frappe.whitelist()
def get_ea_print_format():
	return EA_PRINT_FORMAT
