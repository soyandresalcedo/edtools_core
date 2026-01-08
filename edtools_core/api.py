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
# FEE STRUCTURE ENDPOINTS (Ported from Education develop branch)
# ------------------------------------------------------------------

def get_future_dates(fee_plan, start_date=None):
    """Helper function to calculate future payment dates based on fee plan."""
    from frappe.utils import add_months, nowdate

    today = start_date or nowdate()
    gap_map = {
        "Monthly": 1,
        "Quarterly": 3,
        "Semi-Annually": 6,
        "Annually": 12,
    }
    frequency_map = {
        "Monthly": 12,
        "Quarterly": 4,
        "Semi-Annually": 2,
        "Annually": 1,
    }
    months = []
    gap = gap_map.get(fee_plan)
    frequency = frequency_map.get(fee_plan)

    for i in range(1, frequency + 1):
        months.append(add_months(today, gap * i))

    return months


@frappe.whitelist()
def get_amount_distribution_based_on_fee_plan(
    components,
    total_amount=0,
    fee_plan="Monthly",
    academic_year=None,
):
    """Calculate fee distribution based on payment plan.

    Args:
        components: JSON string of fee components with fees_category and total
        total_amount: Total fee amount
        fee_plan: Payment plan type (Monthly, Quarterly, Semi-Annually, Term-Wise, Annually)
        academic_year: Required for Term-Wise plan

    Returns:
        dict with 'distribution' (list of due dates and amounts) and 'per_component_amount'
    """
    total_amount = flt(total_amount)
    if isinstance(components, str):
        components = json.loads(components)

    month_dict = {
        "Monthly": {"month_list": get_future_dates("Monthly"), "amount": 1 / 12},
        "Quarterly": {
            "month_list": get_future_dates("Quarterly"),
            "amount": 1 / 4,
        },
        "Semi-Annually": {"month_list": get_future_dates("Semi-Annually"), "amount": 1 / 2},
        "Term-Wise": {"month_list": [], "amount": 0},
        "Annually": {"month_list": get_future_dates("Annually"), "amount": 1},
    }

    academic_terms = []
    if fee_plan == "Term-Wise":
        academic_terms = frappe.get_list(
            "Academic Term",
            filters={"academic_year": academic_year},
            fields=["name", "term_start_date"],
            order_by="term_start_date asc",
        )
        if not academic_terms:
            frappe.throw(
                _("No Academic Terms found for Academic Year {0}").format(academic_year)
            )
        month_dict.get(fee_plan)["amount"] = 1 / len(academic_terms)

        for term in academic_terms:
            month_dict.get(fee_plan)["month_list"].append(
                {"term": term.get("name"), "due_date": term.get("term_start_date")}
            )

    month_list_and_amount = month_dict[fee_plan]

    per_component_amount = {}
    for component in components:
        # Use 'total' if available, otherwise calculate from 'amount' and 'discount'
        component_total = component.get("total")
        if component_total is None:
            amount = flt(component.get("amount", 0))
            discount = flt(component.get("discount", 0))
            component_total = amount - (amount * discount / 100)
        per_component_amount[component.get("fees_category")] = flt(component_total) * month_list_and_amount.get("amount")

    amount = sum(per_component_amount.values())

    final_month_list = []

    if fee_plan == "Term-Wise":
        for term in month_list_and_amount.get("month_list"):
            final_month_list.append(
                {"term": term.get("term"), "due_date": term.get("due_date"), "amount": amount}
            )
    else:
        for date in month_list_and_amount.get("month_list"):
            final_month_list.append({"due_date": date, "amount": amount})

    return {"distribution": final_month_list, "per_component_amount": per_component_amount}


def validate_due_date(due_date, idx):
    """Validate that due date is not in the past."""
    from frappe.utils import nowdate
    if due_date < nowdate():
        frappe.throw(
            _("Due Date in row {0} should be greater than or same as today's date.").format(idx)
        )


@frappe.whitelist()
def make_fee_schedule(
    source_name,
    dialog_values,
    per_component_amount,
    total_amount,
    target_doc=None,
):
    """Create Fee Schedule(s) from Fee Structure based on distribution plan.

    This creates multiple Fee Schedules based on the fee plan distribution
    (Monthly, Quarterly, etc.) selected in the modal dialog.

    Args:
        source_name: Fee Structure name
        dialog_values: JSON with distribution and student_groups from modal
        per_component_amount: JSON with amount per component
        total_amount: Total amount from Fee Structure
        target_doc: Optional target document

    Returns:
        Number of Fee Schedules created
    """
    from frappe.model.mapper import get_mapped_doc

    dialog_values = json.loads(dialog_values) if isinstance(dialog_values, str) else dialog_values
    per_component_amount = json.loads(per_component_amount) if isinstance(per_component_amount, str) else per_component_amount

    student_groups = dialog_values.get("student_groups")
    fee_plan_wise_distribution = [
        fee_plan.get("due_date") for fee_plan in dialog_values.get("distribution", [])
    ]

    for distribution in dialog_values.get("distribution", []):
        validate_due_date(distribution.get("due_date"), distribution.get("idx"))

        doc = get_mapped_doc(
            "Fee Structure",
            source_name,
            {
                "Fee Structure": {
                    "doctype": "Fee Schedule",
                },
                "Fee Component": {"doctype": "Fee Component"},
            },
        )
        doc.due_date = distribution.get("due_date")
        if distribution.get("term"):
            doc.academic_term = distribution.get("term")
        amount_per_month = 0

        for component in doc.components:
            component_ratio = component.get("total") / flt(total_amount)
            component_ratio = round((component_ratio * 100) / 100, 2)
            component.total = flt(component_ratio * distribution.get("amount"))

            if component.discount == 100:
                component.amount = component.total
            else:
                component.amount = flt((component.total) / flt(100 - component.discount)) * 100

            amount_per_month += component.total

        # Each distribution will be a separate fee schedule
        doc.total_amount = distribution.get("amount")

        for group in student_groups:
            fee_schedule_student_group = doc.append("student_groups", {})
            fee_schedule_student_group.student_group = group.get("student_group")

        doc.save()

    return len(fee_plan_wise_distribution)


@frappe.whitelist()
def make_term_wise_fee_schedule(source_name, target_doc=None):
    """Create a single Fee Schedule from Fee Structure (term-wise).

    Used when Fee Structure has an academic_term set.
    Simply maps the Fee Structure to a new Fee Schedule.

    Args:
        source_name: Fee Structure name
        target_doc: Optional target document

    Returns:
        Mapped Fee Schedule document
    """
    from frappe.model.mapper import get_mapped_doc

    return get_mapped_doc(
        "Fee Structure",
        source_name,
        {
            "Fee Structure": {
                "doctype": "Fee Schedule",
                "validation": {
                    "docstatus": ["=", 1],
                },
            },
            "Fee Component": {"doctype": "Fee Component"},
        },
        target_doc,
    )
