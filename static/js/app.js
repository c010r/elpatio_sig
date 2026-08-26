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

    /* ----------------------------- Toggle de tema claro/oscuro ----------------------------- */
    var themeToggle = document.getElementById("theme-toggle");
    if (themeToggle) {
        var themeIcon = document.getElementById("theme-icon");

        function themeApply(t) {
            document.documentElement.setAttribute("data-theme", t);
            try { localStorage.setItem("ep-theme", t); } catch (e) {}
            if (themeIcon) themeIcon.className = "bi " + (t === "dark" ? "bi-sun" : "bi-moon-stars");
        }

        // Sincroniza el icono con el tema ya aplicado por el script inline del <head>
        var initialTheme = document.documentElement.getAttribute("data-theme") || "light";
        if (themeIcon) themeIcon.className = "bi " + (initialTheme === "dark" ? "bi-sun" : "bi-moon-stars");

        themeToggle.addEventListener("click", function () {
            var current = document.documentElement.getAttribute("data-theme") || "light";
            themeApply(current === "dark" ? "light" : "dark");
        });
    }

    /* ==========================================================================
       POS — Carrito de venta
       ========================================================================== */
    var posForm = document.getElementById("pos-form");
    if (posForm) {
        var cfg = window.POS_CONFIG || {
            currency: "$U ",
            emptyCartMessage: "El carrito está vacío. Agregá productos para cobrar.",
            exceedingStockMessage: "Stock insuficiente para el producto «{name}». Disponible: {stock}.",
            discountExceedsMessage: "El descuento no puede superar el subtotal ({max})."
        };

        var cart = {}; // { productId: {name, price, priceDisplay, stock, qty} }

        var cartItemsEl = document.getElementById("cart-items");
        var cartTotalEl = document.getElementById("cart-total");
        var cartSubtotalEl = document.getElementById("cart-subtotal");
        var cartDiscountLineEl = document.getElementById("cart-discount-line");
        var cartTipLineEl = document.getElementById("cart-tip-line");
        var discountEl = document.getElementById("pos-discount");
        var tipEl = document.getElementById("pos-tip");
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

        function discountValue() {
            return parseFloat(discountEl ? discountEl.value : 0) || 0;
        }

        function tipValue() {
            return parseFloat(tipEl ? tipEl.value : 0) || 0;
        }

        // Total final = subtotal - descuento + propina (nunca negativo)
        function netTotal() {
            var subtotal = cartTotal();
            var discount = Math.min(discountValue(), subtotal);
            return Math.max(0, subtotal - discount) + tipValue();
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

            var subtotal = cartTotal();
            var discount = Math.min(discountValue(), subtotal);
            var tip = tipValue();

            if (cartSubtotalEl) cartSubtotalEl.textContent = fmt(subtotal);
            if (cartDiscountLineEl) cartDiscountLineEl.textContent = "-" + fmt(discount);
            if (cartTipLineEl) cartTipLineEl.textContent = fmt(tip);
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

        // Botones rápidos de propina (10/15/20% sobre el subtotal, o "sin")
        document.querySelectorAll(".tip-btn").forEach(function (btn) {
            btn.addEventListener("click", function () {
                var pct = parseFloat(btn.getAttribute("data-tip-percent")) || 0;
                if (pct > 0) {
                    var subtotal = cartTotal();
                    var tip = Math.round(subtotal * pct) / 100;
                    tipEl.value = tip.toFixed(2);
                } else {
                    tipEl.value = "";
                }
                render();
            });
        });

        // Recalcular al cambiar método de pago / efectivo / descuento / propina
        if (paymentEl) paymentEl.addEventListener("change", updateChange);
        if (cashEl) cashEl.addEventListener("input", updateChange);
        if (discountEl) discountEl.addEventListener("input", render);
        if (tipEl) tipEl.addEventListener("input", render);

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
            // Validar descuento: 0 <= discount <= subtotal (el backend re-valida)
            var subtotal = cartTotal();
            var discount = discountValue();
            if (discount > subtotal) {
                e.preventDefault();
                window.alert(cfg.discountExceedsMessage.replace("{max}", fmt(subtotal)));
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

    /* ==========================================================================
       ARQUEO DE CAJA (cash_register_close) — esperado vs contado por método
       ========================================================================== */
    var cashCountTable = document.getElementById("cash-count-table");
    if (cashCountTable) {
        var confirmWrap = document.getElementById("confirm-diff-wrap");
        var confirmCheck = document.getElementById("id_confirm_difference");
        var closeForm = document.getElementById("cash-close-form");
        var countRows = cashCountTable.querySelectorAll('tbody tr[data-method][data-expected]');

        function fmtUYU(value) {
            var n = Number(value || 0);
            var neg = n < 0;
            var fixed = Math.abs(n).toFixed(2);
            var parts = fixed.split(".");
            var intPart = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ".");
            return (neg ? "-" : "") + "$U " + intPart + "," + parts[1];
        }

        function parseNum(v) {
            var n = parseFloat(v);
            return isNaN(n) ? 0 : n;
        }

        function updateCounts() {
            var totalExpected = 0;
            var totalCounted = 0;
            countRows.forEach(function (row) {
                var expected = parseNum(row.getAttribute("data-expected"));
                var input = row.querySelector('input[type="number"]');
                var counted = input ? parseNum(input.value) : 0;
                var diff = counted - expected;
                totalExpected += expected;
                totalCounted += counted;
                var cell = row.querySelector(".diff-cell");
                if (cell) {
                    cell.textContent = fmtUYU(diff);
                    cell.className = "text-end diff-cell " + (Math.abs(diff) < 0.005 ? "diff-zero" : (diff < 0 ? "diff-negative" : "diff-positive"));
                }
            });
            var diffTotal = totalCounted - totalExpected;
            var totalCell = cashCountTable.querySelector(".diff-total");
            if (totalCell) {
                totalCell.textContent = fmtUYU(diffTotal);
                totalCell.className = "text-end diff-total " + (Math.abs(diffTotal) < 0.005 ? "diff-zero" : (diffTotal < 0 ? "diff-negative" : "diff-positive"));
            }
            var hasDiff = Math.abs(diffTotal) >= 0.005;
            if (confirmWrap) confirmWrap.style.display = hasDiff ? "" : "none";
            if (confirmCheck) confirmCheck.checked = false;
            return hasDiff;
        }

        cashCountTable.addEventListener("input", function (e) {
            if (e.target.matches('input[type="number"]')) updateCounts();
        });

        if (closeForm) {
            closeForm.addEventListener("submit", function (e) {
                var hasDiff = updateCounts();
                if (hasDiff && (!confirmCheck || !confirmCheck.checked)) {
                    e.preventDefault();
                    window.alert("Hay diferencia entre lo esperado y lo contado. Marcá la confirmación para cerrar la caja.");
                }
            });
        }

        updateCounts();
    }

    /* ==========================================================================
       EDITOR DE RECETA (product_form) — productos compuestos
       Arma ingredient_id[] / quantity[] al submit según las filas del editor.
       ========================================================================== */
    var recipeEditor = document.getElementById("recipe-editor");
    var recipeCheckbox = document.getElementById("id_is_composed");
    if (recipeEditor && recipeCheckbox) {
        var recipeRows = document.getElementById("recipe-rows");
        var recipeTemplate = document.getElementById("recipe-row-template");

        function recipeSync() {
            recipeEditor.style.display = recipeCheckbox.checked ? "" : "none";
        }
        recipeCheckbox.addEventListener("change", recipeSync);
        recipeSync();

        // Agregar fila (clona la plantilla con todas las opciones)
        var recipeAddBtn = document.getElementById("recipe-add");
        if (recipeAddBtn) {
            recipeAddBtn.addEventListener("click", function () {
                if (!recipeTemplate) return;
                var empty = recipeRows.querySelector(".recipe-empty");
                if (empty) empty.remove();
                recipeRows.appendChild(recipeTemplate.content.cloneNode(true));
            });
        }

        // Quitar fila (delegación)
        recipeRows.addEventListener("click", function (e) {
            var btn = e.target.closest(".recipe-remove");
            if (btn && btn.closest(".recipe-row")) {
                btn.closest(".recipe-row").remove();
            }
        });

        // Submit: inputs ocultos ingredient_id[] / quantity[] (solo filas completas)
        var recipeForm = recipeCheckbox.closest("form");
        if (recipeForm) {
            recipeForm.addEventListener("submit", function () {
                recipeForm.querySelectorAll('input[name="ingredient_id"], input[name="quantity"]').forEach(function (el) {
                    el.remove();
                });
                if (!recipeCheckbox.checked) return;
                recipeRows.querySelectorAll(".recipe-row").forEach(function (row) {
                    var sel = row.querySelector(".recipe-ingredient");
                    var qty = row.querySelector(".recipe-quantity");
                    if (!sel || !sel.value) return;
                    var i1 = document.createElement("input");
                    i1.type = "hidden";
                    i1.name = "ingredient_id";
                    i1.value = sel.value;
                    var i2 = document.createElement("input");
                    i2.type = "hidden";
                    i2.name = "quantity";
                    i2.value = (qty && qty.value) ? qty.value : "0";
                    recipeForm.appendChild(i1);
                    recipeForm.appendChild(i2);
                });
            });
        }
    }
})();
