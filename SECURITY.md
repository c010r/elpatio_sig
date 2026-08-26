# SECURITY.md — El Patio SIG

> Documento de seguridad del sistema **El Patio SIG** (Django 5.2 LTS, gestión de
> pub: ventas, inventario, caja, roles). Redactado por el **agente de Seguridad
> Informática**. Fase 1 (auditoría de settings/núcleo + endurecimiento aplicado);
> Fase 2 pendiente (revisión OWASP de models/views/forms/templates cuando el
> backend y el frontend terminen).

## Alcance y propiedad

| Área | Dueño | Estado |
|---|---|---|
| `config/settings/prod.py` | Seguridad | ✔ endurecido (Fase 1) |
| `config/settings/base.py` | Backend (seguridad: partes de seguridad) | ✔ fix urgente de redirects de login (Fase 1) |
| `.env.example` | Seguridad | ✔ actualizado (Fase 1) |
| `core/security_views.py` | Seguridad (nuevo) | ✔ creado (Fase 1) |
| `SECURITY.md` | Seguridad | ✔ este documento |
| `*/models.py`, `*/views.py`, `*/forms.py`, `*/urls.py`, `templates/**` | Backend / Frontend | ⏳ Fase 2 (los módulos aún son placeholders) |

Los hallazgos sobre código ajeno (backend/frontend) se **reportan acá con la
acción exacta**; el agente dueño debe aplicarlos. No se modificó código de
producción ajeno salvo el fix urgente de `base.py` detallado en SEC-04.

---

## 1. Resumen ejecutivo

El sistema hereda una base razonable (Django 5.2, middleware completo, validators
de contraseña, mixins de rol) pero tenía **huecos reales en producción** y
**riesgos de diseño** que se materializarán cuando backend/frontend implementen
los módulos. Acciones ya aplicadas en Fase 1:

- ✔ **Fix crítico**: el login se rompía con 500 tras autenticarse
  (`LOGIN_REDIRECT_URL = "dashboard"` no resuelve; ver SEC-04).
- ✔ **Fail-closed de secretos**: `prod.py` ahora aborta el arranque si
  `DJANGO_SECRET_KEY` es el placeholder de desarrollo (SEC-01).
- ✔ **Cookie CSRF HttpOnly** + `CSRF_FAILURE_VIEW` con registro de intentos.
- ✔ **Sesiones para terminal compartida**: expiran a las 8 h y al cerrar el
  navegador (SEC-06).
- ✔ **Headers explícitos**: nosniff, referrer policy, COOP, XFO (varios ya eran
  default de Django 5.2; ahora quedan fijados a la vista).
- ✔ **EMAIL/ADMINS + LOGGING** con rotación y logger de auditoría `audit`
  (estructura lista; el backend debe emitir los eventos).
- ✔ **Límite de payload** `DATA_UPLOAD_MAX_MEMORY_SIZE = 2 MB`.
- ✔ `manage.py check` y `manage.py check --deploy` pasan **sin issues**.

**Pendiente más crítico (lo implementa backend según las specs de este doc):**
1. Sanitización anti fórmulas en el export CSV de reportes (**SEC-02**).
2. Ticket numbering transaccional con lock (**SEC-03**).
3. Permisos a nivel de objeto / IDOR en ventas, caja, comandas (**SEC-07**).
4. Emitir eventos de auditoría financiera vía logger `audit` (**SEC-08**).

---

## 2. Modelo de amenazas (pub / terminal compartida)

### 2.1 Activos a proteger

| Activo | Riesgo si se compromete |
|---|---|
| **Dinero en caja** (`CashRegister`, `Sale`, `SaleItem`) | Robo directo: apertura/cierre fraudulento, ventas fantasma, anulaciones sin autorización, redondeos mal hechos |
| **Stock / inventario** (`Product`, `StockMovement`) | Robo de mercadería mediante ajustes/entradas/salidas falsos; merma encubierta |
| **Datos de clientes** (`Customer`: nombre, teléfono, email, DNI, fecha nacimiento) | Multas por **Ley 25.326 (AR)**; phishing; reputación. Es dato personal sensible |
| **Credenciales** (usuarios de staff + cuentas de administración propias de `accounts`) | Acceso total, alteración de precios/permisos, borrado de evidencia |
| **Terminal compartida del bar** (bartender/camarero) | Sesión ajena abierta, usuario logueado equivocado, caja manipulada por otro rol |
| **Export CSV de reportes** | Apertura en Excel/LibreOffice: **inyección de fórmulas** (ejecución de fórmulas/DDE del atacante) |
| **Registro/auditoría** | Sin logs no hay detección de fraude ni reconstrucción de hechos |

### 2.2 Actores

| Actor | Motivación | Capacidad |
|---|---|---|
| Bartender / camarero | Curiosidad, error, favoritismo (descuentos) | Terminal del bar, rol restringido |
| Cajero | Robo de caja, arqueo trucho | Caja, ventas, tickets |
| Gerente / admin | Legítimo (o abuso de privilegio si se compromete la cuenta) | Todo |
| Empleado descontento | Sabotaje (borrar ventas, vaciar stock) | Sus credenciales + terminal |
| Cliente en el bar | Distracción, ver pantallas, foto de tickets | Sin credenciales |
| Atacante externo | Fraude, ransomware, exfiltrar datos de clientes | Internet (si el sistema se publica sin restricción) |
| Malware en la terminal del bar | Keylogger, robo de sesión | Terminal compartida |

### 2.3 Vectores principales

1. **Robo de sesión en terminal compartida** (sesión que queda abierta).
2. **Fuerza bruta / spray de contraseñas** en `/login/` y en las pantallas
   propias de gestión de usuarios (`/usuarios/`).
3. **Abuso de rol**: un bartender accede a caja/reportes por falta de control de
   acceso a nivel de objeto (IDOR) o por URLs adivinables.
4. **Fraude financiero**: anular ventas, abrir caja dos veces, redondeos con
   `float`.
5. **Inyección de fórmulas** al exportar CSV (cadenas `=`, `+`, `-`, `@` en
   nombres de producto, notas, referencias).
6. **XSS** si se usa `|safe`/`mark_safe` sobre datos de clientes/productos.
7. **Supply chain**: Bootstrap por CDN sin `integrity` (SRI).
8. **Abuso de la administración propia**: gestión de usuarios (`/usuarios/`) sin
   2FA ni rate-limit; mass assignment al crear usuarios con grupos.

---

## 3. Endurecimiento ya aplicado (estado actual)

### 3.1 `config/settings/base.py`

| Ajuste | Valor | Línea | Nota |
|---|---|---|---|
| `SECRET_KEY` | desde env; fallback `django-insecure-dev-only-change-me` | base.py:33 | fallback **prohibido en prod** por assert (ver SEC-01) |
| `DEBUG` | default `False` | base.py:35 | |
| `ALLOWED_HOSTS` | default `localhost,127.0.0.1` | base.py:37 | |
| Middleware completo | Security, Session, Common, CSRF, Auth, Messages, XFrameOptions | base.py:64-72 | orden correcto; CSRF global |
| Validators de contraseña | min **8** + similitud + comunes + numéricas | base.py:123-128 | |
| `LOGIN_URL` | `"login"` → `/accounts/login/` | base.py:130 | funciona; ver SEC-20 (endpoint duplicado) |
| `LOGIN_REDIRECT_URL` | `"core:dashboard"` ✔ | base.py:131 | **corregido** (era `"dashboard"` → 500, SEC-04) |
| `LOGOUT_REDIRECT_URL` | `"core:login"` ✔ | base.py:132 | **corregido** (dedupe) |

### 3.2 `config/settings/prod.py` (endurecido en Fase 1)

| Ajuste | Valor | Línea |
|---|---|---|
| `assert not DEBUG` | fail-closed | prod.py:13 |
| `assert SECRET_KEY` no placeholder | fail-closed | prod.py:17-19 |
| `ALLOWED_HOSTS` vacío por defecto | fail-closed (400 si no se configura) | prod.py:22 |
| `SECURE_SSL_REDIRECT` | `True` | prod.py:27 |
| `SECURE_PROXY_SSL_HEADER` | `HTTP_X_FORWARDED_PROTO` | prod.py:31 |
| `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` | `True` | prod.py:34-35 |
| HSTS 1 año + subdominios + preload | `31536000` | prod.py:38-41 |
| `X_FRAME_OPTIONS` | `DENY` (clickjacking) | prod.py:47 |
| `SECURE_CONTENT_TYPE_NOSNIFF` | `True` (nosniff) | prod.py:48 |
| `SECURE_REFERRER_POLICY` | `same-origin` | prod.py:49 |
| `SECURE_CROSS_ORIGIN_OPENER_POLICY` | `same-origin` | prod.py:50 |
| `CSRF_TRUSTED_ORIGINS` | env, vacío = same-origin | prod.py:54 |
| `CSRF_COOKIE_HTTPONLY` | `True` (token vía input oculto, no JS) | prod.py:59 |
| `CSRF_COOKIE_SAMESITE` | `Lax` | prod.py:60 |
| `CSRF_FAILURE_VIEW` | `core.security_views.csrf_failure` (loguea + 403) | prod.py:61 |
| `SESSION_COOKIE_HTTPONLY` / `SAMESITE` | `True` / `Lax` | prod.py:67-68 |
| Sesión: `AGE` 8 h + expira al cerrar navegador + renueva con actividad | terminal compartida | prod.py:69-71 |
| `DATA_UPLOAD_MAX_MEMORY_SIZE` | 2 MB | prod.py:85 |
| EMAIL (smtp si `DJANGO_EMAIL_HOST`) + `ADMINS` | prod.py:90-105 |
| `LOGGING` rotativo + logger `audit` | prod.py:110-149 |

> Nota de verificación: en Django 5.2 `SECURE_CONTENT_TYPE_NOSNIFF`, 
> `SECURE_REFERRER_POLICY="same-origin"`, `X_FRAME_OPTIONS="DENY"`,
> `SESSION_COOKIE_HTTPONLY=True` y `CSRF_COOKIE_SAMESITE="Lax"` ya son default;
> se fijaron explícitos para que el endurecimiento sea visible y no dependa de
> cambios de default. No se agregó `SECURE_BROWSER_XSS_FILTER`: está **eliminado**
> en Django 5.

### 3.3 Núcleo y templates

- `core/mixins.py`: `RoleRequiredMixin` (grupos, **superuser pasa siempre**) +
  `StaffRequiredMixin` (`is_staff`) + decorador `role_required` — ok como base;
  ver SEC-13 y SEC-17.
- **Admin de Django DESHABILITADO** (decisión del dueño del pub): fuera de
  `INSTALLED_APPS` (base.py:42-63) y sin ruta `/admin/` (config/urls.py:4-6,
  12-27); toda la administración se hace con pantallas propias. `accounts/admin.py`
  quedó como código inerte (cleanup opcional del backend).
- `templates/base.html:25`: logout por **POST con `{% csrf_token %}`** ✔ (Django 5 rechaza GET).
- Sin `|safe` ni `mark_safe` ni SQL crudo en templates/config/core (grep verificado).
- `.env` en `.gitignore` ✔ (verificado: `.env` existe localmente, no está trackeado).

---

## 4. Hallazgos por severidad

Referencias `archivo:línea` al estado actual. Los hallazgos de código a
implementar (backend/frontend) citan el contrato y el lugar esperado.

### CRÍTICA

| ID | Hallazgo | Referencia | Estado |
|---|---|---|---|
| **SEC-01** | `SECRET_KEY` con fallback **conocido** (`django-insecure-dev-only-change-me`) si se despliega sin env → compromiso total (firma de cookies/sesiones, CSRF, datos) | base.py:33 | ✔ Mitigado: assert en prod.py:17-19. **Acción deploy**: generar clave real; si el fallback se usó alguna vez, **rotar** la clave |
| **SEC-02** | **Inyección de fórmulas en export CSV** de reportes: celdas que empiezan con `=`, `+`, `-`, `@` (nombres de producto, notas, referencias, clientes) se ejecutan como fórmula/DDE en Excel/LibreOffice | reports (a implementar) | 🔴 Pendiente backend — spec exacta en §6.1 |
| **SEC-03** | **Race condition en ticket numbering** `YYYYMMDD-####` único/secuencial: dos ventas concurrentes calculan el mismo número → ticket duplicado o `IntegrityError` | sales (a implementar) | 🔴 Pendiente backend — spec exacta en §6.2 |
| **SEC-04** | **Login roto (500 tras autenticarse)**: `LOGIN_REDIRECT_URL = "dashboard"` no resuelve (la URL vive como `core:dashboard`) → `NoReverseMatch` en cada login exitoso (DoS de autenticación) | base.py (antiguo :131) | ✔ **Corregido en Fase 1** (base.py:131-132). Era fix urgente en settings |

### ALTA

| ID | Hallazgo | Referencia | Estado |
|---|---|---|---|
| **SEC-05** | **Sin protección contra fuerza bruta** en login y en las pantallas propias de gestión de usuarios (sin django-axes ni rate-limit nginx) | core/urls.py:15-19, accounts/urls.py (`/usuarios/`) | 🔴 Pendiente deploy — pasos en §6.7 (NO instalar aún: bloqueado) |
| **SEC-06** | Sesión por defecto de **2 semanas** (`SESSION_COOKIE_AGE=1209600`) en **terminal compartida**: sesión ajena reutilizable | (default Django) | ✔ Mitigado: prod.py:69-71 (8 h + cierre de navegador) |
| **SEC-07** | **IDOR / permisos a nivel de objeto**: sin implementar aún; riesgo de que bartender acceda a caja/reportes o anule ventas ajenas por URL | views de sales/tables/reports (a implementar) | 🔴 Pendiente backend — patrón en §6.3 |
| **SEC-08** | **Sin logging de eventos financieros** (apertura/cierre de caja, anulación de ventas, cambios de rol): imposible detectar fraude | — | 🟡 Base lista (logger `audit`, prod.py:133-146); backend debe emitir eventos — spec §6.5 |
| **SEC-09** | **Bootstrap por CDN sin SRI**: `{% bootstrap_css %}`/`{% bootstrap_javascript %}` sin `integrity`; compromiso del CDN = XSS global | templates/base.html:9-10, base.py:156-158 | 🔴 Pendiente frontend — §6.6 |
| **SEC-10** | **Caja "una abierta por vez" sin lock**: dos aperturas concurrentes (dos terminales) → doble caja abierta, arqueos cruzados | sales `CashRegister` (a implementar) | 🔴 Pendiente backend — §6.4 |
| **SEC-11** | **Dinero**: el contrato exige `DecimalField`, pero hay que garantizar **redondeo `ROUND_HALF_UP`** y evitar `float` en divisiones de totales (drift de centavos) | CONTRACT (moneda) | 🔴 Pendiente backend — §6.8 |

> **ELIMINADO por decisión de arquitectura (dueño del pub):** el hallazgo de
> protección del módulo admin de Django (`/admin/`: renombrar + allowlist IP +
> 2FA) **queda sin objeto**. El admin está **deshabilitado**: no está en
> `INSTALLED_APPS` (base.py:42-63) y no existe la ruta `/admin/`
> (config/urls.py:4-6). La superficie de administración ahora son las
> **pantallas propias** (accounts, `/usuarios/`) → prioridad 1 de revisión en
> Fase 2 (§7). `accounts/admin.py` quedó inerte (cleanup opcional del backend).

### MEDIA

| ID | Hallazgo | Referencia | Estado |
|---|---|---|---|
| **SEC-12** | `CSRF_COOKIE_HTTPONLY=False` (default) | (default Django) | ✔ Corregido: prod.py:59 |
| **SEC-13** | Fallo CSRF sin registro (default `django.views.csrf.csrf_failure`) | (default Django) | ✔ Corregido: prod.py:61 + `core/security_views.py` |
| **SEC-14** | Headers nosniff/referrer/COOP dependían del default | (default Django) | ✔ Fijados explícitos: prod.py:48-50 |
| **SEC-15** | EMAIL sin configurar → backend **console** en prod (password reset/alertas se pierden silenciosamente) | prod.py:100-105 | 🟡 Comportamiento documentado; **acción deploy**: setear `DJANGO_EMAIL_*` |
| **SEC-16** | Sin `CACHES` configurado: si se instala django-axes usará `locmem` (inútil con varios workers) | base.py | 🟡 Documentar en deploy |
| **SEC-17** | Mixins/decorador de rol **redirigen** al dashboard en vez de devolver **403**; para endpoints CSV/JSON la redirección enmascara el abuso | core/mixins.py:22-31, 50-61 | 🟡 Pendiente backend: usar `PermissionDenied` en vistas no interactivas |
| **SEC-18** | `global_context` **traga excepciones** (`except Exception`) — enmascara fallas de DB/stock y dificulta detectar problemas | core/context_processors.py:21,31 | 🟡 Pendiente: loguear `logger.exception` en vez de callar |
| **SEC-19** | `DATA_UPLOAD_MAX_MEMORY_SIZE` default 2.5 MB | (default) | ✔ Fijado 2 MB: prod.py:85; `DATA_UPLOAD_MAX_NUMBER_FIELDS=1000` (default) ok para POS |
| **SEC-20** | Dos endpoints de login (`/login/` y `/accounts/login/`) por `include("django.contrib.auth.urls")` + definición propia en core; mismo template pero superficie duplicada | config/urls.py:14, core/urls.py:15-19 | 🟡 Baja prioridad: dejar uno solo |

### BAJA

| ID | Hallazgo | Referencia | Estado |
|---|---|---|---|
| **SEC-21** | HSTS `preload` requiere registro externo; 1 año sin rampa (aceptable para sitio chico) | prod.py:38-41 | ✔ ok; documentar |
| **SEC-22** | Permisos del `.env` en servidor (por defecto legible) | — | 🟡 Acción deploy: `chmod 600 .env` o secret manager |
| **SEC-23** | `manage.py check --deploy` no integrado en CI | — | 🟡 Recomendación |

---

## 5. Puntos obligatorios (análisis requerido)

### 5.1 Manejo de secretos
- `SECRET_KEY`, `DB_PASSWORD`, credenciales SMTP viven en `.env` (gitignored ✔).
- Fallback de `SECRET_KEY` en base.py:33 **prohibido en prod** por assert (SEC-01).
- Recomendaciones: rotar `SECRET_KEY` si el fallback se usó alguna vez; `chmod 600 .env`; en deploys serios usar secret manager (env real, no archivo); **nunca** loguear `SECRET_KEY`/`DB_PASSWORD`/tokens; no hacer commit de `.env` (verificado: no trackeado).

### 5.2 DEBUG y ALLOWED_HOSTS en prod
- `DEBUG=False` forzado por assert (prod.py:13). `ALLOWED_HOSTS` **vacío por defecto** (prod.py:22): sin configurar, Django responde 400 a todo — fail-closed correcto.
- Riesgo operativo: olvidar `DJANGO_ALLOWED_HOSTS` en el deploy → sistema caído. Documentar en runbook.

### 5.3 Cookies
| Cookie | HttpOnly | Secure | SameSite |
|---|---|---|---|
| `sessionid` | ✔ True (prod.py:67) | ✔ (prod.py:34) | ✔ Lax (prod.py:68) |
| `csrftoken` | ✔ True (prod.py:59) | ✔ (prod.py:35) | ✔ Lax (prod.py:60) |

### 5.4 CSRF
- Middleware global (base.py:70); **logout por POST con token** ✔ (base.html:25).
- Cookie Secure + HttpOnly + SameSite; `CSRF_TRUSTED_ORIGINS` por env (solo necesario si frontend y backend están en dominios distintos).
- Fallo CSRF logueado (SEC-13).
- **Regla para el POS (frontend)**: el JS debe tomar el token del input oculto `{% csrf_token %}` (o `<meta name="csrf-token">`), **nunca** de la cookie (ahora es HttpOnly).

### 5.5 Clickjacking / nosniff / referrer
- `X-Frame-Options: DENY` ✔; `X-Content-Type-Options: nosniff` ✔; `Referrer-Policy: same-origin` ✔; `Cross-Origin-Opener-Policy: same-origin` ✔ (prod.py:47-50).

### 5.6 Fuerza bruta en login
- **NO se instala django-axes** (bloqueado). Recomendación documentada: ver §6.7 (pasos para cuando se habilite) y alternativa nginx `limit_req` **sin código**.

### 5.7 Política de contraseñas
- Ya en base.py:123-128: mínimo **8**, similaridad con usuario, comunes y numéricas prohibidas. Recomendable subir a 10-12 para admin/gerente (decisión de producto) y exigir rotación para cuentas de caja.

### 5.8 Export CSV: inyección de fórmulas
- Ver spec exacta §6.1. **Todos** los reportes (`*_csv` del contrato) deben pasar las celdas por el sanitizador.

### 5.9 IDOR / permisos a nivel de objeto
- Ver patrón §6.3. Reglas por rol: caja solo `cajero/gerente/admin`; anular venta solo quien la hizo o `gerente/admin`; reportes solo `gerente/admin`; comandas del bartender/camarero según contrato.

### 5.10 Dinero
- `DecimalField(max_digits=10, decimal_places=2)` en todo (contrato ✔). Redondeo `ROUND_HALF_UP` y división de totales: ver §6.8. Prohibido `float` para dinero.

### 5.11 Ticket numbering
- Ver spec §6.2 (transacción + `select_for_update`).

### 5.12 SQLi / XSS
- **SQLi**: Django ORM parametriza; **prohibir** `Model.objects.raw()`, `QuerySet.extra()`, `connection.cursor()` con interpolación de strings. Si alguna vez se necesitan, usar siempre parámetros `%s`/`%(name)s`.
- **XSS**: autoescape de templates activo por defecto. Regla: **ningún** `|safe`, `mark_safe`, `autoescape off` sobre datos de clientes/productos/notas. Revisar el POS (JS que inyecta HTML del carrito) con `textContent` o escape manual, nunca `innerHTML` con datos del server. (Grep Fase 1: no hay `|safe` actualmente.)

### 5.13 Logging de eventos financieros
- Estructura lista en prod.py:133-146 (logger `audit` → `logs/audit.log`, rotación 5 MB × 5). Ver spec §6.5 para qué eventos emitir y con qué campos. No loguear passwords, tokens ni datos de tarjetas.

### 5.14 Administración (pantallas propias; admin de Django deshabilitado)
- El admin de Django está **deshabilitado por decisión del dueño** (base.py:42-63,
  config/urls.py:4-6): no existe `/admin/`. Toda la administración (usuarios,
  CRUDs, reportes) son pantallas propias → la superficie de administración es
  **accounts** (`/usuarios/`), con `core/mixins.py` como control de acceso
  (superuser pasa siempre).
- Requisitos para esa superficie (revisar en Fase 2): solo `admin`/`gerente`
  acceden a gestión de usuarios; **2FA** recomendado para `admin`/`gerente`
  (django-otp / django-two-factor-auth, cuando se habilite); rate-limit en login
  y cambio de contraseña (§6.7); cambios de rol/estado registrados en `audit`
  (§6.5); **mass assignment** prohibido al crear usuarios con grupos (§6.9).

---

## 6. Recomendaciones accionables (specs para otros agentes)

### 6.1 SEC-02 — Sanitizador CSV (BACKEND: reports)

Crear `reports/utils.py`:

```python
import csv
import re

# Celdas que Excel/LibreOffice interpretan como fórmula o DDE.
_DANGEROUS = re.compile(r"^[=+\-@\t\r]")

def safe_cell(value):
    """Neutraliza celdas que empiezan con = + - @ (tab/CR) antefijando ' (apóstrofe)."""
    if value is None:
        return ""
    text = str(value)
    if _DANGEROUS.match(text):
        return "'" + text
    return text

def write_safe_csv(response, headers, rows):
    writer = csv.writer(response, delimiter=";")  # ; para Excel es-AR
    writer.writerow(headers)
    for row in rows:
        writer.writerow([safe_cell(c) for c in row])
```

- **No** sanitizar columnas numéricas reales (montos/cantidades): se escriben como
  `Decimal`/`int` y `str()` de un `Decimal` nunca arranca con `=+-@` (un negativo
  `-5` como *texto* sí, pero en columnas numéricas va como número).
- Aplicar a **todos** los `*_csv` (ventas, productos, ganancia, inventario).
- Es opcional pero recomendado: reemplazar saltos de línea dentro de celdas
  (`\n`→espacio) para evitar celdas multilínea.

### 6.2 SEC-03 — Ticket numbering transaccional (BACKEND: sales)

```python
from django.db import transaction

@transaction.atomic
def next_ticket_number(date):
    # Contador por día: tabla TicketCounter(date=DateField(unique=True), last_number=Int)
    counter, _ = TicketCounter.objects.select_for_update().get_or_create(date=date)
    counter.last_number += 1
    counter.save(update_fields=["last_number"])
    return f"{date:%Y%m%d}-{counter.last_number:04d}"
```

- `select_for_update()` serializa los contadores entre transacciones concurrentes
  (PostgreSQL; en SQLite el lock de escritura ya serializa).
- Llamar **dentro** de la misma transacción que crea la `Sale` y descuenta stock;
  si la venta falla, el número no se consume (o se acepta un hueco, decisión de
  negocio: no reutilizar números anulados).
- El `unique=True` de `ticket_number` queda como red de seguridad.

### 6.3 SEC-07 — Control de acceso a nivel de objeto (BACKEND: todas las apps)

Patrón obligatorio para cada vista que reciba `pk`/`slug`:

```python
class SaleVoidView(RoleRequiredMixin, View):
    roles = ["cajero", "gerente", "admin"]

    def post(self, request, pk):
        sale = get_object_or_404(Sale, pk=pk)
        # Regla de negocio: solo el autor, o gerente/admin (ver CONTRACT).
        if sale.user != request.user and not (
            request.user.groups.filter(name__in=["gerente", "admin"]).exists()
        ):
            raise PermissionDenied("No podés anular una venta de otro usuario.")
        ...
```

Reglas mínimas:
- **Caja** (abrir/cerrar/arqueo): solo `cajero`, `gerente`, `admin`.
- **Anulación de venta**: autor o `gerente/admin`; exige `void_reason`; registra en `audit` (SEC-08).
- **Reportes + export CSV**: solo `gerente/admin`.
- **Comandas/mesas**: bartender/camarero según contrato; nunca modificar comanda de otro si el rol no lo permite.
- **Clientes**: `customer_detail` solo para roles con ventas/clientes; no exponer DNI/teléfono en listados a roles sin necesidad.

### 6.4 SEC-10 — Caja única abierta (BACKEND: sales)

```python
from django.db import transaction

@transaction.atomic
def open_cash_register(user, opening_amount):
    # Previene doble apertura concurrente desde dos terminales.
    if CashRegister.objects.select_for_update().filter(status="abierta").exists():
        raise ValidationError("Ya hay una caja abierta.")
    CashRegister.objects.create(opened_by=user, opening_amount=opening_amount, status="abierta")
```

### 6.5 SEC-08 — Eventos de auditoría (BACKEND)

Usar el logger `audit` ya configurado (prod.py:133-146). Eventos mínimos:

```python
import logging
audit = logging.getLogger("audit")

audit.info("caja_abierta user=%s monto=%s", user.username, opening_amount)
audit.info("caja_cerrada user=%s esperado=%s real=%s diff=%s", ...)
audit.warning("venta_anulada user=%s sale=%s motivo=%s", ...)
audit.info("rol_cambiado por=%s a_usuario=%s grupo=%s", ...)
```

Formato: `evento clave=valor ...` (grep-friendly). **Prohibido** loguear passwords,
tokens, datos de tarjetas o DNI completos.

### 6.6 SEC-09 — Bootstrap con SRI (FRONTEND)

En `templates/base.html` reemplazar `{% bootstrap_css %}`/`{% bootstrap_javascript %}`
por `<link>`/`<script>` propios con `integrity` + `crossorigin="anonymous"` (generar
hash con `openssl dgst -sha384`), o **self-hostear** los assets en `static/` (mejor:
sin dependencia de terceros en producción). Coordinar con el ajuste de
`BOOTSTRAP5` en base.py:156-158.

### 6.7 SEC-05 — Fuerza bruta (DEPLOY; NO instalar ahora)

Pasos cuando se habilite (documentados, no ejecutados):

1. `pip install django-axes` → agregar a `requirements-prod.txt`.
2. `INSTALLED_APPS` += `"axes"`; `MIDDLEWARE` += `"axes.middleware.AxesMiddleware"` (después de `AuthenticationMiddleware`).
3. Configurar `AXES_FAILURE_LIMIT=5`, `AXES_COOLOFF_TIME=1` (hora),
   `AXES_LOCKOUT_TEMPLATE`, `AXES_RESET_ON_SUCCESS=True`.
4. `python manage.py migrate` (crea tablas).
5. **Requisito**: configurar `CACHES` (Redis/Memcached) en prod — con `locmem` no
   sirve multiworker (SEC-16).
6. Alternativa **sin dependencias**: en nginx,
   `limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;` aplicado a
   `/login/` y las rutas de gestión de usuarios.

### 6.8 SEC-11 — Dinero y redondeo (BACKEND)

```python
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")

def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)

# Ítems: unit_price * quantity siempre como Decimal, cuantizar al final.
# División de un total en N partes (ej. dividir una cuenta):
parts = [money(total / Decimal(n)) for _ in range(n)]
# corregir drift: la última parte absorbe la diferencia
parts[-1] += total - sum(parts)
```

- Nunca `float` para dinero; validar en forms con `DecimalField`; el descuento
  del canje de puntos también `money()`.

### 6.9 Administración con pantallas propias (accounts) — recomendaciones

El admin de Django está deshabilitado; la gestión de usuarios se hace en
`accounts` (`/usuarios/`). Recomendaciones para backend/frontend:

- **Acceso**: solo `admin`/`gerente` (mixin/decorador de rol); `user_toggle_active`
  y el cambio de grupos con confirmación y registro en `audit` (SEC-08).
- **Mass assignment**: al crear/editar usuario usar `ModelForm` con campos
  whitelist explícitos; asignar grupos por checkbox controlado, nunca aceptar
  `request.POST` completo (ver §6.10, punto de Fase 2).
- **Cambio de contraseña**: vía formulario con validators (base.py:123-128);
  sin rate-limit propio hasta habilitar django-axes (SEC-05/§6.7).
- **2FA** (cuando se habilite): django-otp / django-two-factor-auth para cuentas
  `admin`/`gerente`.
- Cleanup backend: `accounts/admin.py` quedó inerte con el admin deshabilitado;
  puede eliminarse (nunca se autodetecta sin `django.contrib.admin`).

### 6.10 Otras recomendaciones de deploy

- `manage.py check --deploy` en CI (SEC-23) y en el runbook de release.
- nginx debe **sobrescribir** `X-Forwarded-Proto` (`proxy_set_header X-Forwarded-Proto $scheme;`) — ver comentario prod.py:28-31.
- Backups cifrados de la DB (contienen datos personales de clientes — Ley 25.326).
- `SECURE_HSTS_PRELOAD`: registrar el dominio en https://hstspreload.org cuando se decida.

---

## 7. Fase 2 (pendiente, tras backend + frontend)

Revisión OWASP completa de `*/models.py`, `*/views.py`, `*/forms.py`,
`*/urls.py`, `templates/**`, `static/**`.

**Prioridad 1 — `accounts` (superficie de administración; sustituye al admin de
Django — ver §5.14/§6.9):**

- **Mass assignment** al crear/editar usuarios: whitelist de campos en el
  `ModelForm`; asignación de grupos controlada, nunca `request.POST` completo.
- **Escalada de privilegios**: cambiar el grupo/estado de un usuario no debe
  poder manipularse por POST (validar contra `request.user.groups`); nadie puede
  auto-desactivarse ni cambiarse su propio grupo sin quedar registrado.
- **IDOR/permisos** en `user_list`, `user_update`, `user_toggle_active`: solo
  `admin`/`gerente` (y superuser); sin acceso a otros usuarios por URL.
- **Fuerza bruta** sobre login y cambio de contraseña (SEC-05/§6.7).
- **Auditoría**: cambios de rol/estado/contraseña registrados en `audit` (SEC-08).

**Prioridad 2 — resto del sistema:**

1. **SQLi**: grep `raw(`, `extra(`, `cursor(`, `objects.using(`, `__contains` con input crudo.
2. **XSS**: grep `|safe`, `mark_safe`, `autoescape`, `innerHTML` en el POS; validar escape del carrito.
3. **CSRF**: verificar token en **todo** POST (anulación de venta, cerrar comanda, canje de puntos, logout).
4. **Mass assignment**: solo `ModelForm`/campos whitelist; nunca `Model.objects.create(**request.POST)`.
5. **IDOR**: revisar cada vista por `pk` con `get_object_or_404` + chequeo de rol/dueño (SEC-07).
6. **Secretos en logs**: grep `password`, `token`, `SECRET_KEY` en código y en la config de logging.
7. **Validación de entrada**: fechas, cantidades negativas, `quantity=0`, `discount>total`, stock negativo.
8. **Redirección abierta**: `next` param de login (Django lo valida ✔; verificar usos propios de `redirect(request.GET.get("next"))`).
9. **Uploads**: si se agregan imágenes, validar tipo/tamaño y servir media con `X-Content-Type-Options` (nunca desde Django en prod, sino nginx con `add_header`).
10. Actualizar este documento con hallazgos reales de la implementación (IDs SEC-2x) y ajustar severidades.

Criterio de severidad: OWASP (Impacto × Probabilidad) ajustado al contexto de pub
(terminal compartida, dinero físico en caja, datos personales de clientes AR).

---

*Documento mantenido por el agente de Seguridad. Los IDs SEC-xx se referencian en
el código (`prod.py`, `base.py`, `core/security_views.py`) para trazabilidad.*
