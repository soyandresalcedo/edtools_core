# Archivo: apps/edtools_core/edtools_core/api.py
# Descripción: Port de funciones de Education (develop branch) para compatibilidad con Student Portal en v15

import json
import frappe
from frappe import _
from frappe.utils import cstr, flt, getdate, today
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
    abbr = frappe.db.get_single_value(
        "Education Settings", "school_college_name_abbreviation"
    )
    logo = frappe.db.get_single_value("Education Settings", "school_college_logo")
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
    student_sales_invoices = []

    sales_invoice_list = frappe.db.get_list(
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
        order_by="status desc",
    )

    for si in sales_invoice_list:
        student_program_invoice_status = {}
        student_program_invoice_status["status"] = si.status
        # Validar si fee_schedule existe antes de buscar
        if si.fee_schedule:
            student_program_invoice_status["program"] = get_program_from_fee_schedule(si.fee_schedule)
        else:
            student_program_invoice_status["program"] = None

        symbol = get_currency_symbol(si.get("currency", "INR"))
        student_program_invoice_status["amount"] = symbol + " " + str(si.outstanding_amount)
        student_program_invoice_status["invoice"] = si.name

        if si.status == "Paid":
            student_program_invoice_status["amount"] = symbol + " " + str(si.grand_total)
            student_program_invoice_status["payment_date"] = get_posting_date_from_payment_entry_against_sales_invoice(si.name)
            student_program_invoice_status["due_date"] = "-"
        else:
            student_program_invoice_status["due_date"] = si.due_date
            student_program_invoice_status["payment_date"] = "-"

        student_sales_invoices.append(student_program_invoice_status)

    print_format = get_fees_print_format() or "Standard"

    return {"invoices": student_sales_invoices, "print_format": print_format}
