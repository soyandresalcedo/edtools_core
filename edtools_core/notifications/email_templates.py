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
	title_html="{% if is_correction %}Calificación<br>actualizada{% else %}Calificaciones<br>publicadas{% endif %}",
	body_html=(
		'<p style="margin:0 0 12px 0;">Hola {{ student_name }},</p>'
		"{% if is_correction %}"
		'<p style="margin:0 0 16px 0;">Se actualizó la calificación en tu record académico:</p>'
		"{% else %}"
		'<p style="margin:0 0 16px 0;">Se publicaron calificaciones en tu record académico:</p>'
		"{% endif %}"
		"{{ grades_table_html | safe }}"
	),
	button_label=BTN_ES,
	sign_html=SIGN_ES,
)

_GRADE_POSTED_EN = _shell(
	title_html="{% if is_correction %}Grade<br>updated{% else %}Grades<br>published{% endif %}",
	body_html=(
		'<p style="margin:0 0 12px 0;">Hello {{ student_name }},</p>'
		"{% if is_correction %}"
		'<p style="margin:0 0 16px 0;">Your grade record has been updated:</p>'
		"{% else %}"
		'<p style="margin:0 0 16px 0;">Grades have been published to your academic record:</p>'
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
		"subject": "{% if is_correction %}Calificación actualizada{% else %}Calificaciones publicadas{% endif %}",
		"response": _GRADE_POSTED_ES,
	},
	{
		"name": "EdTools Grade Posted EN",
		"subject": "{% if is_correction %}Grade updated{% else %}Grades published{% endif %}",
		"response": _GRADE_POSTED_EN,
	},
]

BRANDED_TEMPLATES_BY_NAME = {tpl["name"]: tpl for tpl in BRANDED_TEMPLATES}
