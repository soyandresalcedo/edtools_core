# Plan: Azure provisioning sin duplicación de usuarios

Objetivo: crear el usuario en Azure AD y asignar licencia Microsoft 365 cuando se inscribe un Student Applicant, **sin crear nunca el User de Frappe en nuestro código**; que la API de Education siga siendo la única que crea el User en Frappe.

---

## 1. Origen de los errores de duplicación (resumen)

- **Dos sitios creaban User:** `enrollment.py` (`_ensure_user`) y `Student.validate_user` (Education). Aunque el flag `azure_provisioning_enroll` hacía que Student no creara User, el flujo era frágil.
- **Réplicas de BD:** con PostgreSQL en Railway, `frappe.db.exists("User", email)` a veces lee de réplica y devuelve `False` aunque el User ya exista en el primario; al hacer `insert()` salía "duplicate key".
- **Conclusión:** para evitar duplicados, el User en Frappe debe crearse **solo en un lugar**: la API de Education (vía `Student.validate_user`).

---

## 2. Principio del nuevo flujo

- **Frappe (Student + User + Program Enrollment):** lo hace siempre la API de Education (`enroll_student`). Nosotros no creamos User en `enrollment.py`.
- **Azure:** solo llamadas a Microsoft Graph (crear usuario en Azure AD + asignar licencia). Si el usuario ya existe en Azure, no fallar; solo asignar licencia si falta.

Así no hay dos flujos que compitan por crear el mismo User en Frappe.

---

## 3. Flujo propuesto (Azure habilitado)

Cuando **Azure provisioning está habilitado** y en el Program Enrollment Tool se inscribe desde **Student Applicant**:

```
1. Generar email @cucusa.org y contraseña temporal
   └─ generate_cucusa_email(applicant) + _generate_temp_password()

2. Azure AD
   └─ Crear usuario en Azure (o reusar si ya existe)
   └─ Asignar licencia (idempotente: si ya tiene, no fallar)

3. Actualizar Student Applicant
   └─ student_email_id = email institucional (para que el mapper lo copie)

4. Llamar a la API de Education (única creación de User en Frappe)
   └─ enroll_student(applicant)  ← Education crea Student + User + Program Enrollment
   └─ Con flag para: no enviar welcome estándar; después nosotros enviamos credenciales

5. Sincronizar contraseña en Frappe
   └─ update_password(user_email, temp_password)

6. Enviar correo de credenciales al correo personal
   └─ _send_credentials_email(personal_email, ...)
```

Nunca creamos el User en nuestro código; solo Azure (paso 2) y Education (paso 4).

---

## 4. Cambios por componente

### 4.1 Student.validate_user (edtools_core)

- Cuando `frappe.flags.azure_provisioning_enroll` está activo y el email es @cucusa.org:
  - **No** hacer “si existe User, solo enlazar y return”.
  - **Sí** crear el User (como hace ahora sin Azure) pero con `send_welcome_email=0`, y **no** llamar a `send_welcome_mail_to_user()`.
  - Así el User se crea **solo aquí** (vía Education), y el único correo que recibe el estudiante es el de credenciales (paso 6 de enrollment.py), **no** el welcome estándar de Frappe. Evita doble notificación al correo personal.

Es decir: con Azure, validate_user debe **crear** el User una sola vez, sin enviar el welcome estándar; la bienvenida con credenciales la envía el flujo de enrollment.

### 4.2 enrollment.py (nuevo flujo, sin crear User)

- **Eliminar** toda la lógica que crea User en Frappe (`_ensure_user`, `_set_password_and_share_for_user`, etc.).
- La función `enroll_student_with_azure_provisioning` debe:
  1. Generar email + contraseña.
  2. Llamar a Azure: crear usuario (o obtener si ya existe) + asignar licencia.
  3. Actualizar Applicant (`student_email_id` = email institucional).
  4. Poner `frappe.flags.azure_provisioning_enroll = True`.
  5. Llamar a `enroll_student(source_name)` de Education (que crea Student + User en Frappe vía validate_user).
  6. Tras el return, `update_password(institutional_email, password)`.
  7. `_send_credentials_email(personal_email, ...)`.
  8. Limpiar el flag.

Así, el único que crea el User en Frappe es Education (Student.validate_user).

### 4.3 azure_provisioning.py

- **create_azure_user:** si la API de Graph devuelve “user already exists” (p. ej. 400 con código conocido), en lugar de fallar:
  - Llamar a `GET /users/{userPrincipalName}` (o por mail) para obtener el `id` del usuario.
  - Devolver ese `id` para usarlo en `assign_microsoft_license`.
- **assign_microsoft_license:** si la licencia ya está asignada, no lanzar error (tratar como éxito o ignorar el error concreto de “ya asignada” si Graph lo devuelve).

Con esto el flujo es idempotente frente a reintentos o usuarios ya creados en Azure.

### 4.4 Program Enrollment Tool

- Para **Student Applicant** con Azure habilitado: llamar a `enroll_student_with_azure_provisioning(stud.student_applicant)` (como en el bloque comentado).
- Para **Student** ya existente: seguir con el flujo actual (solo Program Enrollment, sin Azure).

---

## 5. Orden de implementación sugerido

1. **azure_provisioning.py**
   - Hacer `create_azure_user` idempotente: si el usuario ya existe en Azure, obtener su `id` y devolverlo.
   - Hacer `assign_microsoft_license` tolerante a “licencia ya asignada”.

2. **Student.validate_user**
   - Ajustar el caso “Azure + @cucusa.org”: crear User con `send_welcome_email=0` y no enviar welcome; solo asignar `self.user = ...` después de crear. No hacer “return sin crear” cuando el flag está activo.

3. **enrollment.py**
   - Reescribir `enroll_student_with_azure_provisioning` para que:
     - No cree User en Frappe.
     - Solo: generar email/password → Azure → actualizar Applicant → llamar a Education `enroll_student` → update_password → enviar credenciales.

4. **Program Enrollment Tool**
   - Descomentar y adaptar el bloque que usa `enroll_student_with_azure_provisioning` para applicants cuando Azure esté habilitado.

5. **Pruebas**
   - Con Azure en sandbox: inscribir un Applicant y comprobar que se crea un solo User en Frappe, que existe en Azure (o sandbox) con licencia y que el estudiante recibe el correo de credenciales.
   - Reintentar el mismo Applicant (o mismo email) y comprobar que no hay duplicados ni errores por “ya existe”.

---

## 6. Configuración y documentación

- Mantener las mismas variables de entorno / `site_config` que en AZURE_PROVISIONING.md.
- Actualizar AZURE_PROVISIONING.md para describir el flujo nuevo (Education como única fuente del User en Frappe) y quitar o simplificar la sección de “duplicate key” / script de recuperación, dejando el script solo para casos excepcionales (réplicas, etc.).

---

## 7. Resumen

| Antes (duplicación) | Después (sin duplicación) |
|--------------------|---------------------------|
| enrollment.py creaba User en Frappe | enrollment.py no crea User |
| Student.validate_user podía no crear (solo enlazar) con el flag | Student.validate_user siempre crea el User cuando no existe (con flag: sin welcome) |
| Dos sitios podían crear el mismo User | Solo Education (validate_user) crea el User |
| Azure: create + assign | Azure: create-or-get + assign (idempotente) |

Con esto se implementa la creación de usuario y asignación de licencia en Azure sin generar los errores de duplicación que se presentaron antes, aprovechando que ahora los usuarios se crean correctamente con la API de Education.
