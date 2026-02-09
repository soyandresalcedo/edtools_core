# Customización del Portal del Estudiante – Dónde hacer cada cambio

> **Regla**: No modificar el repo original de Education (`apps/education`). Usar **edtools_core** para backend/APIs/comportamiento y **education-frontend-overrides** (repo principal) para la vista Vue del portal.

---

## 1. Resumen

| Tipo de cambio | Dónde hacerlo | Repo / carpeta |
|----------------|--------------|----------------|
| APIs, permisos, redirect, CSRF, DocTypes, lógica backend | **edtools_core** | Submódulo `apps/edtools_core` |
| Vista Vue del Student Portal (componentes, páginas) | **education-frontend-overrides** | Repo principal, carpeta `education-frontend-overrides/` en la raíz |

El submódulo **edtools_core** no contiene código Vue del portal; solo Python, hooks y JS/CSS globales (branding, Socket.IO). La vista del portal se personaliza con **overrides** que se copian sobre el frontend de Education en el build.

---

## 2. Qué hay en edtools_core (submódulo)

### 2.1 Backend y comportamiento del portal

| Archivo / hook | Qué hace |
|----------------|----------|
| **hooks.py** | `role_home_page` (Student → `/student-portal`), `website_path_resolver`, `website_redirects`, `standard_portal_menu_items`, `override_doctype_class`, `doc_events`, `doctype_js` (Student, Fee Structure). |
| **portal_redirect.py** | Redirect post-login: usuarios con rol Student van a `/student-portal` en lugar de `/me`. |
| **website_resolver.py** | `/student-portal` y `/student-portal/*` resuelven al mismo HTML (evita 404 al recargar en subrutas). |
| **student_portal_csrf.py** | Parche de contexto y render del template: CSRF válido, no-cache, logo/abbr por defecto (evita 417 y `{{ logo }}` sin renderizar). |
| **student_portal_api.py** | Inyección en `education.education.api`: `get_user_info`, `get_student_info`, `get_student_attendance`, `get_course_schedule_for_student`, `get_student_programs`, `get_student_invoices`, `get_school_abbr_logo`. Compat con Vue (develop) y Education v15. |
| **__init__.py** | Al cargar la app: `_patch_portal_redirect()`, `_patch_student_portal_csrf()`, `_patch_education_api()`. |

### 2.2 Overrides de DocTypes (Education)

- **overrides/course_enrollment.py** – Duplicados por `custom_academic_term`.
- **overrides/program_enrollment.py** – No crea/borra Course Enrollments al submit/cancel.

### 2.3 Validaciones y patches

- **validations/** – Enrollment (student status), Student (track status).
- **patches/** – Permisos de lectura del portal, redirect tras edit profile, default student status.
- **www/after_edit_profile.py** + **after-edit-profile.html** – Página y lógica tras editar perfil.

### 2.4 Assets globales (Desk + web)

Cargados vía `hooks.py` (no son parte del Vue del portal):

- **public/js/edtools.js** – Reemplazo de texto (branding Frappe/ERPNext → Edtools).
- **public/js/socketio_override.js** – Redirección de Socket.IO al servicio externo.
- **public/css/edtools.css** – Estilos de branding.
- **doctype_js**: `Student` → `student.js`, `Fee Structure` → `fee_structure_custom.js`.

### 2.5 Lo que NO está en edtools_core

- Código fuente Vue del Student Portal (Schedule, Attendance, Fees, Grades, Navbar, etc.). Ese código vive en `apps/education/frontend` (repo original) y se **sobrescribe** en build con `education-frontend-overrides`.

---

## 3. education-frontend-overrides (repo principal)

Carpeta en la **raíz del repo edtools-sis** (no dentro de edtools_core). En el Dockerfile:

1. Se obtiene el frontend de Education (GitHub develop o `apps/education/frontend`).
2. Se ejecuta: `cp -r education-frontend-overrides/* frontend/`.
3. Luego `yarn build` en `frontend/`.

Cualquier archivo que pongas en `education-frontend-overrides/` con la **misma ruta relativa** que en `education/frontend/src/` **reemplaza** al original en el build. Así no tocas el submodule Education.

Estructura actual de overrides:

```
education-frontend-overrides/
  src/
    components/
      FeesPaymentDialog.vue
      ProfileModal.vue
      Navbar.vue          ← ej. botón "Apply for Leave" comentado aquí
    pages/
      Attendance.vue
      Schedule.vue
```

Para cambiar la **vista** del portal (botones, textos, formularios, páginas):

- Añade o edita el archivo en `education-frontend-overrides/src/` con la misma ruta que en `apps/education/frontend/src/` (p. ej. `components/Navbar.vue`, `pages/Attendance.vue`).
- Tras el próximo build de la imagen, se usará tu versión.

---

## 4. Regla práctica

- **No editar** `apps/education/` para customización (evitas conflictos al actualizar el submodule).
- **Backend / comportamiento del portal** (APIs, redirect, permisos, CSRF, DocTypes) → **edtools_core**.
- **Vista del portal (Vue)** → **education-frontend-overrides** en el repo principal.

Si en el futuro quieres tener los overrides Vue dentro del submódulo edtools_core, se puede mover la carpeta a `edtools_core/frontend_overrides/` y ajustar el Dockerfile para copiar desde ahí (por ejemplo desde `/tmp/edtools-repo/apps/edtools_core/frontend_overrides`).

---

*Última actualización: Feb 2026*
