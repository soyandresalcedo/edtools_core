# Inyecta get_user_info (y get_student_info) en education.education.api para Student Portal.
# Education version-15 no tiene estos métodos; el frontend Vue (develop) sí los llama.

import json
import frappe


@frappe.whitelist()
def get_user_info():
	"""Compat con Student Portal Vue (education develop). Education v15 no lo tiene.
	Solo lee el usuario actual; el rol Student no tiene permiso en User, por eso ignore_permissions."""
	if frappe.session.user == "Guest":
		frappe.throw("Authentication failed", exc=frappe.AuthenticationError)
	users = frappe.db.get_list(
		"User",
		fields=["name", "email", "enabled", "user_image", "full_name", "user_type"],
		filters={"name": frappe.session.user},
		limit_page_length=1,
		ignore_permissions=True,
	)
	if not users:
		frappe.throw("User not found", exc=frappe.AuthenticationError)
	result = dict(users[0])
	result["session_user"] = True
	return result


def patch_education_api():
	"""Inyecta get_user_info y APIs del Student Portal en education.education.api (v15 puede no tenerlas)."""
	try:
		import education.education.api as edu_api
		edu_api.get_user_info = get_user_info
		# get_student_info: siempre usar nuestra versión para garantizar student_groups y current_program
		edu_api.get_student_info = get_student_info
		if not hasattr(edu_api, "get_school_abbr_logo"):
			edu_api.get_school_abbr_logo = get_school_abbr_logo
		# get_course_schedule_for_student: siempre nuestra versión (ignore_permissions + lógica unificada)
		edu_api.get_course_schedule_for_student = get_course_schedule_for_student
		if not hasattr(edu_api, "get_student_programs"):
			edu_api.get_student_programs = get_student_programs
		if not hasattr(edu_api, "get_student_grades"):
			edu_api.get_student_grades = get_student_grades
		edu_api.get_student_invoices = get_student_invoices
		# get_student_attendance: siempre usar nuestra versión (validación + ignore_permissions)
		edu_api.get_student_attendance = get_student_attendance
		if not hasattr(edu_api, "get_student_curriculum"):
			edu_api.get_student_curriculum = get_student_curriculum
	except Exception:
		pass


@frappe.whitelist()
def get_student_curriculum(student, program_enrollment=None):
	"""Devuelve el pensum del estudiante para un Program Enrollment: lista de cursos con estado (completed, in_progress, upcoming)."""
	if not student:
		return {}
	my_student = _get_current_user_student_name()
	if not my_student or my_student != student:
		return {}
	# Obtener Program Enrollment(s)
	pe_list = frappe.db.get_list(
		"Program Enrollment",
		filters={"student": student, "docstatus": 1},
		fields=["name", "program", "enrollment_date", "academic_year"],
		order_by="modified desc",
		ignore_permissions=True,
	)
	if not pe_list:
		return {"program_name": None, "program_enrollment": None, "courses": [], "summary": {"total": 0, "completed": 0, "in_progress": 0, "upcoming": 0}}
	# Elegir el enrollment
	if program_enrollment:
		pe = next((p for p in pe_list if p["name"] == program_enrollment), None)
		if not pe:
			pe = pe_list[0]
	else:
		pe = pe_list[0]
	program_name = pe.get("program")
	if not program_name:
		return {"program_name": None, "program_enrollment": pe["name"], "courses": [], "summary": {"total": 0, "completed": 0, "in_progress": 0, "upcoming": 0}}
	# Cursos del programa (Program Course) en orden
	program_doc = frappe.get_doc("Program", program_name)
	if not program_doc or not getattr(program_doc, "courses", None):
		return {
			"program_name": program_name,
			"program_enrollment": pe["name"],
			"enrollment_date": pe.get("enrollment_date"),
			"courses": [],
			"summary": {"total": 0, "completed": 0, "in_progress": 0, "upcoming": 0},
		}
	# Assessment Results del estudiante (para marcar completed).
	# Nota: no filtramos por program porque en algunas instalaciones el campo puede estar vacío o inconsistente;
	# el matching final se restringe a cursos que existan en el pensum (Program.courses).
	assessment_results = frappe.db.get_list(
		"Assessment Result",
		filters={"student": student, "docstatus": 1},
		fields=["course", "grade", "total_score", "maximum_score", "academic_term"],
		ignore_permissions=True,
	)
	results_by_course = {}
	for ar in assessment_results or []:
		c = ar.get("course")
		if c and c not in results_by_course:
			results_by_course[c] = ar
	# Course Enrollments del estudiante (para in_progress).
	# In progress se restringe al término actual (custom_academic_term) si existe.
	ce_meta = frappe.get_meta("Course Enrollment")
	has_custom_term = ce_meta.has_field("custom_academic_term")
	ce_fields = ["course", "enrollment_date", "program_enrollment", "modified"]
	if has_custom_term:
		ce_fields.append("custom_academic_term")
	ce_list = frappe.db.get_list(
		"Course Enrollment",
		filters={"student": student, "docstatus": 1},
		fields=ce_fields,
		order_by="modified desc",
		ignore_permissions=True,
	)
	current_term = None
	if has_custom_term:
		for ce in ce_list or []:
			term = (ce.get("custom_academic_term") or "").strip()
			if term:
				current_term = term
				break
	enrollments_by_course = {}
	for ce in ce_list or []:
		c = ce.get("course")
		if c and c not in enrollments_by_course:
			enrollments_by_course[c] = ce
	courses_out = []
	summary = {"completed": 0, "in_progress": 0, "upcoming": 0}
	for row in program_doc.courses:
		course_id = row.get("course")
		course_name = row.get("course_name") or course_id
		required = 1 if row.get("required") else 0
		ar = results_by_course.get(course_id)
		ce = enrollments_by_course.get(course_id)
		if ar:
			status = "completed"
			summary["completed"] += 1
			academic_term = ar.get("academic_term")
			grade = ar.get("grade")
			total_score = ar.get("total_score")
			maximum_score = ar.get("maximum_score")
			enrollment_date = ce.get("enrollment_date") if ce else None
		elif ce and (not current_term or not has_custom_term or (ce.get("custom_academic_term") or "").strip() == current_term):
			status = "in_progress"
			summary["in_progress"] += 1
			academic_term = ce.get("custom_academic_term") if has_custom_term else None
			grade = None
			total_score = None
			maximum_score = None
			enrollment_date = ce.get("enrollment_date")
		else:
			status = "upcoming"
			summary["upcoming"] += 1
			academic_term = None
			grade = None
			total_score = None
			maximum_score = None
			enrollment_date = None
		courses_out.append({
			"course": course_id,
			"course_name": course_name,
			"required": required,
			"status": status,
			"grade": grade,
			"total_score": total_score,
			"maximum_score": maximum_score,
			"academic_term": academic_term,
			"enrollment_date": enrollment_date,
		})
	summary["total"] = len(courses_out)
	return {
		"program_name": program_name,
		"program_enrollment": pe["name"],
		"enrollment_date": pe.get("enrollment_date"),
		"current_term": current_term,
		"courses": courses_out,
		"summary": summary,
	}


@frappe.whitelist()
def get_student_attendance(student, student_group):
	"""Compat con Student Portal Vue (Attendance). Valida estudiante, devuelve [] si grupo inválido, usa ignore_permissions."""
	if not student:
		return []
	my_student = _get_current_user_student_name()
	if not my_student or my_student != student:
		return []
	if not student_group or student_group.strip() in ("", "Select Student Group"):
		return []
	try:
		return frappe.db.get_list(
			"Student Attendance",
			filters={"student": student, "student_group": student_group, "docstatus": 1},
			fields=["date", "status", "name"],
			ignore_permissions=True,
		)
	except Exception:
		return []


def _get_current_enrollment_edtools(student_name):
	"""Inscripción activa del estudiante (programa actual). Usado para rellenar student_groups."""
	try:
		from frappe.utils import getdate, today
		# Enrollments con año académico vigente (year_end_date >= hoy) o el más reciente
		enrollments = frappe.db.get_list(
			"Program Enrollment",
			filters={"student": student_name, "docstatus": 1},
			fields=["name", "program", "student_name", "academic_year", "academic_term", "student_batch_name", "student_category"],
			order_by="modified desc",
			limit_page_length=10,
			ignore_permissions=True,
		)
		if not enrollments:
			return None
		# Preferir el que tenga año académico vigente
		for pe in enrollments:
			ay_name = pe.get("academic_year")
			if not ay_name:
				return pe
			year_end = frappe.db.get_value("Academic Year", ay_name, "year_end_date")
			if year_end and getdate(year_end) >= getdate(today()):
				return pe
		return enrollments[0]
	except Exception:
		return None


def _get_student_groups_edtools(student_name, program_name=None, academic_year=None):
	"""Lista de grupos del estudiante. Formato [{ label: "Nombre Grupo" }, ...].

	UNIÓN (deduplicada), no "primera estrategia con filas": el PE suele tener un solo Program
	(p. ej. AS), pero el alumno puede estar en Student Groups cuyo campo Program es otro (p. ej. BS)
	o en grupos por curso donde antes solo devolvíamos grupos AS y el cronograma quedaba vacío.

	Se combinan, en orden: grupos con mismo program que el PE, mismo academic_year, y todos los
	grupos habilitados donde es miembro (para incluir horarios ligados a cualquier sección).
	"""
	if not student_name:
		return []
	try:
		sgs = frappe.qb.DocType("Student Group Student")
		sg = frappe.qb.DocType("Student Group")

		def _groups(extra_where):
			q = (
				frappe.qb.from_(sg)
				.inner_join(sgs)
				.on(sg.name == sgs.parent)
				.select(sg.name.as_("label"))
				.where(sgs.student == student_name)
				.where(sg.disabled == 0)
			)
			for w in extra_where:
				q = q.where(w)
			return q.run(as_dict=True) or []

		merged = []
		seen = set()

		def _add(rlist):
			for r in rlist or []:
				lab = r.get("label")
				if lab and lab not in seen:
					seen.add(lab)
					merged.append({"label": lab})

		if program_name:
			_add(_groups([sg.program == program_name]))
		if academic_year:
			_add(_groups([sg.academic_year == academic_year]))
		_add(_groups([]))
		return merged
	except Exception:
		return []


def _get_student_groups_attendance_edtools(student_name, program_name=None, academic_year=None):
	"""Grupos para el portal de Asistencia: solo Course, con al menos un Student Attendance enviado.
	Orden alfabético. Lista vacía si no aplica (sin fallback a todos los grupos)."""
	if not student_name:
		return []
	try:
		candidates = _get_student_groups_edtools(student_name, program_name, academic_year) or []
		candidate_names = [c.get("label") for c in candidates if c.get("label")]
		if not candidate_names:
			return []
		course_groups = frappe.get_all(
			"Student Group",
			filters={
				"name": ["in", candidate_names],
				"group_based_on": "Course",
				"disabled": 0,
			},
			pluck="name",
		) or []
		if not course_groups:
			return []
		rows = frappe.get_all(
			"Student Attendance",
			filters={
				"student": student_name,
				"docstatus": 1,
				"student_group": ["in", course_groups],
			},
			fields=["student_group"],
			ignore_permissions=True,
		)
		with_attendance = {r.get("student_group") for r in (rows or []) if r.get("student_group")}
		sorted_names = sorted(with_attendance, key=lambda x: (x or "").lower())
		return [{"label": n} for n in sorted_names]
	except Exception:
		return []


@frappe.whitelist()
def get_student_info():
	"""Portal del estudiante: datos del estudiante + current_program + student_groups (siempre poblados)."""
	email = frappe.session.user
	if not email or email == "Guest" or email == "Administrator":
		return None
	students = frappe.db.get_list(
		"Student",
		fields=["*"],
		filters={"user": email},
		limit_page_length=1,
		ignore_permissions=True,
	)
	if not students:
		return None
	student_info = dict(students[0])
	student_info.setdefault("student_groups", [])
	student_info.setdefault("current_program", {})
	current_program = _get_current_enrollment_edtools(student_info["name"])
	if current_program:
		student_info["current_program"] = current_program
		student_info["student_groups"] = _get_student_groups_edtools(
			student_info["name"],
			current_program.get("program"),
			current_program.get("academic_year"),
		) or []
		student_info["student_groups_attendance"] = _get_student_groups_attendance_edtools(
			student_info["name"],
			current_program.get("program"),
			current_program.get("academic_year"),
		) or []
	else:
		student_info["student_groups_attendance"] = []
	# Enriquecer con datos del User: Edit Profile guarda en User (mobile_no, etc.), el modal lee Student
	user_id = student_info.get("user")
	if user_id and user_id == frappe.session.user:
		user_list = frappe.db.get_list(
			"User",
			filters={"name": user_id},
			fields=["mobile_no", "phone", "user_image"],
			limit_page_length=1,
			ignore_permissions=True,
		)
		user_data = user_list[0] if user_list else None
		if user_data:
			if not (student_info.get("student_mobile_number") or "").strip():
				student_info["student_mobile_number"] = (user_data.get("mobile_no") or user_data.get("phone") or "").strip() or None
			if not (student_info.get("image") or "").strip() and user_data.get("user_image"):
				student_info["image"] = user_data["user_image"]
	return student_info


@frappe.whitelist()
def get_school_abbr_logo():
	"""Compat con Student Portal Vue (education develop). Education v15 puede no tener estos campos."""
	abbr = None
	logo = None
	try:
		# Education develop tiene school_college_name_abbreviation / school_college_logo; v15 puede no tenerlos
		abbr = frappe.db.get_single_value(
			"Education Settings", "school_college_name_abbreviation"
		)
		logo = frappe.db.get_single_value("Education Settings", "school_college_logo")
	except Exception:
		pass
	# Si no hay logo en Education Settings, devolver None: el frontend muestra el icono School (Lucide)
	# en lugar de la "F" de Frappe, que es lo que el usuario espera ver en el sidebar.
	return {"name": abbr or "Cucusa Education", "logo": logo}


@frappe.whitelist()
def get_student_programs(student):
	"""Compat con Student Portal Vue (Grades). Education v15 puede no tenerlo.
	Usa ignore_permissions para que el rol Student pueda ver sus enrollments aunque el DocPerm falle."""
	if not student:
		return []
	# Solo devolver programas del estudiante vinculado al usuario actual
	my_student = _get_current_user_student_name()
	if not my_student or my_student != student:
		return []
	programs = frappe.db.get_list(
		"Program Enrollment",
		fields=["program", "name"],
		filters={"docstatus": 1, "student": student},
		ignore_permissions=True,
	)
	return programs or []


@frappe.whitelist()
def get_student_grades(student):
	"""Devuelve Assessment Results del estudiante con program resuelto (desde Assessment Result o Student Group).
	Usado por el portal de estudiantes (Grades) para soportar el filtro por programa correctamente."""
	if not student:
		return []
	my_student = _get_current_user_student_name()
	if not my_student or my_student != student:
		return []
	results = frappe.db.get_list(
		"Assessment Result",
		filters={"student": student, "docstatus": 1},
		fields=[
			"name",
			"student_group",
			"course",
			"program",
			"assessment_group",
			"academic_year",
			"academic_term",
			"total_score",
			"maximum_score",
			"grade",
		],
		ignore_permissions=True,
	)
	if not results:
		return []
	# Resolver program, academic_year y academic_term desde Student Group cuando no vienen
	sg_cache = {}
	for r in results:
		prog = r.get("program")
		sg = r.get("student_group")
		if sg and sg not in sg_cache:
			sg_cache[sg] = frappe.db.get_value(
				"Student Group", sg, ["program", "academic_year", "academic_term"], as_dict=True
			) or {}
		if sg and sg_cache.get(sg):
			info = sg_cache[sg]
			if not prog:
				r["program"] = info.get("program") or ""
			if not r.get("academic_year") and info.get("academic_year"):
				r["academic_year"] = info["academic_year"]
			if not r.get("academic_term") and info.get("academic_term"):
				r["academic_term"] = info["academic_term"]
	return results


def _get_current_user_student_name():
	"""Nombre del Student vinculado al usuario actual (user), o None."""
	email = frappe.session.user
	if not email or email == "Guest":
		return None
	students = frappe.db.get_list(
		"Student",
		fields=["name"],
		filters={"user": email},
		limit=1,
		ignore_permissions=True,
	)
	return students[0]["name"] if students else None


def _sales_invoice_has_student_field():
	"""Comprueba si Sales Invoice tiene el campo student (custom de Education)."""
	try:
		meta = frappe.get_meta("Sales Invoice")
		return meta.get_field("student") is not None
	except Exception:
		return False


def _get_invoices_from_sales_invoice(student):
	"""Lista desde Sales Invoice si tiene campo student. Devuelve lista de dicts o None si falla."""
	if not _sales_invoice_has_student_field():
		return None
	try:
		return frappe.db.get_list(
			"Sales Invoice",
			filters={
				"student": student,
				"status": ["in", ["Paid", "Unpaid", "Overdue", "Partly Paid"]],
				"docstatus": 1,
			},
			fields=[
				"name",
				"status",
				"student",
				"due_date",
				"fee_schedule",
				"outstanding_amount",
				"currency",
				"grand_total",
			],
			order_by="modified desc",
			ignore_permissions=True,
		)
	except Exception:
		return None


def _fee_status(outstanding_amount, due_date):
	"""Estado alineado con la lista de Fees en admin: Overdue, Unpaid, Paid, Submitted."""
	from frappe.utils import flt, getdate, today
	outstanding = flt(outstanding_amount or 0)
	if outstanding <= 0:
		return "Submitted" if outstanding < 0 else "Paid"
	# outstanding > 0
	due = getdate(due_date) if due_date else None
	if due is not None and due < getdate(today()):
		return "Overdue"
	return "Unpaid"


def _get_invoices_from_fees(student):
	"""Lista desde DocType Fees (Education). Devuelve lista de dicts con misma forma que Sales Invoice.
	Status alineado con admin: Overdue (vencida), Unpaid (pendiente), Paid, Submitted (sobrante)."""
	try:
		rows = frappe.db.get_list(
			"Fees",
			filters={"student": student, "docstatus": 1},
			fields=[
				"name",
				"due_date",
				"fee_schedule",
				"outstanding_amount",
				"currency",
				"grand_total",
			],
			order_by="modified desc",
			ignore_permissions=True,
		)
	except Exception:
		return []
	out = []
	for r in rows:
		out.append({
			"name": r.get("name"),
			"status": _fee_status(r.get("outstanding_amount"), r.get("due_date")),
			"due_date": r.get("due_date"),
			"fee_schedule": r.get("fee_schedule"),
			"outstanding_amount": r.get("outstanding_amount"),
			"currency": r.get("currency"),
			"grand_total": r.get("grand_total"),
		})
	return out


def _build_installment_labels(raw_list, from_sales_invoice):
	"""Pre-compute installment labels (e.g. 'Cuota 3/14') for all fees sharing a fee_schedule.
	Groups by fee_schedule in a single pass to avoid N+1 queries."""
	if from_sales_invoice:
		return {}
	schedules = {}
	for si in raw_list:
		fs = si.get("fee_schedule")
		if fs:
			schedules.setdefault(fs, [])
	if not schedules:
		return {}
	for fs_name in list(schedules.keys()):
		try:
			siblings = frappe.db.get_all(
				"Fees",
				filters={"fee_schedule": fs_name, "docstatus": 1},
				fields=["name"],
				order_by="due_date asc, name asc",
			)
			schedules[fs_name] = [s["name"] for s in siblings]
		except Exception:
			schedules[fs_name] = []
	labels = {}
	for si in raw_list:
		fs = si.get("fee_schedule")
		name = si.get("name")
		if not fs or fs not in schedules:
			continue
		sibs = schedules[fs]
		if len(sibs) <= 1:
			continue
		try:
			pos = sibs.index(name) + 1
		except ValueError:
			continue
		labels[name] = f"Cuota {pos}/{len(sibs)}"
	return labels


@frappe.whitelist()
def get_student_invoices(student):
	"""Compat con Student Portal Vue (Fees). Education v15 puede no tenerlo.
	Devuelve facturas (Sales Invoice y/o Fees) del estudiante con programa, estado, fechas y monto.
	Combina ambas fuentes para evitar que una lista vacía de SI oculte Fees existentes."""
	from frappe.utils import flt
	empty = {"invoices": [], "print_format": "Standard", "print_format_fees": "Standard",
			 "total_outstanding": 0, "total_paid": 0, "currency_symbol": "$"}
	if not student:
		return empty
	my_student = _get_current_user_student_name()
	if not my_student or my_student != student:
		return empty

	si_list = _get_invoices_from_sales_invoice(student) or []
	fees_list = _get_invoices_from_fees(student) or []

	tagged = []
	for si in si_list:
		si["_source"] = "Sales Invoice"
		tagged.append(si)
	for fee in fees_list:
		fee["_source"] = "Fees"
		tagged.append(fee)

	installment_labels = _build_installment_labels(fees_list, False) if fees_list else {}

	total_outstanding = 0
	total_paid = 0
	student_sales_invoices = []
	for si in tagged:
		is_si = si["_source"] == "Sales Invoice"
		outstanding = flt(si.get("outstanding_amount") or 0)
		grand_total = flt(si.get("grand_total") or 0)
		symbol = _get_currency_symbol(si.get("currency") or "USD")

		row = {
			"status": si.get("status", ""),
			"program": _get_program_from_fee_schedule(si.get("fee_schedule")),
			"invoice": si.get("name"),
			"doctype": "Sales Invoice" if is_si else "Fees",
			"outstanding_amount": outstanding,
			"grand_total": grand_total,
			"currency_symbol": symbol,
			"fee_schedule": si.get("fee_schedule"),
			"installment_label": installment_labels.get(si.get("name")),
		}
		if is_si:
			row["description"] = ""
		else:
			row["description"] = _get_fee_description(si.get("name"))
		row["amount"] = symbol + " " + str(outstanding)
		if si.get("status") in ("Paid", "Submitted"):
			row["amount"] = symbol + " " + str(grand_total)
			row["payment_date"] = (
				_get_posting_date_from_payment_entry(si.get("name"))
				if is_si
				else _get_posting_date_from_payment_entry_fees(si.get("name"))
			)
			row["due_date"] = "-"
		else:
			row["due_date"] = si.get("due_date") or "-"
			row["payment_date"] = "-"
		total_outstanding += outstanding
		total_paid += (grand_total - outstanding)
		student_sales_invoices.append(row)

	first_currency = (tagged[0].get("currency") or "USD") if tagged else "USD"
	print_format_si = _get_fees_print_format() or "Standard"
	print_format_fees = _get_print_format_for_fees() or "Standard"
	return {
		"invoices": student_sales_invoices,
		"print_format": print_format_si,
		"print_format_fees": print_format_fees,
		"total_outstanding": round(total_outstanding, 2),
		"total_paid": round(total_paid, 2),
		"currency_symbol": _get_currency_symbol(first_currency),
	}


def _get_currency_symbol(currency):
	if not currency:
		return "$"
	return frappe.db.get_value("Currency", currency, "symbol") or currency


def _get_posting_date_from_payment_entry(sales_invoice):
	try:
		ref = frappe.qb.DocType("Payment Entry Reference")
		pe = frappe.qb.DocType("Payment Entry")
		q = (
			frappe.qb.from_(pe)
			.inner_join(ref)
			.on(pe.name == ref.parent)
			.select(pe.posting_date)
			.where(ref.reference_doctype == "Sales Invoice")
			.where(ref.reference_name == sales_invoice)
		)
		rows = q.run(as_dict=True)
		if rows:
			return rows[0].get("posting_date")
	except Exception:
		pass
	return None


def _get_posting_date_from_payment_entry_fees(fee_name):
	"""Fecha de pago para un doc Fees (reference_doctype = Fees)."""
	try:
		ref = frappe.qb.DocType("Payment Entry Reference")
		pe = frappe.qb.DocType("Payment Entry")
		q = (
			frappe.qb.from_(pe)
			.inner_join(ref)
			.on(pe.name == ref.parent)
			.select(pe.posting_date)
			.where(ref.reference_doctype == "Fees")
			.where(ref.reference_name == fee_name)
		)
		rows = q.run(as_dict=True)
		if rows:
			return rows[0].get("posting_date")
	except Exception:
		pass
	return None


def _get_fees_print_format():
	try:
		return frappe.db.get_value(
			"Property Setter",
			{"property": "default_print_format", "doc_type": "Sales Invoice"},
			"value",
		)
	except Exception:
		pass
	return None


def _get_print_format_for_fees():
	"""Print format para Fees en el portal del estudiante (bolante/comprobante).
	Siempre devuelve 'Bolante de Pago' para el portal; el default del DocType (Matricula)
	se usa en el backend/admin."""
	return "Bolante de Pago"


def _get_program_from_fee_schedule(fee_schedule):
	if not fee_schedule:
		return None
	try:
		return frappe.db.get_value("Fee Schedule", fee_schedule, "program")
	except Exception:
		pass
	return None


def _get_fee_description(fee_name):
	"""Description from Fee's components (Fee Component). Joins multiple with ', '."""
	if not fee_name:
		return ""
	try:
		rows = frappe.db.get_all(
			"Fee Component",
			filters={"parent": fee_name, "parenttype": "Fees"},
			fields=["description"],
			order_by="idx asc",
		)
		parts = [str(r.get("description") or "").strip() for r in rows if r.get("description")]
		return ", ".join(parts) if parts else ""
	except Exception:
		return ""


@frappe.whitelist()
def get_course_schedule_for_student(program_name=None, student_groups=None):
	"""Compat con Student Portal Vue (education develop). Education v15 puede no tenerlo.

	Las clases se definen por Student Group; no exigir coincidencia con program del PE para evitar
	cronogramas vacíos cuando Course Schedule.program difiere del Program Enrollment.program.
	"""
	try:
		# Parámetros pueden venir como string (JSON) desde el request
		if isinstance(student_groups, str):
			try:
				student_groups = json.loads(student_groups) if student_groups else []
			except Exception:
				student_groups = []

		def _label(sg):
			if sg is None:
				return None
			if isinstance(sg, dict):
				return sg.get("label") or sg.get("name")
			return sg

		group_names = [_label(sg) for sg in (student_groups or []) if _label(sg)]
		if not group_names:
			return []

		# En Education v15 la columna puede ser "color"; en develop "class_schedule_color"
		fields = [
			"schedule_date", "room", "course",
			"from_time", "to_time", "instructor", "title", "name",
			"color",  # v15; si existe class_schedule_color lo usamos después
		]

		# Preferir coincidencia por programa cuando los datos son coherentes; si no hay filas, todo el grupo.
		schedule = []
		try:
			if program_name:
				schedule = frappe.get_all(
					"Course Schedule",
					filters={"student_group": ["in", group_names], "program": program_name},
					fields=fields,
					ignore_permissions=True,
					order_by="schedule_date asc, from_time asc",
				) or []
			if not schedule:
				schedule = frappe.get_all(
					"Course Schedule",
					filters={"student_group": ["in", group_names]},
					fields=fields,
					ignore_permissions=True,
					order_by="schedule_date asc, from_time asc",
				) or []
		except Exception:
			frappe.log_error(
				title="get_course_schedule_for_student (query)",
				message=frappe.get_traceback(),
			)
			schedule = []

		seen = set()
		deduped = []
		for row in schedule:
			n = row.get("name")
			if n and n in seen:
				continue
			if n:
				seen.add(n)
			deduped.append(row)
		schedule = deduped

		# Enriquecer con datos de Room: room_name, room_number, meeting_url (si existe)
		room_names = list({r.get("room") for r in schedule if r.get("room")})
		room_info = {}
		if room_names:
			fields_room = ["name", "room_name", "room_number"]
			if frappe.db.exists("Custom Field", {"dt": "Room", "fieldname": "meeting_url"}):
				fields_room.append("meeting_url")
			for room_doc in frappe.get_all(
				"Room",
				filters={"name": ["in", room_names]},
				fields=fields_room,
				ignore_permissions=True,
			):
				room_info[room_doc["name"]] = {
					"room_name": room_doc.get("room_name") or "",
					"room_number": room_doc.get("room_number") or "",
					"room_meeting_url": (room_doc.get("meeting_url") or "").strip() or None,
				}

		for row in schedule:
			# El frontend espera class_schedule_color; en v15 la columna es "color"
			row["class_schedule_color"] = row.get("class_schedule_color") or row.get("color")
			for field in ("from_time", "to_time"):
				if field in row and row[field] is not None:
					row[field] = str(row[field])
			info = room_info.get(row.get("room")) or {}
			row["room_name"] = info.get("room_name")
			row["room_number"] = info.get("room_number")
			row["room_meeting_url"] = info.get("room_meeting_url")
		return schedule
	except Exception as e:
		frappe.log_error(
			title="get_course_schedule_for_student",
			message=str(e) + "\n\n" + frappe.get_traceback(),
		)
		return []


@frappe.whitelist()
def _get_student_info():
	"""Solo se usa si education.api no tiene get_student_info."""
	email = frappe.session.user
	if email == "Administrator":
		return
	students = frappe.db.get_list(
		"Student",
		fields=["*"],
		filters={"user": email},
	)
	if not students:
		return
	student_info = students[0]
	student_info.setdefault("student_groups", [])
	student_info.setdefault("current_program", {})
	# current_program y student_groups si existen en education
	try:
		import education.education.api as edu_api
		if hasattr(edu_api, "get_current_enrollment") and hasattr(edu_api, "get_student_groups"):
			current_program = edu_api.get_current_enrollment(student_info["name"])
			if current_program:
				student_groups = edu_api.get_student_groups(student_info["name"], current_program.get("program"))
				student_info["student_groups"] = student_groups or []
				student_info["current_program"] = current_program
	except Exception:
		pass
	return student_info
