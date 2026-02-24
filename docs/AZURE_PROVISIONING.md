# Azure Provisioning - Student Applicant

Provisioning automático de cuentas @cucusa.org al matricular Student Applicants desde el Program Enrollment Tool.

## Activar el flujo (modo sandbox)

**Variables de entorno (Railway)** o `site_config.json`:

| Variable | Sandbox | Producción |
|----------|---------|------------|
| `AZURE_PROVISIONING_ENABLED` | `1` | `1` |
| `AZURE_PROVISIONING_SANDBOX` | `1` | `0` |
| `AZURE_PROVISIONING_TENANT_ID` | (opcional) | Obligatorio |
| `AZURE_PROVISIONING_CLIENT_ID` | (opcional) | Obligatorio |
| `AZURE_PROVISIONING_CLIENT_SECRET` | (opcional) | Obligatorio |
| `AZURE_PROVISIONING_SKU_ID` | (opcional) | Opcional (default: O365 E3) |

Alternativa en `site_config.json`: `azure_provisioning_enabled`, `azure_provisioning_sandbox`, etc.

Con `AZURE_PROVISIONING_ENABLED=0` o ausente, el flujo vuelve al comportamiento original de Education.

## Campos en Student Applicant

- **personal_email** (nuevo): Correo personal donde enviar las credenciales. Obligatorio si provisioning está activo.
- **institutional_email** (nuevo, solo lectura): Se llena automáticamente con el @cucusa.org generado.
- **student_email_id**: Durante la aplicación puede ser el personal. Al matricular con provisioning, se sobrescribe con @cucusa.org.

## Formato del email institucional

`nombre.primerapellido.segundoapellido@cucusa.org` (minúsculas, sin acentos).

Si el correo ya existe (User o Student), no se crea uno nuevo: se lanza un error y el admin debe revisar si el estudiante ya está matriculado.

## Probar en sandbox

1. Activar `azure_provisioning_enabled` y `azure_provisioning_sandbox`.
2. Crear un Student Applicant con **Correo personal** (o usar student_email_id como fallback).
3. Aprobar el Applicant.
4. En Program Enrollment Tool: Get Students From = Student Applicant, seleccionar y Enroll.
5. Se creará Student, User (@cucusa.org), Program Enrollment y se enviará email con credenciales al correo personal.

## Solución de problemas

### 404 al hacer clic en User ID del Student

Si el Student se creó pero el enlace al User da 404, el User puede no existir (por un enrollment anterior con errores). Crear el User manualmente en bench console:

```python
# bench --site cucuniversity.edtools.co console
import frappe
email = "camilo.villalobos.fernandez@cucusa.org"  # usar el email del Student
if not frappe.db.exists("User", email):
    user = frappe.get_doc({
        "doctype": "User",
        "email": email,
        "first_name": "Camilo",
        "last_name": "Villalobos Fernandez",
        "user_type": "Website User",
        "send_welcome_email": 0,
    })
    user.add_roles("Student")
    user.insert(ignore_permissions=True, ignore_if_duplicate=True)
    frappe.db.commit()
    print("User creado")
else:
    print("User ya existe")
```
