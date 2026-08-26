"""
seed_demo — Carga datos de demostración (idempotente).

Uso: python manage.py seed_demo

Crea los 4 grupos (admin, gerente, bartender, cajero), usuarios demo con
contraseña "demo12345", categorías, productos (precios en UYU), mesas,
1 proveedor, 1 cliente y las configuraciones de fidelización y happy hour.
"""
from datetime import time
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand

from customers.models import Customer, LoyaltyConfig
from inventory.models import Category, Product
from purchases.models import Supplier
from sales.models import HappyHourConfig, SaleConfig
from tables.models import Table

GROUPS = ["admin", "gerente", "bartender", "cajero"]

DEMO_USERS = [
    {"username": "admin", "group": "admin", "is_staff": True, "is_superuser": True},
    {"username": "gerente", "group": "gerente"},
    {"username": "bartender", "group": "bartender"},
    {"username": "cajero", "group": "cajero"},
]
DEMO_PASSWORD = "demo12345"

CATEGORIES = [
    {"name": "Cervezas", "description": "Cervezas tiradas y en botella"},
    {"name": "Vinos", "description": "Vinos por copa y por botella"},
    {"name": "Espirituosas", "description": "Destilados y aperitivos"},
    {"name": "Gaseosas", "description": "Gaseosas y aguas saborizadas"},
    {"name": "Aguas", "description": "Agua mineral y soda"},
    {"name": "Snacks", "description": "Snacks y picadas"},
]

# (nombre, categoría, unidad, precio compra UYU, precio venta UYU, stock, stock mínimo)
PRODUCTS = [
    ("Cerveza rubia tirada", "Cervezas", "jarra", "90.00", "180.00", "50", "10"),
    ("Cerveza negra tirada", "Cervezas", "jarra", "100.00", "200.00", "40", "10"),
    ("Porrón de cerveza", "Cervezas", "botella", "60.00", "120.00", "120", "24"),
    ("Copa de vino tinto", "Vinos", "porción", "55.00", "110.00", "30", "10"),
    ("Fernet", "Espirituosas", "botella", "650.00", "1300.00", "20", "5"),
    ("Gin", "Espirituosas", "botella", "750.00", "1500.00", "15", "5"),
    ("Gaseosa cola 500ml", "Gaseosas", "unidad", "40.00", "80.00", "200", "24"),
    ("Gaseosa lima 500ml", "Gaseosas", "unidad", "40.00", "80.00", "200", "24"),
    ("Agua mineral 500ml", "Aguas", "unidad", "25.00", "60.00", "200", "24"),
    ("Hamburguesa", "Snacks", "unidad", "175.00", "350.00", "60", "15"),
    ("Papas fritas", "Snacks", "unidad", "60.00", "120.00", "100", "20"),
    ("Maní salado", "Snacks", "unidad", "40.00", "90.00", "100", "20"),
]

# (número, capacidad, zona)
TABLES = (
    [(number, 2, Table.Zone.BARRA) for number in range(1, 5)]
    + [(number, 4, Table.Zone.SALON) for number in range(5, 13)]
    + [(number, 6, Table.Zone.TERRAZA) for number in range(13, 17)]
)


class Command(BaseCommand):
    help = "Carga datos de demostración (idempotente) para El Patio SIG."

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("Creando grupos..."))
        groups = {}
        for name in GROUPS:
            groups[name], _ = Group.objects.get_or_create(name=name)
            self.stdout.write(f"  - grupo {name}")

        self.stdout.write(self.style.MIGRATE_HEADING("Creando usuarios demo..."))
        for data in DEMO_USERS:
            user, created = User.objects.get_or_create(
                username=data["username"],
                defaults={
                    "is_staff": data.get("is_staff", False),
                    "is_superuser": data.get("is_superuser", False),
                },
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save()
            user.groups.add(groups[data["group"]])
            self.stdout.write(f"  - {user.username} (grupo: {data['group']}, password: {DEMO_PASSWORD})")

        self.stdout.write(self.style.MIGRATE_HEADING("Creando categorías..."))
        categories = {}
        for item in CATEGORIES:
            category, _ = Category.objects.get_or_create(
                name=item["name"], defaults={"description": item["description"]}
            )
            categories[item["name"]] = category
            self.stdout.write(f"  - {category.name}")

        self.stdout.write(self.style.MIGRATE_HEADING("Creando productos..."))
        for name, cat, unit, purchase, sale, stock, stock_min in PRODUCTS:
            product, _ = Product.objects.get_or_create(
                name=name,
                defaults={
                    "category": categories[cat],
                    "unit": unit,
                    "purchase_price": Decimal(purchase),
                    "sale_price": Decimal(sale),
                    "stock_current": Decimal(stock),
                    "stock_min": Decimal(stock_min),
                },
            )
            self.stdout.write(f"  - {product.name} ({product.sale_price} UYU)")

        self.stdout.write(self.style.MIGRATE_HEADING("Creando mesas..."))
        for number, capacity, zone in TABLES:
            table, _ = Table.objects.get_or_create(
                number=number, defaults={"capacity": capacity, "zone": zone}
            )
            self.stdout.write(f"  - Mesa {table.number} ({table.get_zone_display()})")

        self.stdout.write(self.style.MIGRATE_HEADING("Creando proveedor..."))
        supplier, _ = Supplier.objects.get_or_create(
            name="Distribuidora El Patio SRL",
            defaults={
                "contact_name": "Marcos Pérez",
                "phone": "2900 555 1234",
                "email": "ventas@elpatiodistribuidora.com.uy",
                "address": "Av. del Libertador 1234, Montevideo",
                "cuit": "21-12345678-9",
                "notes": "Proveedor principal de bebidas y snacks",
            },
        )
        self.stdout.write(f"  - {supplier.name}")

        self.stdout.write(self.style.MIGRATE_HEADING("Creando cliente demo..."))
        customer, _ = Customer.objects.get_or_create(
            name="Cliente Habitual",
            defaults={
                "phone": "2900 555 9999",
                "dni": "3.456.789-1",
                "points": 150,
                "notes": "Cliente frecuente con puntos de fidelización",
            },
        )
        self.stdout.write(f"  - {customer.name} ({customer.points} puntos)")

        self.stdout.write(self.style.MIGRATE_HEADING("Configuración de fidelización..."))
        config, _ = LoyaltyConfig.objects.get_or_create(
            pk=1,
            defaults={
                "points_per_currency": Decimal("1"),
                "points_required_for_discount": 100,
                "discount_amount": Decimal("10"),
                "max_discount_percent": 50,
            },
        )
        self.stdout.write(
            f"  - {config.points_per_currency} punto por moneda, "
            f"{config.points_required_for_discount} puntos -> {config.discount_amount} UYU, "
            f"máx. descuento manual {config.max_discount_percent}%"
        )

        self.stdout.write(self.style.MIGRATE_HEADING("Configuración de happy hour..."))
        happy_hour, _ = HappyHourConfig.objects.get_or_create(
            pk=1,
            defaults={
                "enabled": True,
                "start_time": time(18, 0),
                "end_time": time(21, 0),
                "discount_percent": Decimal("15"),
                "name": "Happy hour 18-21",
            },
        )
        self.stdout.write(
            f"  - {happy_hour.name}: {happy_hour.discount_percent}% OFF "
            f"({happy_hour.start_time:%H:%M} a {happy_hour.end_time:%H:%M}, "
            f"{'habilitado' if happy_hour.enabled else 'deshabilitado'})"
        )

        self.stdout.write(self.style.MIGRATE_HEADING("Configuración de ventas (ticket POS)..."))
        sale_config, _ = SaleConfig.objects.get_or_create(
            pk=1, defaults={"pos_print_ticket": True}
        )
        self.stdout.write(
            f"  - imprimir ticket en POS: {'sí' if sale_config.pos_print_ticket else 'no'}"
        )

        self.stdout.write(self.style.SUCCESS("Seed demo completado (idempotente)."))
