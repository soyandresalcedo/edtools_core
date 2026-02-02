# edtools_core/moodle_users.py

from typing import Optional, Dict
import frappe

from edtools_core.moodle_integration import _moodle_post

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _build_firstname(first_name: str, middle_name: Optional[str]) -> str:
    if middle_name:
        return f"{first_name} {middle_name}".strip()
    return first_name.strip()

def _get_student_idnumber(student) -> str:
    """
    ID externo para Moodle.
    Usamos el name del Student (ej: EDU-STU-2026-00001)
    """
    return student.name

# ------------------------------------------------------------
# Moodle API – Users
# ------------------------------------------------------------

def _get_student_email(student) -> str:
    """
    Obtiene el email REAL del estudiante a través del User asociado.
    Student.user -> User.email
    """
    if not student.user:
        frappe.throw(
            f"El estudiante {student.name} no tiene un User asociado"
        )

    user = frappe.get_doc("User", student.user)

    if not user.email:
        frappe.throw(
            f"El usuario {user.name} no tiene email configurado"
        )

    return _normalize_email(user.email)

def get_user_by_email(email: str) -> Optional[Dict]:
    """
    Busca un usuario en Moodle por email.
    Retorna el usuario si existe, None si no.
    """
    email = _normalize_email(email)

    payload = {
        "criteria[0][key]": "email",
        "criteria[0][value]": email
    }

    response = _moodle_post(
        wsfunction="core_user_get_users",
        data=payload
    )
    if isinstance(response, dict) and response.get("exception"):
        frappe.throw(
            f"Moodle error (get_user_by_email): {response.get('message')}"
        )
    
    users = response.get("users", [])
    return users[0] if users else None


def create_moodle_user(student) -> Dict:
    """
    Crea un usuario en Moodle usando core_user_create_users.
    El username se genera desde el email (antes del @).
    El password se genera automáticamente y se envía por correo.
    """
    email = _get_student_email(student)
    username = email.split("@")[0]

    firstname = _build_firstname(
        student.first_name,
        getattr(student, "middle_name", None)
    )

    payload = {
        # Identidad
        "users[0][username]": username,
        "users[0][auth]": "manual",

        # Datos personales
        "users[0][firstname]": firstname,
        "users[0][lastname]": student.last_name,
        "users[0][email]": email,

        # Campo "Número de ID" (sección Opcional en Moodle)
        "users[0][idnumber]": _get_student_idnumber(student),

        # Configuración estándar institucional
        "users[0][lang]": "es",
        "users[0][timezone]": "99",
        "users[0][mailformat]": 1,

        # Moodle crea password y envía correo
        "users[0][createpassword]": 1,
    }

    response = _moodle_post(
        wsfunction="core_user_create_users",
        data=payload
    )
    if isinstance(response, dict) and response.get("exception"):
        frappe.throw(
            f"Moodle error (create_user): {response.get('message')}"
        )
    # Moodle retorna una lista de usuarios creados
    return response[0]


def update_user_idnumber(user_id: int, new_idnumber: str) -> None:
    """
    Actualiza únicamente el campo idnumber (Número de ID)
    de un usuario existente en Moodle.
    """
    payload = {
        "users[0][id]": user_id,
        "users[0][idnumber]": new_idnumber
    }

    response = _moodle_post(
        wsfunction="core_user_update_users",
        data=payload
    )
    if isinstance(response, dict) and response.get("exception"):
        frappe.throw(
            f"Moodle error (update_user): {response.get('message')}"
        )


def ensure_moodle_user(student) -> Dict:
    """
    Garantiza que el estudiante tenga usuario en Moodle.

    Flujo:
    - Busca por email
    - Si no existe → crea usuario
    - Si existe y el idnumber es distinto → actualiza idnumber
    - Retorna el usuario de Moodle
    """

    email = _get_student_email(student)
    frappe.log_error(
        title="DEBUG ensure_moodle_user",
        message=f"Procesando estudiante {student.name} - {email}"
    )
    user = get_user_by_email(email)

    # Caso 1: no existe → crear
    if not user:
        frappe.log_error(
            title="DEBUG ensure_moodle_user",
            message=f"Usuario no existe en Moodle, creando: {email}"
        )
        return create_moodle_user(student)

    # Caso 2: existe → validar idnumber
    current_idnumber = (user.get("idnumber") or "").strip()
    expected_idnumber = _get_student_idnumber(student)

    if current_idnumber != expected_idnumber:
        update_user_idnumber(
            user_id=user["id"],
            new_idnumber=expected_idnumber
        )
        # refrescar el valor local
        user["idnumber"] = expected_idnumber

    return user
