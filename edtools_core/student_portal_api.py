# Inyecta get_user_info (y get_student_info) en education.education.api para Student Portal.
# Education version-15 no tiene estos métodos; el frontend Vue (develop) sí los llama.

import json
import frappe


@frappe.whitelist()
def get_user_info():
	"""Compat con Student Portal Vue (education develop). Education v15 no lo tiene."""
	if frappe.session.user == "Guest":
		frappe.throw("Authentication failed", exc=frappe.AuthenticationError)
	users = frappe.db.get_list(
		"User",
		fields=["name", "email", "enabled", "user_image", "full_name", "user_type"],
		filters={"name": frappe.session.user},
	)
	if not users:
		frappe.throw("User not found", exc=frappe.AuthenticationError)
	result = users[0]
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
		if not hasattr(edu_api, "get_student_invoices"):
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
	# Assessment Results del estudiante en este programa (para marcar completed)
	assessment_results = frappe.db.get_list(
		"Assessment Result",
		filters={"student": student, "program": program_name, "docstatus": 1},
		fields=["course", "grade", "total_score", "maximum_score", "academic_term"],
		ignore_permissions=True,
	)
	results_by_course = {}
	for ar in assessment_results or []:
		c = ar.get("course")
		if c and c not in results_by_course:
			results_by_course[c] = ar
	# Course Enrollments del estudiante (para in_progress)
	ce_meta = frappe.get_meta("Course Enrollment")
	has_custom_term = ce_meta.has_field("custom_academic_term")
	ce_fields = ["course", "enrollment_date", "program_enrollment"]
	if has_custom_term:
		ce_fields.append("custom_academic_term")
	ce_list = frappe.db.get_list(
		"Course Enrollment",
		filters={"student": student, "docstatus": 1},
		fields=ce_fields,
		ignore_permissions=True,
	)
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
		elif ce:
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


def _get_student_groups_edtools(student_name, program_name):
	"""Lista de grupos del estudiante en el programa. Formato [{ label: "Nombre Grupo" }, ...]."""
	if not program_name:
		return []
	try:
		# Student Group Student tiene parent = Student Group name; Student Group tiene program
		sgs = frappe.qb.DocType("Student Group Student")
		sg = frappe.qb.DocType("Student Group")
		rows = (
			frappe.qb.from_(sg)
			.inner_join(sgs)
			.on(sg.name == sgs.parent)
			.select(sg.name.as_("label"))
			.where(sgs.student == student_name)
			.where(sg.program == program_name)
			.run(as_dict=True)
		)
		return list(rows) if rows else []
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
			student_info["name"], current_program.get("program")
		) or []
	# Enriquecer con datos del User: Edit Profile guarda en User (mobile_no, etc.), el modal lee Student
	user_id = student_info.get("user")
	if user_id:
		user_data = frappe.db.get_value(
			"User",
			user_id,
			["mobile_no", "phone", "user_image"],
			as_dict=True,
		)
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


@frappe.whitelist()
def get_student_invoices(student):
	"""Compat con Student Portal Vue (Fees). Education v15 puede no tenerlo.
	Devuelve facturas (Sales Invoice o Fees) del estudiante con programa, estado, fechas y monto."""
	if not student:
		return {"invoices": [], "print_format": "Standard"}
	my_student = _get_current_user_student_name()
	if not my_student or my_student != student:
		return {"invoices": [], "print_format": "Standard"}
	# Prefer Sales Invoice si tiene campo student; si falla o no existe, usar Fees
	raw_list = _get_invoices_from_sales_invoice(student)
	from_sales_invoice = raw_list is not None
	if raw_list is None:
		raw_list = _get_invoices_from_fees(student)
	student_sales_invoices = []
	for si in raw_list:
		row = {
			"status": si.get("status", ""),
			"program": _get_program_from_fee_schedule(si.get("fee_schedule")),
			"invoice": si.get("name"),
		}
		if not from_sales_invoice:
			row["description"] = _get_fee_description(si.get("name"))
		else:
			row["description"] = ""
		symbol = _get_currency_symbol(si.get("currency") or "USD")
		row["amount"] = symbol + " " + str(si.get("outstanding_amount") or 0)
		if si.get("status") in ("Paid", "Submitted"):
			row["amount"] = symbol + " " + str(si.get("grand_total") or 0)
			row["payment_date"] = (
				_get_posting_date_from_payment_entry(si.get("name"))
				if from_sales_invoice
				else _get_posting_date_from_payment_entry_fees(si.get("name"))
			)
			row["due_date"] = "-"
		else:
			row["due_date"] = si.get("due_date") or "-"
			row["payment_date"] = "-"
		student_sales_invoices.append(row)
	print_format = _get_fees_print_format() or "Standard"
	return {"invoices": student_sales_invoices, "print_format": print_format}


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
	"""Compat con Student Portal Vue (education develop). Education v15 puede no tenerlo."""
	try:
		# Parámetros pueden venir como string (JSON) desde el request
		if isinstance(student_groups, str):
			try:
				student_groups = json.loads(student_groups) if student_groups else []
			except Exception:
				student_groups = []
		if not program_name or not student_groups:
			return []

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

		schedule = []
		for group_name in group_names:
			try:
				rows = frappe.get_all(
					"Course Schedule",
					filters={"program": program_name, "student_group": group_name},
					fields=fields,
					ignore_permissions=True,
				)
				schedule.extend(rows or [])
			except Exception as group_err:
				frappe.log_error(
					title="get_course_schedule_for_student (per group)",
					message=frappe.get_traceback() + "\n\nGroup: " + str(group_name),
				)
		# Ordenar por fecha
		schedule.sort(key=lambda r: (r.get("schedule_date") or "", r.get("from_time") or ""))

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
