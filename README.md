# El Patio SIG — Sistema de Gestión para Pub

Sistema integral de gestión para el pub **El Patio**: ventas (POS), inventario,
mesas y comandas, empleados y turnos, clientes y fidelización, compras y
proveedores, reservas y reportes.

## Stack

| Capa | Tecnología |
|------|------------|
| Backend | Django 5.2 LTS (Python 3.14) |
| Frontend | Bootstrap 5.3 + templates Django |
| Base de datos | SQLite (desarrollo) / PostgreSQL (producción) |
| Tests | pytest + pytest-django |

## Estructura

```
config/            # Settings del proyecto (base / dev / prod)
core/              # Dashboard, utilidades, mixins
accounts/          # Autenticación, perfiles y roles (Grupos)
inventory/         # Productos, categorías, stock
sales/             # Ventas POS, tickets, caja
tables/            # Mesas y comandas
staff/             # Empleados y turnos
customers/         # Clientes y fidelización
purchases/         # Proveedores y órdenes de compra
reservations/      # Reservas de mesas
reports/           # Reportes y estadísticas
```

## Puesta en marcha (desarrollo)

```bash
# 1. Entorno virtual e instalación
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # Linux/macOS
pip install -r requirements.txt

# 2. Configuración
copy .env.example .env            # Windows
# cp .env.example .env            # Linux/macOS
# Editar .env según corresponda

# 3. Base de datos y usuarios
# El módulo admin de Django está deshabilitado: los usuarios se gestionan con
# las pantallas propias (sección "Usuarios", rol admin). Alternativa rápida:
python manage.py migrate
python manage.py createsuperuser   # opcional: acceso total (sin módulo admin)
python manage.py seed_demo        # opcional: datos de demostración

# 4. Servidor
python manage.py runserver
```

Abrir http://127.0.0.1:8000

## Producción

- Cambiar `DB_ENGINE=postgres` en `.env` y completar credenciales de PostgreSQL.
- `DJANGO_DEBUG=False`, generar `DJANGO_SECRET_KEY` segura, configurar
  `DJANGO_ALLOWED_HOSTS`.
- Instalar `requirements-prod.txt` (psycopg, gunicorn).
- Ver `config/settings/prod.py` (HSTS, cookies seguras, SSL redirect, etc.).
- Correr `collectstatic` y servir con gunicorn + nginx.

## Roles de usuario

- **Administrador**: acceso total (usuarios, configuración, reportes).
- **Gerente**: reportes, inventario, compras.
- **Bartender/Camarero**: mesas, comandas, pedidos.
- **Cajero**: caja, cobros, tickets.

## Tests

```bash
pytest
```
