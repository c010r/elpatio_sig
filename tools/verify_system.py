"""
El Patio SIG — Verificador de integración (coordinador).

Uso:  .\\.venv\\Scripts\\python.exe tools\\verify_system.py [--urls] [--smoke]

- --urls : cruza los URL names definidos por el backend con los {% url %} usados
           en templates/ y reporta nombres faltantes o sobrantes.
- --smoke: recorre todas las URLs de negocio con el rol adecuado (test client)
           e imprime el status code de cada una.

Requiere que backend y frontend hayan terminado su fase 1.
"""
import os
import re
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.test import Client  # noqa: E402
from django.urls import NoReverseMatch, get_resolver, reverse  # noqa: E402

settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, "testserver"]

OUR_APPS = [
    "core", "accounts", "inventory", "sales", "tables", "staff",
    "customers", "purchases", "reservations", "reports",
]


def collect_url_names():
    """Devuelve {namespace:name: pattern} para nuestras apps."""
    resolver = get_resolver()
    names = {}
    for pattern in resolver.url_patterns:
        if hasattr(pattern, "url_patterns"):
            ns = pattern.namespace
            for sub in pattern.url_patterns:
                if getattr(sub, "name", None):
                    names[f"{ns}:{sub.name}"] = sub
    return {k: v for k, v in names.items() if k.split(":")[0] in OUR_APPS}


def check_templates(names):
    """Escanea templates/ por {% url 'name' %} y compara contra names."""
    url_re = re.compile(r"""\{%\s*url\s+['"]([^'"]+)['"]""")
    used = set()
    problems = []
    templates_dir = settings.BASE_DIR / "templates"
    for root, _dirs, files in os.walk(templates_dir):
        for f in files:
            if not f.endswith(".html"):
                continue
            path = os.path.join(root, f)
            with open(path, encoding="utf-8") as fh:
                for m in url_re.finditer(fh.read()):
                    name = m.group(1)
                    used.add(name)
                    if name not in names:
                        problems.append(f"{os.path.relpath(path, templates_dir)}: URL inexistente {name!r}")
    missing_defined = [n for n in sorted(names) if n not in used and not n.endswith("_csv")]
    return problems, sorted(used), missing_defined


def smoke(names):
    """Recorre las URLs con el usuario adecuado (o sin login) e imprime status."""
    from django.contrib.auth.models import Group, User

    groups = ["admin", "gerente", "bartender", "cajero"]
    for g in groups:
        Group.objects.get_or_create(name=g)
    users = {}
    for g in groups:
        u, _ = User.objects.get_or_create(username=f"smoke_{g}")
        u.set_password("SmokePass123!")
        u.groups.add(Group.objects.get(name=g))
        u.save()
        users[g] = u

    # URL name -> roles permitidos (matriz del contrato)
    matrix = {
        "core:dashboard": ["admin", "gerente", "bartender", "cajero"],
        "inventory:product_list": ["admin", "gerente"],
        "inventory:product_create": ["admin", "gerente"],
        "inventory:category_list": ["admin", "gerente"],
        "inventory:stock_movement_list": ["admin", "gerente"],
        "inventory:stock_low": ["admin", "gerente", "bartender"],
        "sales:pos": ["admin", "gerente", "cajero"],
        "sales:sale_list": ["admin", "gerente", "cajero"],
        "sales:cash_register_open": ["admin", "gerente", "cajero"],
        "sales:cash_register_close": ["admin", "gerente", "cajero"],
        "tables:table_map": ["admin", "gerente", "bartender"],
        "tables:order_detail": ["admin", "gerente", "bartender"],
        "staff:employee_list": ["admin", "gerente"],
        "customers:customer_list": ["admin", "gerente", "cajero"],
        "customers:customer_detail": ["admin", "gerente", "cajero"],
        "purchases:purchase_list": ["admin", "gerente"],
        "purchases:supplier_list": ["admin", "gerente"],
        "reservations:reservation_list": ["admin", "gerente"],
        "reservations:reservation_today": ["admin", "gerente"],
        "reports:sales_report": ["admin", "gerente"],
        "reports:products_report": ["admin", "gerente"],
        "reports:profit_report": ["admin", "gerente"],
        "reports:inventory_value_report": ["admin", "gerente"],
    }

    results = []
    for name in sorted(names):
        if name not in matrix:
            continue
        try:
            url = reverse(name)
        except NoReverseMatch:
            # URL con argumentos requeridos (detalles); no aplica al smoke simple
            continue
        roles = matrix[name]
        client = Client()
        if roles:
            client.force_login(users[roles[0]])
        resp = client.get(url)
        results.append(f"{resp.status_code:>4}  {name:45} {resp.get('content-type', '')}")
    return results


if __name__ == "__main__":
    names = collect_url_names()
    print(f"URL names definidos por backend: {len(names)}")
    args = sys.argv[1:]
    if "--urls" in args or not args:
        problems, used, missing_defined = check_templates(names)
        print(f"URLs usadas en templates: {len(used)}")
        if problems:
            print("PROBLEMAS:")
            print("\n".join(problems))
        else:
            print("OK: todas las URLs de templates existen.")
        print(f"URLs definidas pero no usadas en templates: {missing_defined}")
    if "--smoke" in args:
        print("SMOKE TEST por URL (primer rol permitido):")
        for line in smoke(names):
            print(line)
