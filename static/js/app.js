/* ==========================================================================
   El Patio SIG — JS personalizado
   ========================================================================== */
(function () {
    "use strict";

    /* ----------------------------- Confirmación de borrado / acciones ----------------------------- */
    // Cualquier <form data-confirm="..."> pide confirmación antes de enviarse.
    document.addEventListener("submit", function (e) {
        var form = e.target;
        if (form && form.matches && form.matches("form[data-confirm]")) {
            if (!window.confirm(form.getAttribute("data-confirm") || "¿Confirmar la acción?")) {
                e.preventDefault();
            }
        }
    });

    /* ----------------------------- Sidebar móvil ----------------------------- */
    document.addEventListener("click", function (e) {
        if (e.target.closest("[data-sidebar-toggle]")) {
            document.body.classList.toggle("sidebar-open");
        }
        if (e.target.closest("[data-sidebar-close]")) {
            document.body.classList.remove("sidebar-open");
        }
    });

    /* ----------------------------- Botones de impresión ----------------------------- */
    document.addEventListener("click", function (e) {
        var btn = e.target.closest("[data-print]");
        if (btn) {
            e.preventDefault();
            window.print();
        }
    });

    /* ==========================================================================
       POS — Carrito de venta
       ========================================================================== */
    var posForm = document.getElementById("pos-form");
    if (posForm) {
        var cfg = window.POS_CONFIG || {
            currency: "$",
            emptyCartMessage: "El carrito está vacío. Agregá productos para cobrar.",
            exceedingStockMessage: "Stock insuficiente para el producto «{name}». Disponible: {stock}."
        };

        var cart = {}; // { productId: {name, price, priceDisplay, stock, qty} }

        var cartItemsEl = document.getElementById("cart-items");
        var cartTotalEl = document.getElementById("cart-total");
        var discountEl = document.getElementById("pos-discount");
        var cashEl = document.getElementById("pos-cash");
        var cashRowEl = document.getElementById("cash-row");
        var paymentEl = document.getElementById("pos-payment");
        var changeEl = document.getElementById("pos-change");
        var checkoutBtn = document.getElementById("pos-checkout");

        // Formato moneda UYU: "$U 1.234,56" (millares con punto, decimales con coma)
        function fmt(value) {
            var n = Number(value || 0);
            var neg = n < 0;
            var fixed = Math.abs(n).toFixed(2);
            var parts = fixed.split(".");
            var intPart = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ".");
            return (neg ? "-" : "") + cfg.currency + intPart + "," + parts[1];
        }

        function cartCount() {
            return Object.keys(cart).length;
        }

        function cartTotal() {
            var total = 0;
            Object.keys(cart).forEach(function (id) {
                total += cart[id].price * cart[id].qty;
            });
            return total;
        }

        function netTotal() {
            var discount = parseFloat(discountEl ? discountEl.value : 0) || 0;
            return Math.max(0, cartTotal() - discount);
        }

        function updateChange() {
            if (!changeEl || !paymentEl) return;
            var method = paymentEl.value;
            if (method !== "efectivo") {
                changeEl.textContent = fmt(0);
                if (cashRowEl) cashRowEl.style.display = "none";
                if (cashEl) cashEl.value = "";
                return;
            }
            if (cashRowEl) cashRowEl.style.display = "";
            var cash = parseFloat(cashEl ? cashEl.value : 0) || 0;
            var change = Math.max(0, cash - netTotal());
            changeEl.textContent = fmt(change);
        }

        function render() {
            if (!cartItemsEl) return;
            var ids = Object.keys(cart);
            if (!ids.length) {
                cartItemsEl.innerHTML = '<div class="text-center text-muted py-4 small">Tocá un producto para agregarlo</div>';
            } else {
                cartItemsEl.innerHTML = ids.map(function (id) {
                    var item = cart[id];
                    var line = item.price * item.qty;
                    return (
                        '<div class="cart-item" data-id="' + id + '">' +
                            '<div class="cart-item-info">' +
                                '<div class="cart-item-name">' + item.name + '</div>' +
                                '<div class="cart-item-price">' + (item.priceDisplay || fmt(item.price)) + ' c/u</div>' +
                            '</div>' +
                            '<div class="cart-item-qty">' +
                                '<button type="button" class="btn btn-outline-secondary btn-sm" data-act="minus" aria-label="Restar">−</button>' +
                                '<span class="cart-qty-value">' + item.qty + '</span>' +
                                '<button type="button" class="btn btn-outline-secondary btn-sm" data-act="plus" aria-label="Sumar">+</button>' +
                            '</div>' +
                            '<span class="cart-item-subtotal">' + fmt(line) + '</span>' +
                            '<button type="button" class="cart-item-remove" data-act="remove" aria-label="Quitar">✕</button>' +
                        '</div>'
                    );
                }).join("");
            }

            if (cartTotalEl) cartTotalEl.textContent = fmt(netTotal());
            updateChange();
        }

        function addProduct(id, name, price, stock, priceDisplay) {
            if (!(id in cart)) {
                cart[id] = { name: name, price: price, priceDisplay: priceDisplay, stock: stock, qty: 0 };
            }
            if (cart[id].qty >= cart[id].stock) {
                window.alert(cfg.exceedingStockMessage.replace("{name}", name).replace("{stock}", stock));
                return;
            }
            cart[id].qty += 1;
            render();
        }

        // Click en tarjetas de producto (+ teclado: Enter/Espacio)
        document.querySelectorAll(".pos-product-card").forEach(function (card) {
            function pick() {
                if (card.classList.contains("disabled")) return;
                addProduct(
                    card.getAttribute("data-product-id"),
                    card.getAttribute("data-product-name"),
                    parseFloat(card.getAttribute("data-product-price")) || 0,
                    parseFloat(card.getAttribute("data-product-stock")) || 0,
                    card.getAttribute("data-product-price-display")
                );
            }
            card.addEventListener("click", pick);
            card.addEventListener("keydown", function (e) {
                if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    pick();
                }
            });
        });

        // Botones del carrito (sumar/restar/quitar) por delegación
        if (cartItemsEl) {
            cartItemsEl.addEventListener("click", function (e) {
                var btn = e.target.closest("[data-act]");
                if (!btn) return;
                var row = btn.closest(".cart-item");
                var id = row.getAttribute("data-id");
                var act = btn.getAttribute("data-act");
                if (act === "plus") {
                    if (cart[id].qty < cart[id].stock) {
                        cart[id].qty += 1;
                    } else {
                        window.alert(cfg.exceedingStockMessage.replace("{name}", cart[id].name).replace("{stock}", cart[id].stock));
                    }
                } else if (act === "minus") {
                    cart[id].qty -= 1;
                    if (cart[id].qty <= 0) delete cart[id];
                } else if (act === "remove") {
                    delete cart[id];
                }
                render();
            });
        }

        // Vaciar carrito
        var clearBtn = document.getElementById("cart-clear");
        if (clearBtn) {
            clearBtn.addEventListener("click", function () {
                if (!cartCount()) return;
                if (window.confirm("¿Vaciar el carrito?")) {
                    cart = {};
                    render();
                }
            });
        }

        // Recalcular al cambiar método de pago / efectivo / descuento
        if (paymentEl) paymentEl.addEventListener("change", updateChange);
        if (cashEl) cashEl.addEventListener("input", updateChange);
        if (discountEl) discountEl.addEventListener("input", function () {
            render();
        });

        // Envío del formulario: arma los inputs ocultos product_id[] / quantity[]
        posForm.addEventListener("submit", function (e) {
            var ids = Object.keys(cart);
            if (!ids.length) {
                e.preventDefault();
                window.alert(cfg.emptyCartMessage);
                return;
            }
            if (checkoutBtn && checkoutBtn.disabled) {
                e.preventDefault();
                return;
            }
            // Quitar inputs ocultos previos (por si se reenvía)
            posForm.querySelectorAll('input[name="product_id"], input[name="quantity"]').forEach(function (el) {
                el.remove();
            });
            ids.forEach(function (id) {
                var i1 = document.createElement("input");
                i1.type = "hidden";
                i1.name = "product_id";
                i1.value = id;
                var i2 = document.createElement("input");
                i2.type = "hidden";
                i2.name = "quantity";
                i2.value = cart[id].qty;
                posForm.appendChild(i1);
                posForm.appendChild(i2);
            });
        });

        render();
    }

    /* ----------------------------- POS — Filtro de búsqueda ----------------------------- */
    var posSearch = document.getElementById("pos-search");
    if (posSearch) {
        posSearch.addEventListener("input", function () {
            var q = posSearch.value.trim().toLowerCase();
            document.querySelectorAll(".pos-product-card").forEach(function (card) {
                var name = (card.getAttribute("data-product-name") || "").toLowerCase();
                var show = !q || name.indexOf(q) !== -1;
                card.closest(".col-6, .col-md-4, .col-xl-3, [class*='col-']").style.display = show ? "" : "none";
            });
        });
    }
})();
