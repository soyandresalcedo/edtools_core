# Copyright (c) 2026, EdTools and contributors
"""Fuente única del HTML branded de los correos académicos EdTools (CUC University).

El mismo HTML lo usan el seed (instalaciones nuevas) y el patch de rediseño
(actualiza las plantillas ya creadas en producción). Mantener aquí cualquier
cambio de diseño para que ambos caminos queden sincronizados.

Notas de compatibilidad con clientes de correo:
- Solo se usan estilos inline + atributos de tabla (sin <style>/@media): el cuerpo
  se inyecta dentro del wrapper estándar de Frappe (``<p>{{ content }}</p>``) y pasa
  por premailer, así que un documento HTML completo no es seguro.
- Las barras moradas usan ``bgcolor`` sólido (más robusto que background-image).
"""

from __future__ import annotations

LOGO_URL = (
	"https://eopwebn.stripocdn.email/content/guids/"
	"CABINET_b4520928468ffa9aa1be02de26f7c5bb3dbaed7e4f3d55d991560d2c68526369/"
	"images/group_1597883225_1.png"
)
FLAG_URL = (
	"https://eopwebn.stripocdn.email/content/guids/"
	"CABINET_b4520928468ffa9aa1be02de26f7c5bb3dbaed7e4f3d55d991560d2c68526369/"
	"images/image_2187.png"
)

BRAND_PURPLE = "#b7a8ff"
BRAND_PURPLE_SOFT = "#f3f0ff"
BRAND_YELLOW = "#ffd15b"
BORDER = "#e5e7eb"
TEXT = "#000000"
BG = "#F6F6F6"

FONT = "Arial,'Helvetica Neue',Helvetica,sans-serif"

SIGN_ES = "<strong>Saludos,</strong><br>CUC University"
SIGN_EN = "<strong>Regards,</strong><br>CUC University"

BTN_ES = "Ir al portal"
BTN_EN = "Go to the portal"


def _shell(*, title_html: str, body_html: str, button_label: str, sign_html: str) -> str:
	"""Envuelve el contenido específico en el marco branded (logo + barras + botón)."""
	return (
		'<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation"'
		' style="border-collapse:collapse;background-color:' + BG + ';">'
		'<tr><td align="center" style="padding:24px 12px;">'
		'<table width="600" cellpadding="0" cellspacing="0" border="0" role="presentation"'
		' style="border-collapse:collapse;width:600px;max-width:600px;background-color:#FFFFFF;'
		'border-radius:12px;overflow:hidden;">'
		# Barra superior morada
		'<tr><td height="14" style="height:14px;line-height:14px;font-size:0;'
		'background-color:' + BRAND_PURPLE + ';">&nbsp;</td></tr>'
		# Logo
		'<tr><td style="padding:28px 40px 4px 40px;">'
		'<img src="' + LOGO_URL + '" alt="CUC University" width="150"'
		' style="display:block;border:0;outline:none;text-decoration:none;'
		'width:150px;max-width:150px;height:auto;"></td></tr>'
		# Título + imagen decorativa
		'<tr><td style="padding:6px 40px 0 40px;">'
		'<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation"'
		' style="border-collapse:collapse;"><tr>'
		'<td valign="middle" style="font-family:' + FONT + ';color:' + BRAND_PURPLE + ';'
		'font-size:30px;line-height:36px;font-weight:bold;">' + title_html + '</td>'
		'<td valign="middle" width="110" align="right">'
		'<img src="' + FLAG_URL + '" alt="" width="95"'
		' style="display:block;border:0;outline:none;text-decoration:none;'
		'width:95px;max-width:95px;height:auto;"></td>'
		'</tr></table></td></tr>'
		# Cuerpo
		'<tr><td style="padding:18px 40px 4px 40px;font-family:' + FONT + ';color:' + TEXT + ';'
		'font-size:14px;line-height:21px;">' + body_html + '</td></tr>'
		# Botón
		'<tr><td style="padding:20px 40px 4px 40px;">'
		'<table cellpadding="0" cellspacing="0" border="0" role="presentation"'
		' style="border-collapse:collapse;"><tr>'
		'<td align="center" bgcolor="' + BRAND_YELLOW + '"'
		' style="border-radius:8px;background-color:' + BRAND_YELLOW + ';">'
		'<a href="{{ portal_url }}" target="_blank"'
		' style="display:inline-block;padding:12px 28px;font-family:' + FONT + ';font-size:14px;'
		'font-weight:bold;color:' + TEXT + ';text-decoration:none;border-radius:8px;">'
		+ button_label + '</a>'
		'</td></tr></table></td></tr>'
		# Firma
		'<tr><td style="padding:20px 40px 28px 40px;font-family:' + FONT + ';color:' + TEXT + ';'
		'font-size:14px;line-height:21px;">' + sign_html + '</td></tr>'
		# Barra inferior morada
		'<tr><td height="14" style="height:14px;line-height:14px;font-size:0;'
		'background-color:' + BRAND_PURPLE + ';">&nbsp;</td></tr>'
		'</table></td></tr></table>'
	)


def _detail_table(rows: list[tuple[str, str]]) -> str:
	"""Tabla de dos columnas (etiqueta / valor) con estilo branded."""
	cells = []
	last = len(rows) - 1
	for index, (label, value) in enumerate(rows):
		border = "" if index == last else "border-bottom:1px solid " + BORDER + ";"
		cells.append(
			'<tr>'
			'<td style="padding:9px 12px;width:42%;background-color:' + BRAND_PURPLE_SOFT + ';'
			+ border + 'font-weight:bold;vertical-align:top;">' + label + '</td>'
			'<td style="padding:9px 12px;' + border + 'vertical-align:top;">' + value + '</td>'
			'</tr>'
		)
	return (
		'<table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation"'
		' style="border-collapse:collapse;border:1px solid ' + BORDER + ';font-family:' + FONT + ';'
		'font-size:14px;color:' + TEXT + ';">' + "".join(cells) + '</table>'
	)


# ---------------------------------------------------------------------------
# Matrícula a curso
# ---------------------------------------------------------------------------

_ENROLL_ROWS_ES = [
	("Curso", "{% if ref.course %}{{ ref.course.course_name }}{% else %}{{ course_name }}{% endif %}"),
	("Programa", "{% if ref.program %}{{ ref.program.program_name }}{% else %}{{ program }}{% endif %}"),
	("Periodo", "{% if ref.academic_term %}{{ ref.academic_term.term_name }}{% else %}{{ academic_term }}{% endif %}"),
	(
		"Inicio del periodo",
		"{% if ref.academic_term and ref.academic_term.term_start_date %}"
		"{{ ref.academic_term.term_start_date }}{% else %}&mdash;{% endif %}",
	),
	("Fecha de inscripción", "{{ enrollment_date }}"),
]

_ENROLL_ROWS_EN = [
	("Course", "{% if ref.course %}{{ ref.course.course_name }}{% else %}{{ course_name }}{% endif %}"),
	("Program", "{% if ref.program %}{{ ref.program.program_name }}{% else %}{{ program }}{% endif %}"),
	("Term", "{% if ref.academic_term %}{{ ref.academic_term.term_name }}{% else %}{{ academic_term }}{% endif %}"),
	(
		"Term start",
		"{% if ref.academic_term and ref.academic_term.term_start_date %}"
		"{{ ref.academic_term.term_start_date }}{% else %}&mdash;{% endif %}",
	),
	("Enrollment date", "{{ enrollment_date }}"),
]

_COURSE_ENROLLMENT_ES = _shell(
	title_html="Inscripción a<br>un nuevo curso",
	body_html=(
		'<p style="margin:0 0 12px 0;">Hola {{ student_name }},</p>'
		'<p style="margin:0 0 16px 0;">Te confirmamos tu inscripción al siguiente curso:</p>'
		+ _detail_table(_ENROLL_ROWS_ES)
	),
	button_label=BTN_ES,
	sign_html=SIGN_ES,
)

_COURSE_ENROLLMENT_EN = _shell(
	title_html="Enrollment in<br>a new course",
	body_html=(
		'<p style="margin:0 0 12px 0;">Hello {{ student_name }},</p>'
		'<p style="margin:0 0 16px 0;">Your enrollment in the following course has been confirmed:</p>'
		+ _detail_table(_ENROLL_ROWS_EN)
	),
	button_label=BTN_EN,
	sign_html=SIGN_EN,
)

# ---------------------------------------------------------------------------
# Calificaciones publicadas / actualizadas
# ---------------------------------------------------------------------------

_GRADE_POSTED_ES = _shell(
	title_html="{% if is_correction %}Calificación<br>actualizada{% else %}Nueva<br>calificación{% endif %}",
	body_html=(
		'<p style="margin:0 0 12px 0;">Hola {{ student_name }},</p>'
		"{% if is_correction %}"
		"{% if grade_count == 1 %}"
		'<p style="margin:0 0 16px 0;">Se ha modificado la nota del siguiente curso. '
		"Ingresa al portal para consultar el resultado.</p>"
		"{% else %}"
		'<p style="margin:0 0 16px 0;">Se han modificado calificaciones en los siguientes cursos. '
		"Ingresa al portal para consultar el resultado.</p>"
		"{% endif %}"
		"{% else %}"
		"{% if grade_count == 1 %}"
		'<p style="margin:0 0 16px 0;">Se ha agregado una nueva nota al siguiente curso. '
		"Ingresa al portal para consultar el resultado.</p>"
		"{% else %}"
		'<p style="margin:0 0 16px 0;">Se han agregado nuevas calificaciones a tu record académico. '
		"Ingresa al portal para consultar el resultado.</p>"
		"{% endif %}"
		"{% endif %}"
		"{{ grades_table_html | safe }}"
	),
	button_label=BTN_ES,
	sign_html=SIGN_ES,
)

_GRADE_POSTED_EN = _shell(
	title_html="{% if is_correction %}Grade<br>updated{% else %}New<br>grade{% endif %}",
	body_html=(
		'<p style="margin:0 0 12px 0;">Hello {{ student_name }},</p>'
		"{% if is_correction %}"
		"{% if grade_count == 1 %}"
		'<p style="margin:0 0 16px 0;">The grade for the following course has been updated. '
		"Sign in to the portal to view the result.</p>"
		"{% else %}"
		'<p style="margin:0 0 16px 0;">Grades have been updated for the following courses. '
		"Sign in to the portal to view the results.</p>"
		"{% endif %}"
		"{% else %}"
		"{% if grade_count == 1 %}"
		'<p style="margin:0 0 16px 0;">A new grade has been added for the following course. '
		"Sign in to the portal to view the result.</p>"
		"{% else %}"
		'<p style="margin:0 0 16px 0;">New grades have been added to your academic record. '
		"Sign in to the portal to view the results.</p>"
		"{% endif %}"
		"{% endif %}"
		"{{ grades_table_html | safe }}"
	),
	button_label=BTN_EN,
	sign_html=SIGN_EN,
)


BRANDED_TEMPLATES = [
	{
		"name": "EdTools Course Enrollment ES",
		"subject": "Inscripción a curso: {% if ref.course %}{{ ref.course.course_name }}{% else %}{{ course_name }}{% endif %}",
		"response": _COURSE_ENROLLMENT_ES,
	},
	{
		"name": "EdTools Course Enrollment EN",
		"subject": "Course enrollment: {% if ref.course %}{{ ref.course.course_name }}{% else %}{{ course_name }}{% endif %}",
		"response": _COURSE_ENROLLMENT_EN,
	},
	{
		"name": "EdTools Grade Posted ES",
		"subject": "{% if is_correction %}Calificación actualizada{% else %}Nueva calificación{% endif %}",
		"response": _GRADE_POSTED_ES,
	},
	{
		"name": "EdTools Grade Posted EN",
		"subject": "{% if is_correction %}Grade updated{% else %}New grade{% endif %}",
		"response": _GRADE_POSTED_EN,
	},
]

BRANDED_TEMPLATES_BY_NAME = {tpl["name"]: tpl for tpl in BRANDED_TEMPLATES}


# ---------------------------------------------------------------------------
# Débito automático (autopay) de cuotas — ver edtools_core.stripe_autopay
# ---------------------------------------------------------------------------
# Contexto disponible: student_name, program, card, charge_day, amount, fee_description,
# due_date, charge_date, next_charge_date, failure_reason, will_retry, next_retry_date,
# portal_url.

BTN_AUTOPAY_ES = "Ver mis pagos"
BTN_AUTOPAY_EN = "View my payments"


def _p(text: str, *, bottom: int = 12) -> str:
	return '<p style="margin:0 0 ' + str(bottom) + 'px 0;">' + text + "</p>"


_AUTOPAY_ACTIVATED_ES = _shell(
	title_html="Pago automático<br>activado",
	body_html=(
		_p("Hola {{ student_name }},")
		+ _p(
			"Activaste el pago automático de tus cuotas. A partir de ahora cobraremos la cuota "
			"pendiente de cada mes a tu tarjeta, sin que tengas que entrar al portal.",
			bottom=16,
		)
		+ _detail_table(
			[
				("Programa", "{{ program }}"),
				("Tarjeta", "{{ card }}"),
				("Día de cobro", "El {{ charge_day }} de cada mes"),
				("Primer cobro automático", "{{ next_charge_date }}"),
			]
		)
		+ '<p style="margin:16px 0 0 0;">Te avisaremos por correo unos días antes de cada cobro. '
		"Puedes cambiar la tarjeta, el día o cancelar el pago automático cuando quieras desde el "
		"Portal del Estudiante, en la sección <strong>Pagos</strong>.</p>"
	),
	button_label=BTN_AUTOPAY_ES,
	sign_html=SIGN_ES,
)

_AUTOPAY_ACTIVATED_EN = _shell(
	title_html="Automatic payments<br>turned on",
	body_html=(
		_p("Hello {{ student_name }},")
		+ _p(
			"You turned on automatic payments. From now on we will charge each month's pending "
			"installment to your card, with no need to log in to the portal.",
			bottom=16,
		)
		+ _detail_table(
			[
				("Program", "{{ program }}"),
				("Card", "{{ card }}"),
				("Charge day", "Day {{ charge_day }} of each month"),
				("First automatic charge", "{{ next_charge_date }}"),
			]
		)
		+ '<p style="margin:16px 0 0 0;">We will email you a few days before each charge. '
		"You can change the card or the day, or cancel automatic payments at any time from the "
		"Student Portal, in the <strong>Fees</strong> section.</p>"
	),
	button_label=BTN_AUTOPAY_EN,
	sign_html=SIGN_EN,
)

_AUTOPAY_REMINDER_ES = _shell(
	title_html="Tu próximo<br>cobro automático",
	body_html=(
		_p("Hola {{ student_name }},")
		+ _p("Te recordamos que el <strong>{{ charge_date }}</strong> cobraremos automáticamente:", bottom=16)
		+ _detail_table(
			[
				("Concepto", "{{ fee_description }}"),
				("Monto", "<strong>{{ amount }}</strong>"),
				("Tarjeta", "{{ card }}"),
			]
		)
		+ '<p style="margin:16px 0 0 0;">No tienes que hacer nada. Si prefieres pagar con otra tarjeta, '
		"cámbiala en el portal antes de esa fecha.</p>"
	),
	button_label=BTN_AUTOPAY_ES,
	sign_html=SIGN_ES,
)

_AUTOPAY_REMINDER_EN = _shell(
	title_html="Your next<br>automatic charge",
	body_html=(
		_p("Hello {{ student_name }},")
		+ _p("This is a reminder that on <strong>{{ charge_date }}</strong> we will automatically charge:", bottom=16)
		+ _detail_table(
			[
				("Item", "{{ fee_description }}"),
				("Amount", "<strong>{{ amount }}</strong>"),
				("Card", "{{ card }}"),
			]
		)
		+ '<p style="margin:16px 0 0 0;">No action is needed. If you would rather use a different card, '
		"update it in the portal before that date.</p>"
	),
	button_label=BTN_AUTOPAY_EN,
	sign_html=SIGN_EN,
)

_AUTOPAY_CHARGED_ES = _shell(
	title_html="Recibimos<br>tu pago",
	body_html=(
		_p("Hola {{ student_name }},")
		+ _p("Cobramos con éxito tu cuota mediante el pago automático:", bottom=16)
		+ _detail_table(
			[
				("Concepto", "{{ fee_description }}"),
				("Monto", "<strong>{{ amount }}</strong>"),
				("Tarjeta", "{{ card }}"),
				("Próximo cobro", "{% if next_charge_date %}{{ next_charge_date }}{% else %}&mdash;{% endif %}"),
			]
		)
		+ '<p style="margin:16px 0 0 0;">El pago quedará reflejado en tu estado de cuenta una vez '
		"Tesorería lo concilie.</p>"
	),
	button_label=BTN_AUTOPAY_ES,
	sign_html=SIGN_ES,
)

_AUTOPAY_CHARGED_EN = _shell(
	title_html="We received<br>your payment",
	body_html=(
		_p("Hello {{ student_name }},")
		+ _p("Your installment was successfully charged through automatic payments:", bottom=16)
		+ _detail_table(
			[
				("Item", "{{ fee_description }}"),
				("Amount", "<strong>{{ amount }}</strong>"),
				("Card", "{{ card }}"),
				("Next charge", "{% if next_charge_date %}{{ next_charge_date }}{% else %}&mdash;{% endif %}"),
			]
		)
		+ '<p style="margin:16px 0 0 0;">The payment will show on your account statement once the '
		"Treasury office reconciles it.</p>"
	),
	button_label=BTN_AUTOPAY_EN,
	sign_html=SIGN_EN,
)

_AUTOPAY_FAILED_ES = _shell(
	title_html="No pudimos<br>cobrar tu cuota",
	body_html=(
		_p("Hola {{ student_name }},")
		+ _p("Intentamos cobrar tu cuota con el pago automático, pero no fue posible:", bottom=16)
		+ _detail_table(
			[
				("Concepto", "{{ fee_description }}"),
				("Monto", "<strong>{{ amount }}</strong>"),
				("Tarjeta", "{{ card }}"),
				("Motivo", "{{ failure_reason }}"),
			]
		)
		+ "{% if will_retry %}"
		'<p style="margin:16px 0 0 0;">Lo intentaremos de nuevo el <strong>{{ next_retry_date }}</strong>. '
		"Para evitar recargos, puedes pagar ahora desde el portal o actualizar tu tarjeta.</p>"
		"{% else %}"
		'<p style="margin:16px 0 0 0;">Pausamos el pago automático. Entra al portal para pagar la cuota '
		"y actualizar tu tarjeta; al hacerlo el pago automático se reactivará.</p>"
		"{% endif %}"
	),
	button_label=BTN_AUTOPAY_ES,
	sign_html=SIGN_ES,
)

_AUTOPAY_FAILED_EN = _shell(
	title_html="We could not<br>charge your installment",
	body_html=(
		_p("Hello {{ student_name }},")
		+ _p("We tried to charge your installment through automatic payments, but it did not go through:", bottom=16)
		+ _detail_table(
			[
				("Item", "{{ fee_description }}"),
				("Amount", "<strong>{{ amount }}</strong>"),
				("Card", "{{ card }}"),
				("Reason", "{{ failure_reason }}"),
			]
		)
		+ "{% if will_retry %}"
		'<p style="margin:16px 0 0 0;">We will try again on <strong>{{ next_retry_date }}</strong>. '
		"To avoid late fees, you can pay now from the portal or update your card.</p>"
		"{% else %}"
		'<p style="margin:16px 0 0 0;">Automatic payments are paused. Log in to the portal to pay the '
		"installment and update your card; doing so turns automatic payments back on.</p>"
		"{% endif %}"
	),
	button_label=BTN_AUTOPAY_EN,
	sign_html=SIGN_EN,
)


AUTOPAY_TEMPLATES = [
	{"name": "EdTools Autopay Activated ES", "subject": "Pago automático activado", "response": _AUTOPAY_ACTIVATED_ES},
	{"name": "EdTools Autopay Activated EN", "subject": "Automatic payments turned on", "response": _AUTOPAY_ACTIVATED_EN},
	{"name": "EdTools Autopay Reminder ES", "subject": "Tu cuota se cobrará el {{ charge_date }}", "response": _AUTOPAY_REMINDER_ES},
	{"name": "EdTools Autopay Reminder EN", "subject": "Your installment will be charged on {{ charge_date }}", "response": _AUTOPAY_REMINDER_EN},
	{"name": "EdTools Autopay Charged ES", "subject": "Recibimos tu pago de {{ amount }}", "response": _AUTOPAY_CHARGED_ES},
	{"name": "EdTools Autopay Charged EN", "subject": "We received your payment of {{ amount }}", "response": _AUTOPAY_CHARGED_EN},
	{"name": "EdTools Autopay Failed ES", "subject": "No pudimos cobrar tu cuota", "response": _AUTOPAY_FAILED_ES},
	{"name": "EdTools Autopay Failed EN", "subject": "We could not charge your installment", "response": _AUTOPAY_FAILED_EN},
]
