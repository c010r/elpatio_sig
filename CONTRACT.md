# CONTRATO TÉCNICO — El Patio SIG

Especificación que los agentes (backend, frontend, seguridad, pruebas) deben
seguir. Cada agente trabaja SOLO en su área de propiedad (ver sección
"Propiedad de archivos"). Ante conflicto, este documento manda.

## Stack

- Django 5.2 LTS (Python 3.14), proyecto: `config`, apps bajo `config.settings.dev|prod`.
- Bootstrap 5.3 (CDN) + `django-bootstrap5` para formularios + CSS/JS propios en `static/`.
- DB: SQLite dev / PostgreSQL prod (switch por `.env` → `DB_ENGINE`).
- Tests: pytest + pytest-django.

## Admin de Django DESHABILITADO (decisión del dueño del pub)

No existe `/admin/` ni `django.contrib.admin` en INSTALLED_APPS. Toda la
administración (usuarios, roles, CRUD de todos los módulos, reportes) se hace
con pantallas propias del sistema. Consecuencias:
- Los archivos `admin.py` de las apps son código inerte (no se importan): no
  mantenerlos ni depender de ellos.
- Los superusuarios (createsuperuser o pantallas propias) pasan los chequeos
  de rol: `RoleRequiredMixin` y `role_required` permiten `is_superuser`.

## Propiedad de archivos

| Agente | Área de propiedad |
|--------|-------------------|
| Backend | `config/settings/base.py`, `*/models.py`, `*/forms.py`, `*/views.py`, `*/urls.py`, `*/admin.py`, `*/apps.py`, `*/managers.py`, comandos de gestión (`*/management/commands/*`) |
| Frontend | `templates/**` (todos los .html), `static/**` (css/js/img), NO tocar Python |
| Seguridad | `config/settings/prod.py`, `config/settings/base.py` (solo partes de seguridad), `.env.example`, decoradores/mixins de permisos en `core/`, headers, dependencias sensibles. Puede proponer fixes a otros agentes vía reporte |
| Pruebas | `tests/**` en cada app + `pytest.ini`/`pyproject.toml` + `conftest.py`. NO modificar código de producción |

## Convenciones globales

- Español (AR) para textos de UI y nombres de modelos/vistas (con `verbose_name` en español).
- Toda vista de negocio requiere login (`LoginRequiredMixin` o `@login_required`).
- Permisos por **Grupos de Django**: `admin`, `gerente`, `bartender`, `cajero`.
  - Bartender/camarero: mesas, comandas, ver stock.
  - Cajero: caja, ventas, cobros, tickets, clientes.
  - Gerente: todo lo anterior + inventario, compras, reportes, reservas, empleados.
  - Admin: todo + gestión de usuarios.
- URLs con prefijo por módulo: `/ventas/`, `/inventario/`, `/mesas/`, `/empleados/`,
  `/clientes/`, `/compras/`, `/reservas/`, `/reportes/`.
- Mensajes con framework `django.contrib.messages`.
- Toda moneda: `DecimalField(max_digits=10, decimal_places=2)`. Cantidades: `DecimalField(max_digits=10, decimal_places=2)`.
- Fechas: `created_at = DateTimeField(auto_now_add=True)` en todos los modelos.
- `is_active = BooleanField(default=True)` en modelos maestros (borrado lógico).

## Aplicaciones y modelos

### core
Sin modelos. Mixins: `RoleRequiredMixin` (chequea grupo), `StaffRequiredMixin`.
Vista `dashboard` en `/` con KPIs (ventas de hoy, tickets de hoy, mesas ocupadas,
stock bajo, reservas de hoy).

### accounts
- `Profile(OneToOneField→User)`: `phone`, `role_label` (derivado del grupo principal).
- Señal `post_save` crea Profile al crear User.
- Páginas: login, logout, cambio de contraseña, gestión de usuarios (admin):
  crear usuario + asignar grupo.

### inventory
- `Category`: `name`, `description`, `is_active`.
- `Product`: `name`, `category(FK)`, `unit` (choices: unidad, botella, jarra,
  porción, kg, l), `purchase_price`, `sale_price`, `stock_current`,
  `stock_min` (alerta), `barcode` (único, opcional), `is_active`.
- `StockMovement`: `product(FK)`, `quantity` (con signo), `movement_type`
  (choices: entrada, salida, ajuste, venta, compra), `reference` (texto libre),
  `user(FK)`, `created_at`. Método `apply()` actualiza `stock_current` de forma
  transaccional.
- Vistas: listado categorías (CRUD), listado productos (CRUD), movimientos de
  stock (crear entrada/salida/ajuste), vista "stock bajo".

### sales
- `CashRegister`: `opened_by(FK user)`, `opened_at`, `closed_at`, `opening_amount`,
  `closing_amount`, `expected_amount`, `actual_amount`, `status`
  (choices: abierta, cerrada), `notes`. Regla: UNA caja abierta por vez.
- `Sale`: `ticket_number` (único, secuencial por día, formato `YYYYMMDD-####`),
  `user(FK)`, `cash_register(FK, null)`, `table(FK, null)`, `customer(FK, null)`,
  `items` (relación inversa), `subtotal`, `discount`, `total`, `payment_method`
  (choices: efectivo, tarjeta, transferencia, otro), `cash_received`,
  `change`, `status` (choices: completada, anulada), `created_at`,
  `voided_by`, `voided_at`, `void_reason`.
- `SaleItem`: `sale(FK)`, `product(FK)`, `quantity`, `unit_price`, `subtotal`.
- Vistas: POS (grilla de productos + carrito + cobro), listado de ventas,
  detalle/ticket (imprimible), anular venta, abrir/cerrar caja.
- Lógica: al completar una venta se descuenta stock (StockMovement tipo venta).
  Al anular, se repone. Ticket numérico secuencial diario.

### tables
- `Table`: `number` (único), `capacity`, `zone` (choices: barra, salón, terraza,
  privado), `status` (choices: libre, ocupada, reservada, limpieza), `is_active`.
- `Order` (comanda): `table(FK)`, `waiter(FK user)`, `status` (choices: abierta,
  cerrada, pagada, cancelada), `note`, `opened_at`, `closed_at`, `total` (derivado).
- `OrderItem`: `order(FK)`, `product(FK)`, `quantity`, `unit_price`, `status`
  (choices: pendiente, entregado, cancelado), `note`, `requested_at`.
- Vistas: mapa de mesas (grid por zona), abrir mesa, agregar ítems, marcar
  entregado, cerrar comanda → genera `Sale` (descuenta stock, puede cobrar desde
  cajero), historial.

### staff
- `Employee`: `user(FK OneToOne)`, `position` (choices: bartender, camarero,
  cajero, gerente, admin), `hire_date`, `hourly_rate`, `is_active`.
- `Shift`: `employee(FK)`, `date`, `start_time`, `end_time`, `note`,
  `worked_hours` (calculado).
- Vistas: listado empleados (CRUD), turnos (CRUD), "mi turno" para empleados
  (fichar entrada/salida).

### customers
- `Customer`: `name`, `phone`, `email`, `dni`, `birth_date`, `points`
  (fidelización), `notes`, `created_at`, `is_active`.
- Regla fidelización: 1 punto por cada $1 gastado (redondeo a entero), canje
  configurable: `LoyaltyConfig` (singleton): `points_per_currency` (default 1),
  `points_required_for_discount` (default 100), `discount_amount` (default 10).
  Caché de valores.
- Vistas: listado clientes (CRUD), detalle con historial de ventas y puntos,
  canje de puntos (genera descuento en venta).

### purchases
- `Supplier`: `name`, `contact_name`, `phone`, `email`, `address`, `cuit`,
  `notes`, `is_active`.
- `PurchaseOrder`: `number` (único, `OC-####`), `supplier(FK)`,
  `status` (choices: pendiente, recibida, cancelada), `total`, `ordered_by(FK
  user)`, `created_at`, `received_at`.
- `PurchaseItem`: `order(FK)`, `product(FK)`, `quantity`, `unit_cost`, `subtotal`.
- Vistas: proveedores (CRUD), órdenes de compra (CRUD), "recibir orden" →
  genera StockMovement entrada y actualiza stock/purchase_price.

### reservations
- `Reservation`: `table(FK)`, `customer(FK, null)`, `name`, `phone`, `date`,
  `start_time`, `party_size`, `status` (choices: pendiente, confirmada,
  cancelada, completada), `note`, `created_by(FK user)`, `created_at`.
- Regla: no se puede reservar una mesa ocupada en el mismo horario (validación
  en form/model).
- Vistas: listado, CRUD, agenda de hoy, confirmar/cancelar.

### reports
Sin modelos. Vistas con agregaciones (QuerySet):
- Ventas por período (filtro fechas, total, cantidad, ticket promedio).
- Productos más vendidos (top N por cantidad/ingresos).
- Ventas por método de pago y por usuario.
- Ganancia bruta por período (suma (precio - costo) por ítem vendido).
- Valor del inventario (suma stock × costo) y por categoría.
- Comandas por mesa / ocupación.
Export CSV en cada reporte (botón).

## Páginas / navegación (frontend)

Layout base: sidebar (módulos según rol) + navbar superior (usuario, caja
abierta/cerrada, logout). Páginas:

1. `login.html` — login (Bootstrap centrado).
2. `dashboard.html` — KPIs con cards + top productos.
3. Inventario: `category_list.html`, `category_form.html`,
   `product_list.html`, `product_form.html`, `stock_movement_list.html`,
   `stock_movement_form.html`, `stock_low.html`.
4. Ventas: `pos.html` (grid productos + carrito, JS), `sale_list.html`,
   `sale_detail.html` (ticket imprimible), `cash_register_open.html`,
   `cash_register_close.html`.
5. Mesas: `table_map.html` (grid por zona con colores por estado),
   `order_detail.html` (comanda con ítems), `order_form.html` (abrir/agregar).
6. Empleados: `employee_list.html`, `employee_form.html`, `shift_list.html`,
   `shift_form.html`, `my_shift.html`.
7. Clientes: `customer_list.html`, `customer_form.html`, `customer_detail.html`
   (historial + puntos).
8. Compras: `supplier_list.html`, `supplier_form.html`, `purchase_list.html`,
   `purchase_form.html`, `purchase_receive.html`.
9. Reservas: `reservation_list.html`, `reservation_form.html`,
   `reservation_today.html`.
10. Reportes: `sales_report.html`, `products_report.html`, `profit_report.html`,
    `inventory_value_report.html` + botón CSV.
11. Usuarios (admin): `user_list.html`, `user_form.html`.

Templates por defecto de admin de Django OK.

## Código de ejemplo (patrón de vista)

```python
# core/views.py
class RoleRequiredMixin(LoginRequiredMixin):
    roles = []  # nombres de grupos
    def dispatch(self, request, *args, **kwargs):
        if self.roles and not request.user.groups.filter(name__in=self.roles).exists():
            messages.error(request, "No tenés permisos para esta acción.")
            return redirect("dashboard")
        return super().dispatch(request, *args, **kwargs)
```

## Convención de nombres de URLs (usar EXACTAMENTE estos `name`)

`app_name` por módulo: `core`, `inventory`, `sales`, `tables`, `staff`,
`customers`, `purchases`, `reservations`, `reports`, `accounts`.

- core: `core:dashboard`, `core:login`, `core:logout`
- inventory: `category_list`, `category_create`, `category_update`,
  `category_delete`, `product_list`, `product_create`, `product_update`,
  `product_delete`, `stock_movement_list`, `stock_movement_create`, `stock_low`
- sales: `pos`, `sale_list`, `sale_detail`, `sale_void`, `cash_register_open`,
  `cash_register_close`
- tables: `table_map`, `table_create`, `table_update`, `table_delete`,
  `order_detail`, `order_create`, `order_add_item`, `order_item_status`,
  `order_close`
- staff: `employee_list`, `employee_create`, `employee_update`,
  `employee_delete`, `shift_list`, `shift_create`, `shift_update`,
  `shift_delete`, `my_shift`
- customers: `customer_list`, `customer_create`, `customer_update`,
  `customer_delete`, `customer_detail`, `customer_redeem`
- purchases: `supplier_list`, `supplier_create`, `supplier_update`,
  `supplier_delete`, `purchase_list`, `purchase_create`, `purchase_detail`,
  `purchase_receive`, `purchase_cancel`
- reservations: `reservation_list`, `reservation_create`, `reservation_update`,
  `reservation_delete`, `reservation_today`, `reservation_confirm`,
  `reservation_cancel`
- reports: `sales_report`, `products_report`, `profit_report`,
  `inventory_value_report` (+ variantes `_csv` para exportar CSV)
- accounts: `user_list`, `user_create`, `user_update`, `user_toggle_active`

## Notas para agentes

- Ejecutar SIEMPRE `python manage.py makemigrations <app>` + `migrate` después de
  crear modelos, usando `.venv\Scripts\python.exe`.
- Verificar con `python manage.py check` al terminar.
- El agente de pruebas corre `pytest`; debe crear fixtures en `conftest.py`
  (usuario admin, grupos, productos, caja abierta).
