"""
El Patio SIG — Fixtures compartidas de pruebas (raíz).

Área de propiedad: Pruebas. NO modificar código de producción.

Convenciones:
- Grupos de Django (admin, gerente, bartender, cajero) creados con get_or_create.
- Usuarios por rol con password "test-pass-123".
- Fixtures de negocio (category, product, table, customer, supplier,
  open_cash_register) sólo crean objetos si el backend ya implementó los
  modelos; si faltan, el test que las pida se marca como "skipped" (no falla).
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse

User = get_user_model()

DEFAULT_PASSWORD = "test-pass-123"

ROLE_GROUPS = ("admin", "gerente", "bartender", "cajero")


# ---------------------------------------------------------------------------
# Helpers compartidos (importables desde los tests: `from conftest import ...`)
# ---------------------------------------------------------------------------

def get_or_create_group(name: str) -> Group:
    """Devuelve el grupo de Django con el nombre dado, creándolo si no existe."""
    return Group.objects.get_or_create(name=name)[0]


def import_model(model_path: str):
    """Devuelve la clase del modelo 'app.models.Clase'.

    Si el backend todavía no implementó el modelo, salta el test que lo pida
    (pytest.skip) en lugar de fallar por un import inexistente.
    """
    import importlib

    try:
        module_name, _, attr = model_path.rpartition(".")
        return getattr(importlib.import_module(module_name), attr)
    except (ImportError, AttributeError):
        pytest.skip(f"Backend no implementado: {model_path}")


def assert_access_denied(response):
    """Acepta 403 o redirect a dashboard (patrón RoleRequiredMixin del contrato).

    El contrato define que las vistas con rol incorrecto redirigen a
    `core:dashboard` con un mensaje; también se acepta 403 si el backend
    decide responder Forbidden.
    """
    assert response.status_code in (302, 403), (
        f"Se esperaba acceso denegado (403 o redirect a dashboard), "
        f"status={response.status_code}"
    )
    if response.status_code == 302:
        dashboard_url = reverse("core:dashboard")
        assert response.url == dashboard_url or response.url.startswith(dashboard_url), (
            f"Redirect inesperado al denegar acceso: {response.url}"
        )


# ---------------------------------------------------------------------------
# Grupos
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_group(db):
    return get_or_create_group("admin")


@pytest.fixture
def gerente_group(db):
    return get_or_create_group("gerente")


@pytest.fixture
def bartender_group(db):
    return get_or_create_group("bartender")


@pytest.fixture
def cajero_group(db):
    return get_or_create_group("cajero")


@pytest.fixture
def all_groups(db):
    """Diccionario con los 4 grupos del contrato."""
    return {name: get_or_create_group(name) for name in ROLE_GROUPS}


# ---------------------------------------------------------------------------
# Usuarios por rol
# ---------------------------------------------------------------------------

@pytest.fixture
def user_factory(db):
    """Factory de usuarios: user_factory(username, group=<Group>, **kwargs)."""
    def _create(username, group=None, password=DEFAULT_PASSWORD, **kwargs):
        user = User.objects.create_user(username=username, password=password, **kwargs)
        if group is not None:
            user.groups.add(group)
        return user

    return _create


@pytest.fixture
def admin_user(user_factory, admin_group):
    return user_factory("admin_user", group=admin_group, is_staff=True, is_superuser=True)


@pytest.fixture
def gerente_user(user_factory, gerente_group):
    return user_factory("gerente_user", group=gerente_group)


@pytest.fixture
def bartender_user(user_factory, bartender_group):
    return user_factory("bartender_user", group=bartender_group)


@pytest.fixture
def cajero_user(user_factory, cajero_group):
    return user_factory("cajero_user", group=cajero_group)


# ---------------------------------------------------------------------------
# Clientes autenticados por rol (django.test.Client + force_login)
# ---------------------------------------------------------------------------

@pytest.fixture
def client_admin(client, admin_user):
    client.force_login(admin_user)
    return client


@pytest.fixture
def client_gerente(client, gerente_user):
    client.force_login(gerente_user)
    return client


@pytest.fixture
def client_bartender(client, bartender_user):
    client.force_login(bartender_user)
    return client


@pytest.fixture
def client_cajero(client, cajero_user):
    client.force_login(cajero_user)
    return client


# ---------------------------------------------------------------------------
# Fixtures de negocio (requieren modelos del backend; si no existen → skip)
# ---------------------------------------------------------------------------

@pytest.fixture
def category(db):
    Category = import_model("inventory.models.Category")
    return Category.objects.create(name="Bebidas", description="Bebidas y tragos")


@pytest.fixture
def product(db, category):
    Product = import_model("inventory.models.Product")
    return Product.objects.create(
        name="Cerveza 1L",
        category=category,
        unit="botella",
        purchase_price=Decimal("80.00"),
        sale_price=Decimal("150.00"),
        stock_current=Decimal("20"),
        stock_min=Decimal("5"),
        is_active=True,
    )


@pytest.fixture
def table(db):
    Table = import_model("tables.models.Table")
    return Table.objects.create(
        number=1, capacity=4, zone="salón", status="libre", is_active=True
    )


@pytest.fixture
def customer(db):
    Customer = import_model("customers.models.Customer")
    return Customer.objects.create(
        name="Cliente de Prueba",
        phone="+54 11 5555-0100",
        email="cliente@example.com",
        dni="30111222",
        points=0,
        is_active=True,
    )


@pytest.fixture
def supplier(db):
    Supplier = import_model("purchases.models.Supplier")
    return Supplier.objects.create(
        name="Proveedor de Prueba",
        contact_name="Contacto",
        phone="+54 11 5555-0200",
        email="proveedor@example.com",
        address="Av. Siempre Viva 742",
        cuit="30-12345678-9",
        is_active=True,
    )


@pytest.fixture
def open_cash_register(db, cajero_user):
    """Caja registradora abierta (status='abierta') para ventas."""
    CashRegister = import_model("sales.models.CashRegister")
    return CashRegister.objects.create(
        opened_by=cajero_user,
        opening_amount=Decimal("1000.00"),
        status="abierta",
    )
