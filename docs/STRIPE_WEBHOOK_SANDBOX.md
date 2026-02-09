# Cómo crear el webhook en el sandbox de Stripe

Así configuras el webhook en modo **test** para que Stripe llame a tu backend cuando un pago sea exitoso.

---

## 1. Entrar al Dashboard en modo Test

1. Entra a [https://dashboard.stripe.com](https://dashboard.stripe.com) e inicia sesión.
2. **Activa el modo Test** (interruptor "Test mode" en la esquina superior derecha debe estar en ON). Así usas las claves `pk_test_...` y `sk_test_...`.

---

## 2. Crear el endpoint del webhook

1. En el menú lateral: **Developers** → **Webhooks**.
2. Pulsa **Add endpoint** (o "Add an endpoint").
3. **Endpoint URL**:
   - Si pruebas en **local** (ej. `http://localhost:8080`):
     - Stripe no puede llamar a localhost. Tienes que usar **Stripe CLI** para reenviar eventos (ver sección 4 más abajo).
   - Si tu sitio está en **Internet** (ej. Railway, cucuniversity.edtools.co):
     ```
     https://cucuniversity.edtools.co/api/method/edtools_core.stripe_payment.stripe_webhook
     ```
4. En **Select events to listen to**, elige:
   - **payment_intent.succeeded**
5. Pulsa **Add endpoint**.

---

## 3. Copiar el Signing secret

1. Después de crear el endpoint, se abre la página del webhook.
2. En **Signing secret** pulsa **Reveal**.
3. Verás algo como: `whsec_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
4. **Cópialo** y añádelo en tu `site_config.json`:
   ```json
   "stripe_webhook_secret": "whsec_..."
   ```
5. Reinicia el servidor (o recarga la configuración) para que lea el nuevo valor.

Sin este secret, el backend no puede verificar que el POST viene de Stripe y rechazará el webhook.

---

## 4. Probar en local con Stripe CLI (opcional)

Si tu app está en **localhost**, Stripe no puede enviar el webhook a tu máquina. Puedes usar **Stripe CLI** para reenviar los eventos:

1. Instala Stripe CLI: [https://stripe.com/docs/stripe-cli](https://stripe.com/docs/stripe-cli)
2. Inicia sesión: `stripe login`
3. Reenvía eventos al endpoint **público** de tu app (por ejemplo tu URL en Railway):
   ```bash
   stripe listen --forward-to https://cucuniversity.edtools.co/api/method/edtools_core.stripe_payment.stripe_webhook
   ```
4. El CLI mostrará un **Signing secret** temporal, por ejemplo: `whsec_...`
5. Pon ese valor en `stripe_webhook_secret` en tu site_config (o en las variables de entorno del servidor que recibe el webhook, es decir Railway).

Así, cuando hagas un pago de prueba, el CLI enviará el evento a tu URL y podrás ver en los logs que el webhook se ejecutó.

---

## 5. Ver que el pago se refleja en el sandbox

1. En el Dashboard de Stripe (modo Test): **Payments**.
2. Después de hacer "Pay Now" en el student portal con tarjeta `4242 4242 4242 4242`, debe aparecer un pago nuevo con estado **Succeeded**.
3. Ahí ves el monto, la moneda y el `payment_intent_id` (ej. `pi_...`).

Con el webhook configurado y el secret en site_config, tu backend recibirá `payment_intent.succeeded`. Por ahora solo se registra en el Error Log (sin crear Payment Entry); cuando quieras activar la creación del PE, se descomenta el código indicado en `stripe_payment.py`.
