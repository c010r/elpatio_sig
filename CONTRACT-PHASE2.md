# CONTRATO FASE 2 — El Patio SIG (borrador)

Funcionalidades aprobadas por el dueño del pub para la segunda iteración.
Se refina después de reconciliar la fase 1 (depende de los modelos finales).

## Moneda
- **Peso uruguayo (UYU)**, formato `$U 1.234,56` (filtro `money` en
  `core/templatetags/money.py`).

## 1. Happy hour por franja horaria
- Modelo `HappyHourConfig` (singleton estilo LoyaltyConfig, con caché):
  `enabled`, `start_time`, `end_time`, `discount_percent` (Decimal, 0-100),
  `name` (ej: "Happy hour 18-21").
- Regla: en el POS y al cerrar comanda, si la hora actual cae en la franja y
  `enabled`:
  - Si el ítem tiene `promo_price` activo → se usa el promo (el happy hour NO
    se acumula con promo).
  - Si no → se aplica `discount_percent` sobre el precio regular del ítem.
- El descuento se materializa en el `unit_price` del `OrderItem`/`SaleItem` al
  momento de agregar el ítem (precio congelado, no recalculado después).
- Mostrar banner "🍺 Happy hour: X% OFF (hasta HH:MM)" en POS y comanda.
- Admin (solo admin/gerente): editar config, activar/desactivar.

## 2. Promos por producto
- Agregar a `Product`: `promo_price` (Decimal, null=True, blank=True) y
  `promo_active` (BooleanField default False). `promo_active=True` sin precio
  → inválido (validación en form).
- POS: card del producto muestra precio tacho + precio promo destacado.
- Venta/comanda usa `promo_price` cuando `promo_active` y hay stock.

## 3. Descuentos manuales en venta
- `Sale.discount` ya existe: agregar input en POS (monto $U) y al cerrar
  comanda.
- Validación: 0 <= discount <= subtotal. Límite configurable
  `max_discount_percent` (default 50%) en `LoyaltyConfig` (o `SaleConfig`
  nuevo — decidir en reconciliación).
- El descuento manual NO se acumula con happy hour por ítem (aplica sobre el
  subtotal ya calculado). Total = subtotal - discount + tip.
- Registrar en el ticket "Descuento: -$U X".

## 4. Propinas
- Agregar `Sale.tip` (Decimal, default 0). Input en POS (monto $U o % rápido
  10/15/20%).
- `total = subtotal - discount + tip`. Ticket muestra "Propina: $U X".

## 5. Arqueo de caja detallado
- `CashRegister` agrega: `counted_cash`, `counted_card`, `counted_transfer`,
  `counted_other` (Decimal null) y `difference` (calculado).
- Al cerrar: la vista muestra lo ESPERADO por método (suma de `Sale.total` por
  `payment_method` durante el período abierto, descontando anuladas) y el
  cajero ingresa lo CONTADO por método. `closing_amount` = suma de contado.
  Diferencia por método + total (puede ser negativa).
- Cierre con diferencia ≠ 0: requiere confirmación explícita (checkbox "caja
  cuadrada"/nota) y se registra en el log.

## 6. Gráficos (Chart.js)
- Frontend: incluir Chart.js por CDN en templates de reportes.
- Backend: los reportes pasan series en contexto:
  - `sales_report`: `chart_labels` (días), `chart_data` (totales por día).
  - `products_report`: `chart_labels` (top productos), `chart_data` (cantidad
    o ingresos).
  - `profit_report`: `chart_labels` (días), `chart_data` (ganancia por día).
  - Reporte métodos de pago (nuevo o dentro de sales_report): donut.
- Los gráficos son un "extra": la tabla + CSV siguen siendo la fuente de verdad.

## Notas
- Todas las nuevas columnas vía migraciones (`makemigrations`).
- Tests fase 2: happy hour aplica/no aplica según franja, promo precedence,
  descuento límite, propina en total, arqueo con diferencia, series JSON de
  gráficos.
- Seguridad fase 2: validar que el descuento no permita totales negativos ni
  manipulación vía POST (recalcular en backend, NUNCA confiar en el total
  enviado por el cliente).
