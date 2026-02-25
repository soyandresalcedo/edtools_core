from . import __version__ as app_version

app_name = "edtools_core"
app_title = "Edtools"
app_publisher = "Andres Salcedo"
app_description = "Custom branding and features for Edtools Educational System"
app_email = "soyandresalcedo@gmail.com"
app_license = "MIT"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
app_include_css = "/assets/edtools_core/css/edtools.css"
app_include_js = [
    "/assets/edtools_core/js/edtools.js",
    "/assets/edtools_core/js/socketio_override.js"
]

# include js, css files in header of web template
web_include_css = "/assets/edtools_core/css/edtools.css"
web_include_js = "/assets/edtools_core/js/edtools.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "edtools_core/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
	"Student": "public/js/student.js",
	"Student Applicant": "public/js/student_applicant.js",
	"Fee Structure": "public/js/fee_structure_custom.js",
	"Student Group": "public/js/student_group_custom.js",
}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role). Valor debe ser lista para get_home_page_via_hooks (usa [-1]).
# Estudiantes van a /student-portal (Education Vue app: horario, notas, cuotas, asistencia)
role_home_page = {
	"Student": ["student-portal"],
}

# Resolver: /student-portal y /student-portal/schedule (etc.) sirven el mismo HTML para que F5 no dé 404
website_path_resolver = ["edtools_core.website_resolver.resolve"]

# Favicon: /favicon.png no existe → redirigir al que sí existe (evita 404 en student-portal y resto del sitio)
website_redirects = [
	{"source": "favicon.png", "target": "/assets/frappe/images/frappe-favicon.svg", "redirect_http_status": 302},
]

# Ítems del menú lateral del portal web para el rol Student (se suman a los estándar)
standard_portal_menu_items = [
	{
		"title": "Portal del Estudiante",
		"route": "/student-portal",
		"role": "Student",
	},
]

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "edtools_core.utils.jinja_methods",
# 	"filters": "edtools_core.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "edtools_core.install.before_install"
# after_install = "edtools_core.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "edtools_core.uninstall.before_uninstall"
# after_uninstall = "edtools_core.uninstall.after_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "edtools_core.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes (permite mismo curso en distintos periodos)
override_doctype_class = {
	"Course Enrollment": "edtools_core.overrides.course_enrollment.CourseEnrollment",
	"Program Enrollment": "edtools_core.overrides.program_enrollment.ProgramEnrollment",
	"Program Enrollment Tool": "edtools_core.overrides.program_enrollment_tool.ProgramEnrollmentTool",
	"Student": "edtools_core.overrides.student.Student",
	"Student Group": "edtools_core.overrides.student_group.StudentGroup",
	"User": "edtools_core.overrides.user.User",
}

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Program Enrollment": {
		"validate": "edtools_core.validations.enrollment.validate_student_status"
	},
	"Course Enrollment": {
		"validate": "edtools_core.validations.enrollment.validate_student_status"
	},
	"Student": {
		"before_save": "edtools_core.validations.student.track_status_change"
	},
	"Fees": {
		"before_save": "edtools_core.fees_events.update_components_description"
	}
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"edtools_core.tasks.all"
# 	],
# 	"daily": [
# 		"edtools_core.tasks.daily"
# 	],
# 	"hourly": [
# 		"edtools_core.tasks.hourly"
# 	],
# 	"weekly": [
# 		"edtools_core.tasks.weekly"
# 	],
# 	"monthly": [
# 		"edtools_core.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "edtools_core.install.before_tests"

# Overriding Methods
# ------------------------------
#
# Office 365: Microsoft no envía email/email_verified en id_token para cuentas organizacionales.
override_whitelisted_methods = {
	"frappe.integrations.oauth2_logins.login_via_office365": "edtools_core.oauth_office365.login_via_office365",
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "edtools_core.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]


# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"edtools_core.auth.validate"
# ]

# Translation
# --------------------------------

# Make link fields search translated document names for these DocTypes
# Recommended only for DocTypes which have limited documents with untranslated names
# For example: Role, Gender, etc.
# translated_search_doctypes = []

# Website Settings
# Override the default website title
website_context = {
	"brand_html": "CUC University",
	"top_bar_items": [],
	"footer_items": []
}

# Brand overrides - CUC University
brand_html = "CUC University"
app_name = "edtools_core"
app_title = "CUC University"

# Logo de login y páginas web (transparente, se ve sobre fondo claro u oscuro)
app_logo_url = ["/assets/edtools_core/images/cuc-university-logo.png"]

# Boot session - inject custom values into frappe.boot
# extend_bootinfo = "edtools_core.boot.boot_session"
