# Integración Stripe – Portal del Estudiante (CUC University)

## 1. Cómo funciona la API de Stripe (resumen)

- **Stripe** es el procesador de pagos. El estudiante paga con tarjeta en Stripe; el dinero va a tu **Stripe Connect** o cuenta estándar; luego puedes hacer transferencias a tu cuenta de banco (FirstBank Florida) desde el dashboard de Stripe.
- **Modo prueba (sandbox)**:
  - Usas **claves de prueba** (publishable key y secret key que empiezan con `pk_test_` y `sk_test_`).
  - No se mueve dinero real. Tarjetas de prueba: `4242 4242 4242 4242`, cualquier fecha futura, cualquier CVC.
- **Flujo que implementamos**:
  1. Estudiante hace clic en **Pay Now** en una cuota (Fees).
  2. El backend (edtools_core) crea un **PaymentIntent** en Stripe con el monto y metadata (fee, estudiante).
  3. El backend devuelve el **client_secret** del PaymentIntent al frontend.
  4. El frontend carga **Stripe.js** y muestra el formulario de tarjeta (Elements); el usuario completa y confirma.
  5. Stripe procesa el pago y confirma.
  6. El frontend llama a **`finalize_payment_and_get_volante`**: el backend verifica el PaymentIntent en Stripe, crea (o reutiliza) una **Payment Entry en borrador** (`docstatus = 0`) y devuelve la URL del PDF **Volante / Bolante de Pago** (`Fees` + print format `Bolante de Pago`) para abrirlo al instante.
  7. Stripe puede enviar además el **webhook** `payment_intent.succeeded`; el mismo código de creación de Payment Entry es **idempotente** por `reference_no = payment_intent_id` (no duplica si el paso 6 ya corrió).
  8. El `outstanding_amount` del Fee se actualiza cuando **Tesorería somete** la Payment Entry (flujo normal de ERPNext).

## 2. Claves y configuración

- **Clave pública (publishable key)**: `pk_test_...` para pruebas. Va en el frontend (Stripe.js) para tokenizar la tarjeta. No es secreta.
- **Clave secreta (secret key)**: `sk_test_...` para pruebas. Solo en el backend; nunca en el frontend. Se usa para crear PaymentIntents y para verificar el webhook.
- En producción usarás `pk_live_...` y `sk_live_...` y conectarás tu cuenta de banco (FirstBank Florida) en Stripe.

Configuración en EdTools:
- Las claves se guardan en **Site Config** (o variables de entorno) para no hardcodear.
- Claves usadas:
  - `stripe_secret_key`: para backend (crear PaymentIntent, verificar webhook).
  - `stripe_publishable_key`: para frontend (opcional si pasas desde backend por API; o se puede exponer en el template del student-portal).
  - `stripe_webhook_secret`: (whitelist endpoint) para verificar que el webhook viene de Stripe.

## 3. Dónde está implementado

| Parte | Ubicación |
|-------|-----------|
| Crear PaymentIntent (API) | `edtools_core.stripe_payment.create_payment_intent` |
| Tras pago exitoso: PE borrador + URL volante PDF | `edtools_core.stripe_payment.finalize_payment_and_get_volante` |
| Webhook Stripe | `edtools_core.stripe_payment.stripe_webhook` (URL pública) |
| Configuración (claves) | Site Config o variables de entorno: `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, etc. |
| Vista "Pay Now" | Override en `education-frontend-overrides`: `FeesPaymentDialog.vue` (Stripe Elements) |

## 4. Idempotencia y duplicados

- Cada **PaymentIntent** tiene un `id` único. En **`Payment Entry.reference_no`** se guarda ese id. Antes de insertar, se comprueba si ya existe una PE con ese `reference_no` en **borrador o enviada** (`docstatus` 0 o 1). Si existe, se devuelve la misma y no se crea otra.
- Así se evitan duplicados si Stripe reenvía el webhook, el estudiante reintenta **Descargar volante**, o el frontend llama dos veces a `finalize_payment_and_get_volante`.

### Checklist manual (sandbox)

1. Pagar una cuota con tarjeta de prueba; comprobar que se abre el **PDF del volante** al terminar.
2. En Desk: la **Payment Entry** nueva debe estar en **Borrador** hasta que alguien la someta.
3. Llamar dos veces a finalize con el mismo `payment_intent_id` (o usar **Descargar volante** en estado “Validando pago…”): una sola PE.
4. Tras llegar el **webhook**, sigue habiendo una sola PE con ese `reference_no`.

## 5. Configuración

**Railway (recomendado):** En el servicio web → Variables, añade:
- `STRIPE_SECRET_KEY` = `sk_test_...` (o `sk_live_...`)
- `STRIPE_PUBLISHABLE_KEY` = `pk_test_...` (o `pk_live_...`)
- Opcional: `STRIPE_WEBHOOK_SECRET`, `STRIPE_MODE_OF_PAYMENT`, `STRIPE_PAID_TO_ACCOUNT`

**Alternativa (site_config.json):** En `sites/<tu-sitio>/site_config.json`:

```json
{
  "stripe_secret_key": "sk_test_...",
  "stripe_publishable_key": "pk_test_...",
  "stripe_webhook_secret": "whsec_...",
  "stripe_mode_of_payment": "Stripe",
  "stripe_paid_to_account": "Stripe - CUCUSA"
}
```

- **stripe_secret_key** y **stripe_publishable_key**: obligatorios. En sandbox usas las claves de prueba (`pk_test_`, `sk_test_`).
- **stripe_webhook_secret**: necesario para que el webhook cree el Payment Entry. En desarrollo lo obtienes con Stripe CLI (ver más abajo).
- **stripe_mode_of_payment**: modo de pago en ERPNext (ej. "Stripe"). Debe existir y tener una cuenta por defecto para tu Company.
- **stripe_paid_to_account**: cuenta donde “entra” el pago (ej. "Stripe - CUCUSA"). Debe existir en tu Company; si no configuras, se intenta usar la cuenta por defecto del Mode of Payment.

## 6. Pruebas en sandbox

1. Configura en Site Config (o variables de entorno): `stripe_secret_key`, `stripe_publishable_key`.
2. Crea en ERPNext un **Mode of Payment** "Stripe" y asígnale una cuenta (ej. "Stripe - CUCUSA") en la Company que usen los Fees. Opcional: configura `stripe_paid_to_account` en site_config.
3. En el portal del estudiante, ve a Fees y haz clic en **Pay Now** en una cuota con saldo.
4. Al hacer clic en **Proceed to Payment** se crea el PaymentIntent y aparece el formulario de tarjeta. Usa tarjeta de prueba: **4242 4242 4242 4242**, fecha futura, CVC cualquiera (ej. 123).
5. Tras **Pay Now**, Stripe confirma el pago. El portal llama a **finalize** (PE en borrador + PDF). El **webhook** es respaldo idempotente. Si finalize falla por red pero el webhook llega, igual quedará la PE en borrador. El Fee pasa a “pagado” en el portal cuando la PE se **someta** y el saldo del Fee se actualice.
6. Para probar el webhook en local o en un entorno sin URL pública: instala **Stripe CLI** y ejecuta:
   ```bash
   stripe listen --forward-to https://cucuniversity.edtools.co/api/method/edtools_core.stripe_payment.stripe_webhook
   ```
   El CLI te dará un `whsec_...`; ponlo en `stripe_webhook_secret` en site_config (o en variables de entorno) y reinicia/recarga.

## 7. Producción (FirstBank Florida)

- En Stripe Dashboard cambias a modo Live y añades las claves `pk_live_` y `sk_live_` en Site Config.
- Configuras la **cuenta bancaria** (FirstBank Florida) en Stripe: Settings → Payouts. Los pagos que lleguen a Stripe se pueden programar para transferencia a esa cuenta.
- El webhook en producción debe usar la URL pública de tu sitio (p. ej. `https://cucuniversity.edtools.co/...`) y el `stripe_webhook_secret` del webhook creado en el Dashboard de Stripe (modo Live).
