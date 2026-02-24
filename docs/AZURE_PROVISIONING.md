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

### Verificar configuración (provisioning no activo)

Si el enrollment crea Student con @cucusa.org pero **no** crea el User en Frappe, confirma que el provisioning está habilitado:

```python
# bench --site cucuniversity.edtools.co console
from edtools_core.azure_provisioning import is_provisioning_enabled
print("Provisioning activo:", is_provisioning_enabled())
```

Si devuelve `False`, añade a `site_config.json` o variables de entorno:

- `azure_provisioning_enabled`: `1`
- `azure_provisioning_sandbox`: `1` (para pruebas sin Azure real)

### 404 al hacer clic en User ID del Student

Si el Student se creó pero el enlace al User da 404, el User puede no existir (por un enrollment anterior con errores) o hay registros huérfanos en `tabHas Role`. Usar este script robusto en bench console:

```python
# bench --site cucuniversity.edtools.co console
import frappe

email = "camilo.villalobos.fernandez@cucusa.org"  # usar el email del Student
first_name = "Camilo"   # del Student
last_name = "Villalobos Fernandez"  # del Student

# Usar get_doc para evitar duplicados y desfase de réplicas
try:
    user = frappe.get_doc("User", email)
    if "Student" not in [r.role for r in user.roles]:
        user.add_roles("Student")
        user.save(ignore_permissions=True)
    frappe.db.commit()
    print("User ya existía, rol Student verificado")
except frappe.DoesNotExistError:
    try:
        user = frappe.get_doc({
            "doctype": "User",
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "user_type": "Website User",
            "send_welcome_email": 0,
        })
        user.add_roles("Student")
        user.insert(ignore_permissions=True)
        frappe.db.commit()
        print("User creado")
    except (frappe.DuplicateEntryError, frappe.UniqueValidationError, Exception) as e:
        if "duplicate" in str(e).lower() or "unique" in str(e).lower() or "already exists" in str(e).lower():
            frappe.db.rollback()
            user = frappe.get_doc("User", email)
            if "Student" not in [r.role for r in user.roles]:
                user.add_roles("Student")
                user.save(ignore_permissions=True)
            frappe.db.commit()
            print("User existía (duplicado detectado), rol verificado")
        else:
            raise
```

**Nota:** Si usas réplicas de solo lectura (ej. DBeaver conectado a réplica de Railway), el `SELECT` puede devolver vacío aunque el User exista en el primario. Ejecuta el script en bench console (que usa el nodo primario) o verifica la conexión de DBeaver al nodo de escritura.
