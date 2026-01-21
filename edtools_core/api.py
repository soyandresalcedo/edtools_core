# Archivo: apps/edtools_core/edtools_core/api.py
# Descripción: Port de funciones de Education (develop branch) para compatibilidad con Student Portal en v15

import json
import frappe
from frappe import _
from frappe.utils import cstr, flt, getdate, today, add_months, nowdate
from frappe.utils.dateutils import get_dates_from_timegrain

# ------------------------------------------------------------------
# UTILS & HELPERS (Necesarios para que funcionen los endpoints)
# ------------------------------------------------------------------

def get_currency_symbol(currency):
    return frappe.db.get_value("Currency", currency, "symbol") or currency

def get_program_from_fee_schedule(fee_schedule):
    program = frappe.db.get_value(
        "Fee Schedule", filters={"name": fee_schedule}, fieldname=["program"]
    )
    return program

def get_fees_print_format():
    return frappe.db.get_value(
        "Property Setter",
        dict(property="default_print_format", doc_type="Sales Invoice"),
        "value",
    )

def get_posting_date_from_payment_entry_against_sales_invoice(sales_invoice):
    payment_entry = frappe.qb.DocType("Payment Entry")
    payment_entry_reference = frappe.qb.DocType("Payment Entry Reference")

    q = (
        frappe.qb.from_(payment_entry)
        .inner_join(payment_entry_reference)
        .on(payment_entry.name == payment_entry_reference.parent)
        .select(payment_entry.posting_date)
        .where(payment_entry_reference.reference_name == sales_invoice)
    ).run(as_dict=1)

    if len(q) > 0:
        payment_date = q[0].get("posting_date")
        return payment_date

def get_student_groups(student, program_name):
    student_group = frappe.qb.DocType("Student Group")
    student_group_students = frappe.qb.DocType("Student Group Student")

    student_group_query = (
        frappe.qb.from_(student_group)
        .inner_join(student_group_students)
        .on(student_group.name == student_group_students.parent)
        .select((student_group_students.parent).as_("label"))
        .where(student_group_students.student == student)
        .where(student_group.program == program_name)
        .run(as_dict=1)
    )
    return student_group_query

def make_attendance_records(student, student_name, status, course_schedule=None, student_group=None, date=None):
    """Creates/Update Attendance Record."""
    student_attendance = frappe.get_doc(
        {
            "doctype": "Student Attendance",
            "student": student,
            "course_schedule": course_schedule,
            "student_group": student_group,
            "date": date,
        }
    )
    if not student_attendance:
        student_attendance = frappe.new_doc("Student Attendance")
    student_attendance.student = student
    student_attendance.student_name = student_name
    student_attendance.course_schedule = course_schedule
    student_attendance.student_group = student_group
    student_attendance.date = date
    student_attendance.status = status
    student_attendance.save()
    student_attendance.submit()

def apply_leave_based_on_course_schedule(leave_data, program_name):
    course_schedule_in_leave_period = frappe.db.get_list(
        "Course Schedule",
        fields=["name", "schedule_date"],
        filters={
            "program": program_name,
            "schedule_date": [
                "between",
                [leave_data.get("from_date"), leave_data.get("to_date")],
            ],
        },
        order_by="schedule_date asc",
    )
    if not course_schedule_in_leave_period:
        frappe.throw(_("No classes found in the leave period"))
    for course_schedule in course_schedule_in_leave_period:
        # check if attendance record does not exist for the student on the course schedule
        if not frappe.db.exists(
            "Student Attendance",
            {"course_schedule": course_schedule.get("name"), "docstatus": 1},
        ):
            make_attendance_records(
                leave_data.get("student"),
                leave_data.get("student_name"),
                "Leave",
                course_schedule.get("name"),
                None,
                course_schedule.get("schedule_date"),
            )

def apply_leave_based_on_student_group(leave_data, program_name):
    student_groups = get_student_groups(leave_data.get("student"), program_name)
    leave_dates = get_dates_from_timegrain(
        leave_data.get("from_date"), leave_data.get("to_date")
    )
    for student_group in student_groups:
        for leave_date in leave_dates:
            make_attendance_records(
                leave_data.get("student"),
                leave_data.get("student_name"),
                "Leave",
                None,
                student_group.get("label"),
                leave_date,
            )

# ------------------------------------------------------------------
# ENDPOINTS PRINCIPALES (WHITELISTED)
# ------------------------------------------------------------------

@frappe.whitelist()
def get_user_info():
    if frappe.session.user == "Guest":
        frappe.throw("Authentication failed", exc=frappe.AuthenticationError)

    current_user = frappe.db.get_list(
        "User",
        fields=["name", "email", "enabled", "user_image", "full_name", "user_type"],
        filters={"name": frappe.session.user},
    )[0]
    current_user["session_user"] = True
    return current_user

@frappe.whitelist()
def get_current_enrollment(student, academic_year=None):
    # If academic_year is not passed, use today's date
    compare_date = getdate(academic_year) if academic_year else getdate(today())

    program_enrollment_list = frappe.db.sql(
        """
        SELECT
            pe.name AS program_enrollment, pe.student_name, pe.program, pe.student_batch_name AS student_batch,
            pe.student_category, pe.academic_term, pe.academic_year
        FROM
            `tabProgram Enrollment` pe
        JOIN
            `tabAcademic Year` ay ON pe.academic_year = ay.name
        WHERE
            pe.student = %s
            AND ay.year_end_date >= %s
        ORDER BY
            pe.creation
        """,
        (student, compare_date),
        as_dict=1,
    )

    if program_enrollment_list:
        return program_enrollment_list[0]
    else:
        return None

@frappe.whitelist()
def get_student_info():
    email = frappe.session.user
    if email == "Administrator":
        return

    # Busca el estudiante vinculado al usuario
    student_list = frappe.db.get_list("Student", fields=["*"], filters={"user": email})

    if not student_list:
        frappe.throw(_("No Student found for user {0}").format(email))

    student_info = student_list[0]

    current_program = get_current_enrollment(student_info.name)
    if current_program:
        student_groups = get_student_groups(student_info.name, current_program.program)
        student_info["student_groups"] = student_groups
        student_info["current_program"] = current_program
    return student_info

@frappe.whitelist()
def get_school_abbr_logo():
    """Get school abbreviation and logo from Education Settings.

    Returns default values if fields don't exist (requires bench migrate).
    """
    try:
        abbr = frappe.db.get_single_value(
            "Education Settings", "school_college_name_abbreviation"
        )
    except Exception:
        abbr = None

    try:
        logo = frappe.db.get_single_value("Education Settings", "school_college_logo")
    except Exception:
        logo = None

    # Fallback: try to get from Website Settings if Education Settings fields don't exist
    if not abbr:
        abbr = frappe.db.get_single_value("Website Settings", "app_name") or "EdTools"
    if not logo:
        logo = frappe.db.get_single_value("Website Settings", "app_logo")

    return {"name": abbr, "logo": logo}

@frappe.whitelist()
def get_student_programs(student):
    programs = frappe.db.get_list(
        "Program Enrollment",
        fields=["program", "name"],
        filters={"docstatus": 1, "student": student},
    )
    return programs

@frappe.whitelist()
def get_course_list_based_on_program(program_name):
    program = frappe.get_doc("Program", program_name)
    course_list = []
    for course in program.courses:
        course_list.append(course.course)
    return course_list

@frappe.whitelist()
def get_course_schedule_for_student(program_name, student_groups):
    # student_groups viene como lista de dicts [{'label': 'GRUPO-A'}, ...]
    # Convertimos a lista simple si es necesario
    if isinstance(student_groups, str):
        student_groups = json.loads(student_groups)

    group_names = [sg.get("label") for sg in student_groups]

    schedule = frappe.db.get_list(
        "Course Schedule",
        fields=[
            "schedule_date",
            "room",
            "class_schedule_color",
            "course",
            "from_time",
            "to_time",
            "instructor",
            "title",
            "name",
        ],
        filters={"program": program_name, "student_group": ["in", group_names]},
        order_by="schedule_date asc",
    )
    return schedule

@frappe.whitelist()
def apply_leave(leave_data, program_name):
    if isinstance(leave_data, str):
        leave_data = json.loads(leave_data)

    attendance_based_on_course_schedule = frappe.db.get_single_value(
        "Education Settings", "attendance_based_on_course_schedule"
    )
    if attendance_based_on_course_schedule:
        apply_leave_based_on_course_schedule(leave_data, program_name)
    else:
        apply_leave_based_on_student_group(leave_data, program_name)

@frappe.whitelist()
def get_student_invoices(student):
    """Get student fees/invoices.

    Uses the Fees doctype which always has the student field.
    Falls back to Sales Invoice if custom fields are configured.
    """
    student_invoices = []

    # Primary: Use Fees doctype (native to Education module)
    fees_list = frappe.db.get_list(
        "Fees",
        filters={
            "student": student,
            "docstatus": 1,
        },
        fields=[
            "name",
            "student",
            "student_name",
            "due_date",
            "posting_date",
            "fee_schedule",
            "outstanding_amount",
            "currency",
            "grand_total",
            "program",
        ],
        order_by="posting_date desc",
    )

    for fee in fees_list:
        # Determine status based on outstanding amount
        if fee.outstanding_amount <= 0:
            status = "Paid"
        elif fee.outstanding_amount < fee.grand_total:
            status = "Partly Paid"
        elif fee.due_date and getdate(fee.due_date) < getdate(today()):
            status = "Overdue"
        else:
            status = "Unpaid"

        symbol = get_currency_symbol(fee.get("currency") or "USD")

        invoice_data = {
            "status": status,
            "program": fee.program,
            "invoice": fee.name,
            "due_date": fee.due_date or "-",
            "payment_date": "-",
        }

        if status == "Paid":
            invoice_data["amount"] = symbol + " " + str(fee.grand_total)
            # Get payment date from Payment Entry
            invoice_data["payment_date"] = get_posting_date_from_fee_payment(fee.name) or fee.posting_date
            invoice_data["due_date"] = "-"
        else:
            invoice_data["amount"] = symbol + " " + str(fee.outstanding_amount)

        student_invoices.append(invoice_data)

    print_format = get_fees_print_format() or "Standard"

    return {"invoices": student_invoices, "print_format": print_format}


def get_posting_date_from_fee_payment(fee_name):
    """Get payment date for a Fee from Payment Entry Reference."""
    result = frappe.db.sql(
        """
        SELECT pe.posting_date
        FROM `tabPayment Entry` pe
        INNER JOIN `tabPayment Entry Reference` per ON pe.name = per.parent
        WHERE per.reference_doctype = 'Fees'
        AND per.reference_name = %s
        AND pe.docstatus = 1
        ORDER BY pe.posting_date DESC
        LIMIT 1
        """,
        (fee_name,),
        as_dict=1,
    )
    return result[0].posting_date if result else None


# ------------------------------------------------------------------
# FEE STRUCTURE ENDPOINTS (Financial Logic - Updated)
# ------------------------------------------------------------------

# --- CONFIGURACIÓN FINANCIERA ---
INTEREST_RATE_MONTHLY = 0.0103  # 1.03% Tasa Mensual

# --- CATEGORÍAS EXACTAS ---
CAT_INSCRIPCION = "Inscripción"      # Mes 1
CAT_TRADUCCION = "Traducción y equivalencia" # Mes 2
CAT_GRADUACION = "Graduación"        # Último Mes
CAT_REGISTRO = "Registro"            # Distribuido
CAT_INTERESES = "Intereses"          # Calculado

@frappe.whitelist()
def get_amount_distribution_based_on_fee_plan(
    components,
    total_amount=0,
    fee_plan="Monthly",
    academic_year=None,
    custom_installments=12, 
    initial_payment_amount=None,
    ignore_interest=False
):
    if isinstance(ignore_interest, str):
        ignore_interest = frappe.parse_json(ignore_interest)
    
    if isinstance(components, str): components = json.loads(components)

    if fee_plan != "Monthly" or not custom_installments:
        return legacy_distribution(fee_plan, total_amount, components, academic_year)

    try: n_total_rows = int(custom_installments)
    except: n_total_rows = 12
    if n_total_rows < 3: n_total_rows = 3 

    # 1. CLASIFICAR
    val_inscripcion = 0.0
    val_traduccion = 0.0
    val_graduacion = 0.0
    val_capital = 0.0
    
    for c in components:
        cat = c.get("fees_category")
        amount = flt(c.get("amount") or 0)
        
        if cat == CAT_INSCRIPCION: val_inscripcion += amount
        elif cat == CAT_TRADUCCION: val_traduccion += amount
        elif cat == CAT_GRADUACION: val_graduacion += amount
        elif cat == CAT_INTERESES: pass
        else: val_capital += amount # Registro va aqui

    # 2. CALCULAR
    try: n_total_rows = int(custom_installments)
    except: n_total_rows = 12
    if n_total_rows < 3: n_total_rows = 3 

    n_financial_months = n_total_rows - 2 
    monthly_finance_quota = 0.0
    total_finance_paid = 0.0
    
    if val_capital > 0:
        # 3. MODIFICAR AQUÍ: Lógica para ignorar interés
        if ignore_interest:
            # División simple del capital entre los meses financieros
            monthly_finance_quota = val_capital / n_financial_months
            total_finance_paid = val_capital
        else:
            # Lógica original con interés compuesto
            r = INTEREST_RATE_MONTHLY
            n = n_financial_months
            numerator = r * ((1 + r) ** n)
            denominator = ((1 + r) ** n) - 1
            if denominator != 0:
                monthly_finance_quota = val_capital * (numerator / denominator)
            else:
                monthly_finance_quota = val_capital
            total_finance_paid = monthly_finance_quota * n
            
    elif val_capital < 0:
        monthly_finance_quota = val_capital / n_financial_months
        total_finance_paid = val_capital
    
    calculated_interest = total_finance_paid - val_capital
    if calculated_interest < 0: calculated_interest = 0

    # 3. GENERAR TABLA
    final_month_list = []
    start_date = nowdate()

    # Mes 1
    final_month_list.append({
        "due_date": add_months(start_date, 1),
        "amount": val_inscripcion,
        "term": "Pago Inicial 1 (Inscripción)"
    })
    # Mes 2
    final_month_list.append({
        "due_date": add_months(start_date, 2),
        "amount": val_traduccion,
        "term": "Pago Inicial 2 (Traducción)"
    })
    # Meses 3..N
    for i in range(1, n_financial_months + 1):
        real_month_idx = i + 2
        this_amount = monthly_finance_quota
        if i == n_financial_months: this_amount += val_graduacion

        final_month_list.append({
            "due_date": add_months(start_date, real_month_idx),
            "amount": this_amount,
            "term": f"Cuota {i}/{n_financial_months}"
        })

    return {
        "distribution": final_month_list, 
        "new_total_interest": calculated_interest,
        "per_component_amount": {}
    }

def legacy_distribution(fee_plan, total_amount, components, academic_year):
    from frappe.utils import add_months, nowdate
    # ... (Legacy simplificado)
    distribution = []
    return {"distribution": distribution, "per_component_amount": {}}

@frappe.whitelist()
def make_fee_schedule(source_name, dialog_values, per_component_amount, total_amount):
    from frappe.model.mapper import get_mapped_doc
    
    if isinstance(dialog_values, str): dialog_values = json.loads(dialog_values)
    
    student_groups = dialog_values.get("student_groups", [])
    dist_total = sum(d.get("amount") for d in dialog_values.get("distribution", []))
    created_count = 0
    
    for dist in dialog_values.get("distribution", []):
        doc = get_mapped_doc("Fee Structure", source_name, {
            "Fee Structure": {"doctype": "Fee Schedule"},
            "Fee Component": {"doctype": "Fee Component"}
        })
        
        doc.due_date = dist.get("due_date")
        if dist.get("term"): doc.academic_term = dist.get("term")
        
        # Estudiantes
        for sg in student_groups:
            row = doc.append("student_groups", {})
            row.student_group = sg.get("student_group")
        
        # --- CORRECCIÓN DE TOTALES ---
        quota_amount = flt(dist.get("amount"))
        
        # 1. Prorrateo de componentes
        current_quota_ratio = 0
        if dist_total > 0:
            current_quota_ratio = quota_amount / dist_total
            
        comp_sum = 0
        for comp in doc.components:
            original_comp_amount = flt(comp.amount)
            new_comp_amount = original_comp_amount * current_quota_ratio
            comp.amount = flt(new_comp_amount, 2)
            comp_sum += comp.amount
            
        # Ajuste decimales
        diff = quota_amount - comp_sum
        if diff != 0 and doc.components:
            doc.components[-1].amount += diff
            
        # 2. FORZADO BRUTO DE TOTALES (Para arreglar el bug de $2492)
        doc.grand_total = quota_amount
        doc.outstanding_amount = quota_amount
        doc.base_grand_total = quota_amount
        
        # Si existe el campo 'total_amount' (que causó problemas antes), lo sobrescribimos
        if hasattr(doc, 'total_amount'):
            doc.total_amount = quota_amount
            
        # Si existe 'total_amount_per_student' (visto en tu imagen), lo sobrescribimos
        if hasattr(doc, 'total_amount_per_student'):
            doc.total_amount_per_student = quota_amount
            
        doc.save()
        created_count += 1
        
    return created_count

@frappe.whitelist()
def make_term_wise_fee_schedule(source_name, target_doc=None):
    from frappe.model.mapper import get_mapped_doc
    return get_mapped_doc("Fee Structure", source_name, {
        "Fee Structure": {"doctype": "Fee Schedule", "validation": {"docstatus": ["=", 1]}},
        "Fee Component": {"doctype": "Fee Component"}
    }, target_doc)


# ------------------------------------------------------------------
# PROGRAM ENROLLMENT ENDPOINTS
# ------------------------------------------------------------------

@frappe.whitelist()
def get_program_enrollments(program, academic_year=None, academic_term=None):
    """Get students enrolled in a program.

    Args:
        program: Program name (required)
        academic_year: Academic year filter (optional)
        academic_term: Academic term filter (optional)

    Returns:
        List of program enrollments with student details
    """
    filters = {
        "program": program,
        "docstatus": 1,  # Only submitted enrollments
    }

    if academic_year:
        filters["academic_year"] = academic_year

    if academic_term:
        filters["academic_term"] = academic_term

    enrollments = frappe.db.get_list(
        "Program Enrollment",
        filters=filters,
        fields=[
            "name",
            "student",
            "student_name",
            "program",
            "academic_year",
            "academic_term",
            "student_batch_name",
            "student_category",
            "enrollment_date",
        ],
        order_by="enrollment_date desc",
    )

    # Enrich with student details
    for enrollment in enrollments:
        student = frappe.db.get_value(
            "Student",
            enrollment.student,
            ["student_email_id", "student_mobile_number", "enabled"],
            as_dict=True,
        )
        if student:
            enrollment.update(student)

    return enrollments


@frappe.whitelist()
def get_enrolled_courses(program_enrollment):
    """Get courses enrolled for a program enrollment.

    Args:
        program_enrollment: Program Enrollment name (required)

    Returns:
        List of courses with enrollment details
    """
    # Get the program enrollment document
    enrollment = frappe.get_doc("Program Enrollment", program_enrollment)

    if not enrollment:
        frappe.throw(_("Program Enrollment {0} not found").format(program_enrollment))

    # Get courses from the enrollment's courses child table
    enrolled_courses = []

    for course_enrollment in enrollment.courses:
        course_data = {
            "course": course_enrollment.course,
            "course_name": frappe.db.get_value("Course", course_enrollment.course, "course_name"),
        }
        enrolled_courses.append(course_data)

    # If no courses in enrollment, get courses from the program
    if not enrolled_courses:
        program = frappe.get_doc("Program", enrollment.program)
        for program_course in program.courses:
            course_data = {
                "course": program_course.course,
                "course_name": frappe.db.get_value("Course", program_course.course, "course_name"),
                "required": program_course.required,
            }
            enrolled_courses.append(course_data)

    return {
        "program_enrollment": program_enrollment,
        "student": enrollment.student,
        "student_name": enrollment.student_name,
        "program": enrollment.program,
        "academic_year": enrollment.academic_year,
        "academic_term": enrollment.academic_term,
        "courses": enrolled_courses,
    }


# ------------------------------------------------------------------
# ATTENDANCE ENDPOINTS (Ported from Education develop branch)
# ------------------------------------------------------------------

@frappe.whitelist()
def get_student_attendance(student, student_group=None, from_date=None, to_date=None):
    """Get attendance records for a student.

    Args:
        student: Student ID (required)
        student_group: Student Group filter (optional)
        from_date: Start date filter (optional)
        to_date: End date filter (optional)

    Returns:
        List of attendance records
    """
    filters = {
        "student": student,
        "docstatus": 1,
    }

    if student_group:
        filters["student_group"] = student_group

    if from_date and to_date:
        filters["date"] = ["between", [from_date, to_date]]
    elif from_date:
        filters["date"] = [">=", from_date]
    elif to_date:
        filters["date"] = ["<=", to_date]

    attendance_records = frappe.db.get_list(
        "Student Attendance",
        filters=filters,
        fields=[
            "name",
            "student",
            "student_name",
            "course_schedule",
            "student_group",
            "date",
            "status",
            "leave_application",
        ],
        order_by="date desc",
    )

    return attendance_records


@frappe.whitelist()
def get_attendance_percentage(student, student_group=None, from_date=None, to_date=None):
    """Calculate attendance percentage for a student.

    Args:
        student: Student ID (required)
        student_group: Student Group filter (optional)
        from_date: Start date filter (optional)
        to_date: End date filter (optional)

    Returns:
        dict with total_classes, present_count, absent_count, leave_count, and percentage
    """
    filters = {
        "student": student,
        "docstatus": 1,
    }

    if student_group:
        filters["student_group"] = student_group

    if from_date and to_date:
        filters["date"] = ["between", [from_date, to_date]]
    elif from_date:
        filters["date"] = [">=", from_date]
    elif to_date:
        filters["date"] = ["<=", to_date]

    attendance_records = frappe.db.get_list(
        "Student Attendance",
        filters=filters,
        fields=["status"],
    )

    total_classes = len(attendance_records)
    present_count = sum(1 for r in attendance_records if r.status == "Present")
    absent_count = sum(1 for r in attendance_records if r.status == "Absent")
    leave_count = sum(1 for r in attendance_records if r.status == "Leave")

    percentage = (present_count / total_classes * 100) if total_classes > 0 else 0

    return {
        "total_classes": total_classes,
        "present_count": present_count,
        "absent_count": absent_count,
        "leave_count": leave_count,
        "percentage": round(percentage, 2),
    }


# ------------------------------------------------------------------
# COURSE & INSTRUCTOR ENDPOINTS (Ported from Education develop branch)
# ------------------------------------------------------------------

@frappe.whitelist()
def get_course_topics(course):
    """Get topics for a course.

    Args:
        course: Course name (required)

    Returns:
        List of topics with their content
    """
    course_doc = frappe.get_doc("Course", course)

    topics = []
    for topic_item in course_doc.topics:
        topic_data = {
            "topic": topic_item.topic,
            "topic_name": frappe.db.get_value("Topic", topic_item.topic, "topic_name"),
        }

        # Get topic contents
        topic_doc = frappe.get_doc("Topic", topic_item.topic)
        contents = []
        for content_item in topic_doc.topic_content:
            content_data = {
                "content_type": content_item.content_type,
                "content": content_item.content,
            }
            contents.append(content_data)

        topic_data["contents"] = contents
        topics.append(topic_data)

    return {
        "course": course,
        "course_name": course_doc.course_name,
        "topics": topics,
    }


@frappe.whitelist()
def get_instructor_courses(instructor, academic_year=None, academic_term=None):
    """Get courses taught by an instructor.

    Args:
        instructor: Instructor ID (required)
        academic_year: Academic year filter (optional)
        academic_term: Academic term filter (optional)

    Returns:
        List of courses with schedule details
    """
    filters = {
        "instructor": instructor,
    }

    if academic_year:
        # Get course schedules filtered by programs in this academic year
        filters["schedule_date"] = [">=", frappe.db.get_value(
            "Academic Year", academic_year, "year_start_date"
        )]

    course_schedules = frappe.db.get_list(
        "Course Schedule",
        filters=filters,
        fields=[
            "name",
            "course",
            "program",
            "student_group",
            "room",
            "schedule_date",
            "from_time",
            "to_time",
        ],
        order_by="schedule_date desc",
    )

    # Get unique courses
    courses = {}
    for schedule in course_schedules:
        course_key = schedule.course
        if course_key not in courses:
            course_name = frappe.db.get_value("Course", schedule.course, "course_name")
            courses[course_key] = {
                "course": schedule.course,
                "course_name": course_name,
                "programs": set(),
                "student_groups": set(),
                "schedules": [],
            }

        courses[course_key]["programs"].add(schedule.program)
        courses[course_key]["student_groups"].add(schedule.student_group)
        courses[course_key]["schedules"].append({
            "schedule_date": schedule.schedule_date,
            "from_time": schedule.from_time,
            "to_time": schedule.to_time,
            "room": schedule.room,
            "student_group": schedule.student_group,
        })

    # Convert sets to lists for JSON serialization
    result = []
    for course_data in courses.values():
        course_data["programs"] = list(course_data["programs"])
        course_data["student_groups"] = list(course_data["student_groups"])
        result.append(course_data)

    return result


# ------------------------------------------------------------------
# ASSESSMENT & RESULTS ENDPOINTS (Ported from Education develop branch)
# ------------------------------------------------------------------

@frappe.whitelist()
def get_student_results(student, program=None, academic_year=None, academic_term=None):
    """Get assessment results for a student.

    Args:
        student: Student ID (required)
        program: Program filter (optional)
        academic_year: Academic year filter (optional)
        academic_term: Academic term filter (optional)

    Returns:
        List of assessment results with details
    """
    filters = {
        "student": student,
        "docstatus": 1,
    }

    if program:
        filters["program"] = program

    if academic_year:
        filters["academic_year"] = academic_year

    if academic_term:
        filters["academic_term"] = academic_term

    results = frappe.db.get_list(
        "Assessment Result",
        filters=filters,
        fields=[
            "name",
            "student",
            "student_name",
            "assessment_plan",
            "course",
            "program",
            "academic_year",
            "academic_term",
            "total_score",
            "maximum_score",
            "grade",
            "grading_scale",
        ],
        order_by="creation desc",
    )

    # Enrich with assessment plan details
    for result in results:
        plan = frappe.db.get_value(
            "Assessment Plan",
            result.assessment_plan,
            ["assessment_name", "assessment_group", "assessment_criteria"],
            as_dict=True,
        )
        if plan:
            result.update(plan)

        # Get course name
        if result.course:
            result["course_name"] = frappe.db.get_value("Course", result.course, "course_name")

    return results


@frappe.whitelist()
def get_student_average(student, program=None, academic_year=None, academic_term=None):
    """Calculate student's average grade across assessments.

    Args:
        student: Student ID (required)
        program: Program filter (optional)
        academic_year: Academic year filter (optional)
        academic_term: Academic term filter (optional)

    Returns:
        dict with average_score, average_percentage, total_assessments, and grade
    """
    filters = {
        "student": student,
        "docstatus": 1,
    }

    if program:
        filters["program"] = program

    if academic_year:
        filters["academic_year"] = academic_year

    if academic_term:
        filters["academic_term"] = academic_term

    results = frappe.db.get_list(
        "Assessment Result",
        filters=filters,
        fields=[
            "total_score",
            "maximum_score",
            "grading_scale",
        ],
    )

    if not results:
        return {
            "average_score": 0,
            "average_percentage": 0,
            "total_assessments": 0,
            "grade": None,
        }

    total_score = sum(flt(r.total_score) for r in results)
    maximum_score = sum(flt(r.maximum_score) for r in results)
    total_assessments = len(results)

    average_percentage = (total_score / maximum_score * 100) if maximum_score > 0 else 0
    average_score = total_score / total_assessments if total_assessments > 0 else 0

    # Get grade based on average percentage using the first grading scale found
    grade = None
    grading_scale = results[0].get("grading_scale") if results else None
    if grading_scale:
        grade_intervals = frappe.db.get_list(
            "Grading Scale Interval",
            filters={"parent": grading_scale},
            fields=["grade_code", "threshold"],
            order_by="threshold desc",
        )
        for interval in grade_intervals:
            if average_percentage >= flt(interval.threshold):
                grade = interval.grade_code
                break

    return {
        "average_score": round(average_score, 2),
        "average_percentage": round(average_percentage, 2),
        "total_assessments": total_assessments,
        "total_score": round(total_score, 2),
        "maximum_score": round(maximum_score, 2),
        "grade": grade,
    }


# ------------------------------------------------------------------
# TOOL ENDPOINTS (Ported from Education develop branch)
# ------------------------------------------------------------------

@frappe.whitelist()
def get_students_for_program_enrollment(academic_year, academic_term=None, program=None, student_batch=None):
    """Get students for program enrollment tool.

    Args:
        academic_year: Academic year (required)
        academic_term: Academic term filter (optional)
        program: Program filter (optional)
        student_batch: Student batch filter (optional)

    Returns:
        List of students eligible for enrollment
    """
    filters = {"enabled": 1}

    students = frappe.db.get_list(
        "Student",
        filters=filters,
        fields=[
            "name",
            "student_name",
            "student_email_id",
            "student_mobile_number",
        ],
        order_by="student_name asc",
    )

    # Filter out students already enrolled in the program for this academic year
    if program and academic_year:
        enrolled_students = frappe.db.get_list(
            "Program Enrollment",
            filters={
                "program": program,
                "academic_year": academic_year,
                "docstatus": ["!=", 2],  # Not cancelled
            },
            fields=["student"],
            pluck="student",
        )

        students = [s for s in students if s.name not in enrolled_students]

    return students


@frappe.whitelist()
def get_courses_for_student_group(program, academic_term=None):
    """Get courses for student group creation tool.

    Args:
        program: Program name (required)
        academic_term: Academic term filter (optional)

    Returns:
        List of courses in the program
    """
    program_doc = frappe.get_doc("Program", program)

    courses = []
    for program_course in program_doc.courses:
        course_data = {
            "course": program_course.course,
            "course_name": frappe.db.get_value("Course", program_course.course, "course_name"),
            "required": program_course.required,
        }
        courses.append(course_data)

    return courses


@frappe.whitelist()
def get_students_for_assessment_result(student_group, assessment_plan=None):
    """Get students for assessment result tool.

    Args:
        student_group: Student Group name (required)
        assessment_plan: Assessment Plan filter (optional)

    Returns:
        List of students with their existing assessment results
    """
    # Get students from the student group
    student_group_doc = frappe.get_doc("Student Group", student_group)

    students = []
    for student_entry in student_group_doc.students:
        student_data = {
            "student": student_entry.student,
            "student_name": student_entry.student_name,
            "group_roll_number": student_entry.group_roll_number,
        }

        # Get existing assessment result if assessment_plan is provided
        if assessment_plan:
            existing_result = frappe.db.get_value(
                "Assessment Result",
                filters={
                    "student": student_entry.student,
                    "assessment_plan": assessment_plan,
                    "docstatus": ["!=", 2],
                },
                fieldname=["name", "total_score", "grade"],
                as_dict=True,
            )
            if existing_result:
                student_data["assessment_result"] = existing_result.name
                student_data["total_score"] = existing_result.total_score
                student_data["grade"] = existing_result.grade

        students.append(student_data)

    return students


# ------------------------------------------------------------------
# REPORT CARD ENDPOINTS (Ported from Education develop branch)
# ------------------------------------------------------------------

@frappe.whitelist()
def get_report_card_data(student, academic_year=None, academic_term=None):
    """Get report card data for a student.

    Args:
        student: Student ID (required)
        academic_year: Academic year filter (optional)
        academic_term: Academic term filter (optional)

    Returns:
        dict with student info, courses, grades, attendance, and summary
    """
    # Get student info
    student_doc = frappe.get_doc("Student", student)

    # Get current enrollment
    enrollment_filters = {"student": student, "docstatus": 1}
    if academic_year:
        enrollment_filters["academic_year"] = academic_year
    if academic_term:
        enrollment_filters["academic_term"] = academic_term

    enrollment = frappe.db.get_value(
        "Program Enrollment",
        filters=enrollment_filters,
        fieldname=["name", "program", "academic_year", "academic_term", "student_batch_name"],
        as_dict=True,
        order_by="creation desc",
    )

    if not enrollment:
        return {
            "student": student,
            "student_name": student_doc.student_name,
            "message": _("No enrollment found for the specified criteria"),
        }

    # Get assessment results
    result_filters = {"student": student, "docstatus": 1}
    if academic_year:
        result_filters["academic_year"] = academic_year
    if academic_term:
        result_filters["academic_term"] = academic_term

    assessment_results = frappe.db.get_list(
        "Assessment Result",
        filters=result_filters,
        fields=[
            "name",
            "course",
            "assessment_plan",
            "total_score",
            "maximum_score",
            "grade",
            "grading_scale",
        ],
        order_by="course asc",
    )

    # Group results by course
    courses = {}
    for result in assessment_results:
        course = result.course
        if course not in courses:
            courses[course] = {
                "course": course,
                "course_name": frappe.db.get_value("Course", course, "course_name"),
                "assessments": [],
                "total_score": 0,
                "maximum_score": 0,
            }

        courses[course]["assessments"].append({
            "assessment_plan": result.assessment_plan,
            "score": result.total_score,
            "maximum_score": result.maximum_score,
            "grade": result.grade,
        })
        courses[course]["total_score"] += flt(result.total_score)
        courses[course]["maximum_score"] += flt(result.maximum_score)

    # Calculate course grades
    for course_data in courses.values():
        if course_data["maximum_score"] > 0:
            course_data["percentage"] = round(
                course_data["total_score"] / course_data["maximum_score"] * 100, 2
            )
        else:
            course_data["percentage"] = 0

    # Get attendance summary
    attendance_filters = {"student": student, "docstatus": 1}
    if academic_year:
        # Get date range from academic year
        year_dates = frappe.db.get_value(
            "Academic Year", academic_year, ["year_start_date", "year_end_date"], as_dict=True
        )
        if year_dates:
            attendance_filters["date"] = ["between", [year_dates.year_start_date, year_dates.year_end_date]]

    attendance_records = frappe.db.get_list(
        "Student Attendance",
        filters=attendance_filters,
        fields=["status"],
    )

    total_classes = len(attendance_records)
    present_count = sum(1 for r in attendance_records if r.status == "Present")
    absent_count = sum(1 for r in attendance_records if r.status == "Absent")
    leave_count = sum(1 for r in attendance_records if r.status == "Leave")

    attendance_percentage = (present_count / total_classes * 100) if total_classes > 0 else 0

    # Calculate overall summary
    total_score = sum(c["total_score"] for c in courses.values())
    maximum_score = sum(c["maximum_score"] for c in courses.values())
    overall_percentage = (total_score / maximum_score * 100) if maximum_score > 0 else 0

    return {
        "student": student,
        "student_name": student_doc.student_name,
        "program": enrollment.program,
        "academic_year": enrollment.academic_year,
        "academic_term": enrollment.academic_term,
        "student_batch": enrollment.student_batch_name,
        "courses": list(courses.values()),
        "attendance": {
            "total_classes": total_classes,
            "present": present_count,
            "absent": absent_count,
            "leave": leave_count,
            "percentage": round(attendance_percentage, 2),
        },
        "summary": {
            "total_score": round(total_score, 2),
            "maximum_score": round(maximum_score, 2),
            "overall_percentage": round(overall_percentage, 2),
            "total_courses": len(courses),
        },
    }


@frappe.whitelist()
def get_student_report_card(student, academic_year=None, academic_term=None):
    """Get student report card (alias for get_report_card_data).

    Args:
        student: Student ID (required)
        academic_year: Academic year filter (optional)
        academic_term: Academic term filter (optional)

    Returns:
        Report card data
    """
    return get_report_card_data(student, academic_year, academic_term)

@frappe.whitelist()
def get_ordered_student_fees(student):
    """Obtiene todas las Fees pendientes ordenadas por fecha de vencimiento"""
    return frappe.db.get_list("Fees",
        filters={
            "student": student,
            "docstatus": 1,
            "outstanding_amount": [">", 0]
        },
        fields=["name", "outstanding_amount", "due_date"],
        order_by="due_date asc, creation asc"
    )

@frappe.whitelist()
def get_students_by_group(student_group):
    return frappe.db.get_list(
        'Student Group Student',
        filters={'parent': student_group},
        pluck='student'
    )

# ------------------------------------------------------------------
# STUDENT FINANCIAL TOOL - LÓGICA DE NEGOCIO
# ------------------------------------------------------------------

@frappe.whitelist()
def get_structure_components(fee_structure):
    """Trae los componentes de la estructura seleccionada."""
    doc = frappe.get_doc("Fee Structure", fee_structure)
    
    # 1. Calculamos el total manualmente (evita error grand_total)
    total_calculado = sum(flt(c.amount) for c in doc.components)

    # 2. Obtenemos la moneda de forma segura (evita error currency)
    # Si no tiene campo currency, asumimos "USD"
    moneda = doc.get("currency") or "USD"

    return {
        "program": doc.program,
        "academic_year": doc.academic_year,
        "components": doc.components,
        "grand_total": total_calculado,
        "currency": moneda
    }

@frappe.whitelist()
def calculate_special_plan(components, capital_installments, start_date, apply_interest=False):
    """
    Calcula el plan financiero personalizado:
    1. Mes 1: Inscripción ($100)
    2. Mes 2: Traducción ($200)
    3. Mes 3..N: Capital amortizado
    4. Último Mes: Capital + Graduación ($200)
    """
    from frappe.utils import getdate, add_months, flt
    import json

    if isinstance(components, str): components = json.loads(components)
    capital_installments = int(capital_installments)
    start_date = getdate(start_date)

    # 1. Calcular el Total Real sumando los componentes de la tabla
    total_amount = sum(flt(c.get('amount')) for c in components)
    
    # 2. Definir valores fijos (Regla de Negocio)
    VALOR_INSCRIPCION = 100.0
    VALOR_TRADUCCION = 200.0
    VALOR_GRADUACION = 200.0
    
    # 3. Calcular el Capital Puro a financiar
    # Capital = Total - (Pagos Fijos)
    capital_principal = total_amount - VALOR_INSCRIPCION - VALOR_TRADUCCION - VALOR_GRADUACION
    
    schedule = []
    
    # --- CUOTA 1: INSCRIPCIÓN ---
    schedule.append({
        "term": "Pago Inicial 1 (Inscripción)",
        "due_date": start_date,
        "amount": VALOR_INSCRIPCION,
        "type": "Inscripcion" # Marca interna para saber qué componente asignar luego
    })
    
    # --- CUOTA 2: TRADUCCIÓN (1 mes después) ---
    schedule.append({
        "term": "Pago Inicial 2 (Traducción)",
        "due_date": add_months(start_date, 1),
        "amount": VALOR_TRADUCCION,
        "type": "Traduccion"
    })
    
    # --- CÁLCULO DE LA CUOTA DE CAPITAL ---
    monthly_capital = 0.0
    
    if capital_principal > 0:
        if apply_interest:
            # Fórmula de Amortización con Interés Compuesto (1.03% mensual)
            r = 0.0103
            n = capital_installments
            numerator = r * ((1 + r) ** n)
            denominator = ((1 + r) ** n) - 1
            
            if denominator != 0:
                monthly_capital = capital_principal * (numerator / denominator)
            else:
                monthly_capital = capital_principal
        else:
            # División Simple (Sin Interés)
            monthly_capital = capital_principal / capital_installments

    # --- GENERAR CUOTAS DE CAPITAL (Empiezan 2 meses después) ---
    current_date = add_months(start_date, 2)
    
    for i in range(1, capital_installments + 1):
        is_last = (i == capital_installments)
        
        amount = monthly_capital
        term_name = f"Cuota {i}/{capital_installments}"
        row_type = "Capital"
        
        if is_last:
            # En la última cuota sumamos los $200 de Graduación
            amount += VALOR_GRADUACION
            row_type = "Capital+Graduacion"
            term_name += " + Graduación"
            
        schedule.append({
            "term": term_name,
            "due_date": current_date,
            "amount": flt(amount, 2),
            "type": row_type
        })
        
        current_date = add_months(current_date, 1)

    return schedule

@frappe.whitelist()
def generate_batch_records(student_group, fee_structure, components, schedule_data):
    """
    Genera los registros para TODO el grupo de estudiantes:
    1. Fee Schedule (Planilla General) usando los componentes personalizados.
    2. Fees (Facturas Mensuales) desglosando los componentes según el tipo de cuota.
    """
    import json
    if isinstance(components, str): components = json.loads(components)
    if isinstance(schedule_data, str): schedule_data = json.loads(schedule_data)
    
    # 1. Obtener estudiantes activos del grupo
    students = frappe.db.get_list("Student Group Student", 
        filters={"parent": student_group, "active": 1}, 
        fields=["student"]
    )
    
    if not students:
        frappe.throw("El grupo de estudiantes seleccionado está vacío.")

    generated_count = 0
    struct_doc = frappe.get_doc("Fee Structure", fee_structure)
    
    # Calcular totales para el Fee Schedule
    total_schedule_amount = sum(flt(d.get("amount")) for d in schedule_data)

    for stu in students:
        try:
            # --- A. CREAR FEE SCHEDULE (Planilla) ---
            fs = frappe.new_doc("Fee Schedule")
            fs.student = stu.student
            fs.student_group = student_group
            fs.program = struct_doc.program
            fs.academic_year = struct_doc.academic_year
            fs.fee_structure = fee_structure
            fs.grand_total = total_schedule_amount
            fs.outstanding_amount = total_schedule_amount
            
            # Copiamos los componentes EXACTOS de la herramienta (incluyendo manuales)
            for c in components:
                fs.append("components", {
                    "fees_category": c.get("fees_category"),
                    "description": c.get("description"),
                    "amount": c.get("amount")
                })
            
            fs.save(ignore_permissions=True)
            fs.submit()
            
            # --- B. OBTENER ENROLLMENT ---
            enrollment = frappe.db.get_value("Program Enrollment", 
                {"student": stu.student, "docstatus": 1}, "name"
            )
            
            if not enrollment:
                frappe.log_error(f"Estudiante {stu.student} no tiene matrícula activa.")
                continue

            # --- C. CREAR FEES (Facturas) ---
            for row in schedule_data:
                fee = frappe.new_doc("Fees")
                fee.student = stu.student
                fee.program_enrollment = enrollment
                fee.program = struct_doc.program
                fee.academic_year = struct_doc.academic_year
                fee.fee_structure = fee_structure
                fee.fee_schedule = fs.name
                fee.due_date = row.get("due_date")
                fee.posting_date = row.get("due_date")
                fee.currency = struct_doc.currency or "USD"
                
                # Asignación inteligente de componentes según el tipo de cuota
                row_type = row.get("type")
                row_amount = flt(row.get("amount"))
                
                if row_type == "Inscripcion":
                    fee.append("components", {
                        "fees_category": "Inscripción",
                        "description": "Registration Fee",
                        "amount": row_amount
                    })
                    
                elif row_type == "Traduccion":
                    fee.append("components", {
                        "fees_category": "Traducción y equivalencia",
                        "description": "Translation Fee",
                        "amount": row_amount
                    })
                    
                elif row_type == "Capital":
                    fee.append("components", {
                        "fees_category": "Costo de programa", # Tuition
                        "description": row.get("term"),
                        "amount": row_amount
                    })
                    
                elif row_type == "Capital+Graduacion":
                    val_grad = 200.0
                    val_capital = row_amount - val_grad
                    
                    fee.append("components", {
                        "fees_category": "Costo de programa",
                        "description": row.get("term") + " (Capital)",
                        "amount": val_capital
                    })
                    fee.append("components", {
                        "fees_category": "Graduación",
                        "description": "Graduation Fee",
                        "amount": val_grad
                    })

                fee.grand_total = row_amount
                fee.outstanding_amount = row_amount
                
                fee.save(ignore_permissions=True)
                fee.submit()
            
            generated_count += 1
            
        except Exception as e:
            frappe.log_error(f"Error generando plan para {stu.student}: {str(e)}")
            continue
            
    return generated_count