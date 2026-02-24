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

`primernombre.segundonombre.apellido1.apellido2@cucusa.org` (minúsculas, sin acentos). Incluye el segundo nombre si está definido en el Applicant.

Si el correo ya existe (User o Student), no se crea uno nuevo: se lanza un error y el admin debe revisar si el estudiante ya está matriculado.

## Logs y correo de credenciales

- **Logs de simulación (SANDBOX=1):** Los mensajes `[Azure Sandbox] Simulando...` van al **log del servidor** (stdout), no al Registro de Errores de Frappe. En Railway: pestaña **Deployments** → tu servicio → **View Logs**.
- **Correo de credenciales no llega:** Comprueba en Frappe: **Configuración → Email → Email Account**: debe haber una cuenta saliente por defecto. Si el envío falla, en **Registro de Errores** aparecerá una entrada con título "Error enviando credenciales al estudiante".

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

### 404 al hacer clic en User ID del Student / "User not found" pero "duplicate key" al crear

Si el Student se creó pero el enlace al User da 404, o si en bench console **get_doc("User", email)** da "not found" y al hacer **user.insert()** sale "duplicate key tabUser_pkey", suele ser **desfase réplica/primario**: la lectura no ve el User pero la escritura sí lo encuentra. Usar este script **solo con SQL en la misma conexión** (bench console):

```python
# bench --site cucuniversity.edtools.co console
# Copiar y pegar TODO el bloque de una vez (incluye las 3 líneas finales).
import frappe

email = "camilo.villalobos.fernandez@cucusa.org"  # usar el email del Student
first_name = "Camilo"
last_name = "Villalobos Fernandez"

frappe.clear_cache(doctype="User")
# Comprobar existencia con SQL en la misma conexión que la escritura (evita réplica)
exists = frappe.db.sql('SELECT 1 FROM "tabUser" WHERE name = %s LIMIT 1', (email,))
if exists:
    # User existe en BD. Añadir rol Student por SQL si falta (sin usar get_doc por si lee de réplica).
    has_role = frappe.db.sql(
        'SELECT 1 FROM "tabHas Role" WHERE parent = %s AND parenttype = %s AND role = %s LIMIT 1',
        (email, "User", "Student"),
    )
    if not has_role:
        name_hr = frappe.generate_hash(length=10)
        frappe.db.sql("""
            INSERT INTO "tabHas Role" (name, parent, parenttype, role, creation, modified, modified_by, owner, docstatus, idx)
            VALUES (%s, %s, 'User', 'Student', NOW(), NOW(), %s, %s, 0, 0)
        """, (name_hr, email, frappe.session.user or "Administrator", frappe.session.user or "Administrator"))
    frappe.db.commit()
    print("User ya existía, rol Student verificado/añadido por SQL")
else:
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
    except frappe.DuplicateEntryError:
        frappe.db.rollback()
        frappe.db.commit()
        frappe.clear_cache(doctype="User")
        # Existe en primario pero no en nuestra lectura. Añadir rol por SQL.
        has_role = frappe.db.sql(
            'SELECT 1 FROM "tabHas Role" WHERE parent = %s AND parenttype = %s AND role = %s LIMIT 1',
            (email, "User", "Student"),
        )
        if not has_role:
            name_hr = frappe.generate_hash(length=10)
            frappe.db.sql("""
                INSERT INTO "tabHas Role" (name, parent, parenttype, role, creation, modified, modified_by, owner, docstatus, idx)
                VALUES (%s, %s, 'User', 'Student', NOW(), NOW(), %s, %s, 0, 0)
            """, (name_hr, email, frappe.session.user or "Administrator", frappe.session.user or "Administrator"))
            frappe.db.commit()
        print("User existía en primario (duplicado al insertar), rol Student verificado/añadido por SQL")
```

**Nota:** Si usas réplicas de solo lectura (ej. DBeaver/pgAdmin conectado a réplica de Railway), el `SELECT` puede devolver vacío aunque el User exista en el primario. Ejecuta el script en bench console (que usa el nodo primario) o verifica la conexión de DBeaver al nodo de escritura.

**Por qué la herramienta falla pero el User no aparece en tu SELECT:** Si el error es "duplicate key tabUser_pkey" y en pgAdmin/DBeaver no ves ese usuario, casi siempre es porque estás consultando una **réplica de solo lectura** o **otra base de datos**. La app escribe en el nodo primario; si hay réplicas, el User puede existir solo en el primario. Solución: ejecuta el script de recuperación desde **bench console** (misma conexión que la app) y vuelve a intentar la herramienta.

**Conexión pública en Railway (USE_PUBLIC_PGHOST):** Si en el entrypoint usas `USE_PUBLIC_PGHOST=1` y la URL pública de Postgres, las lecturas y escrituras pueden ir por rutas distintas (réplica vs primario), por eso a veces `get_doc` no ve al User y el `insert` devuelve "duplicate key". El código de enrollment está preparado para que, ante **DuplicateEntryError**, se asuma que el User existe y se continúe sin lanzar error; si fallan `update_password` o DocShare por no ver al User, se registra en Error Log y el enrollment termina igual (Student y Program Enrollment se crean). Luego puedes ejecutar el script de recuperación para fijar contraseña y rol.

### Verificar registros huérfanos (tabUser, tabHas Role, tabDocShare)

Si ves errores como `duplicate key "tabUser_pkey"` o `tabHas Role_pkey`, puede haber registros duplicados o filas huérfanas. En el repo está **`docs/VERIFICAR_REGISTROS_FANTASMAS_USER.sql`**: ábrelo en pgAdmin (o psql) y ejecuta las consultas. Las consultas 1–3 listan duplicados/huérfanos; la 4 da conteos. Las sentencias DELETE al final están comentadas; úsalas solo tras revisar y hacer backup.
