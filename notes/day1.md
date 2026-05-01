# Day 1

Building the Django e-commerce API: M2M relationships, project restructuring, management commands, Python packaging, and the first DRF endpoint (serializer → view → URL).

---

## 1. Many-to-Many: why `OrderItem` exists

### The relationship

- One **Order** contains many **Products**
- One **Product** appears in many **Orders**
- That's many-to-many — and it can't be represented with simple ForeignKeys

### The bridge/junction table

`OrderItem` resolves the M2M *and* carries extra data (`quantity`) that doesn't belong on either Order or Product alone.

```
Order  (1) ──< (many) OrderItem (many) >── (1)  Product
```

- One Order → many OrderItems (via `order_id` FK)
- One Product → many OrderItems (via `product_id` FK)
- The combination of those two FKs creates the M2M

### Worked example

**Product**
| id | name     | price |
|----|----------|-------|
| 1  | T-shirt  | 20    |
| 2  | Jeans    | 50    |
| 3  | Sneakers | 80    |

**Order**
| order_id | user  | status    |
|----------|-------|-----------|
| A        | Alice | CONFIRMED |
| B        | Bob   | PENDING   |

**OrderItem** (the bridge)
| id | order_id | product_id | quantity |
|----|----------|------------|----------|
| 1  | A        | 1          | 2        |
| 2  | A        | 2          | 1        |
| 3  | B        | 1          | 3        |
| 4  | B        | 3          | 1        |

Alice's order (A) contains 2 T-shirts and 1 Jeans. Bob's order (B) contains 3 T-shirts and 1 Sneakers. Notice T-shirt (Product 1) appears in **both** orders — that's the many-to-many in action.

### Why a bridge instead of a list/JSON column

- A single `product_id` column → only one product per order ❌
- A comma-separated string → no quantity, no FK integrity ❌
- Repeating order rows per product → duplicates Order data on every row ❌
- **Separate OrderItem table** → normalized, supports quantity, FK integrity ✅

---

## 2. The `through` and `related_name` parameters

```python
products = models.ManyToManyField(Product, through='OrderItem', related_name='orders')
```

### `through='OrderItem'`

Tells Django: "Don't auto-create a hidden join table — use **this** model as the bridge." Without it, Django would silently create `apis_order_products` with just `(order_id, product_id)` and there'd be nowhere for `quantity` to live.

### `related_name='orders'`

Controls the **reverse accessor** name on the other side of the relationship:

| Direction          | Without `related_name`     | With `related_name='orders'`   |
|--------------------|----------------------------|--------------------------------|
| Order → Products   | `order.products.all()`     | `order.products.all()` (same)  |
| Product → Orders   | `product.order_set.all()`  | `product.orders.all()`         |

Pure naming/ergonomics — no DB impact.

---

## 3. Direct vs indirect relationships

- **No direct FK** between Order and Product (neither table has a column pointing at the other)
- **The relationship is carried by OrderItem** — the JOIN through OrderItem *is* the relationship
- This is precisely the point of a junction table: it lets two tables relate many-to-many without a direct column

---

## 4. SQL behind `order.products.all()`

```sql
SELECT product.id, product.name, product.description, product.price, product.stock, product.image
FROM apis_product AS product
INNER JOIN apis_orderitem AS orderitem
    ON product.id = orderitem.product_id
WHERE orderitem.order_id = 'A';
```

The M2M field is **purely Python sugar** — same SQL whether you write `order.products.all()` (with the M2M field) or `Product.objects.filter(orderitem__order=order)` (without it).

### Inspecting the SQL Django generates

```python
qs = order.products.all()
print(qs.query)      # prints the SQL
```

### The duplicate-row gotcha

If the same product has multiple OrderItem rows in the same order, `order.products.all()` returns the product multiple times. Use `.distinct()` to dedupe — or just iterate `order.orderitem_set.all()` and access `.product` on each row.

---

## 5. M2M field: keep or drop?

| Accessor                    | Pros                                    | Cons                                |
|-----------------------------|-----------------------------------------|-------------------------------------|
| `order.products.all()`      | Reads naturally for product-info displays | Loses quantity; needs `.distinct()` |
| `order.orderitem_set.all()` | Always gives quantity; no duplicates    | Slightly more verbose               |

**Verdict for real e-commerce code**: many projects drop the M2M field because they almost always need `quantity`, which forces them through `orderitem_set` anyway. The M2M field becomes dead weight.

---

## 6. The `LookupError: No installed app with label 'apis'` error

### What happened

`models.py` was placed inside the **project package** (`apis/apis/`), and `AUTH_USER_MODEL = 'apis.User'` referenced an app called `apis`. But `INSTALLED_APPS` didn't contain `'apis'`, so Django couldn't find the User model.

### Why the project package isn't auto-treated as an app

Django was designed assuming **one project = many apps**. Auto-promoting the project package to an app would mix configuration code (`settings.py`, `urls.py`) with feature code (`models.py`, `views.py`) — confusing as projects grow.

### Two ways to fix

| Option | What | Pros | Cons |
|--------|------|------|------|
| A — Register project package as an app | Add `'apis'` to `INSTALLED_APPS` | Quick, no file moves | Mixes config + feature code |
| B — Create a real app and move models | Create `store/`, move models there, register `'store'` | Clean separation, scales | More upfront files |

We chose Option B.

---

## 7. Project restructure (what we did)

### Before

```
apis/
├── manage.py
├── db.sqlite3
└── apis/                    ← project + models mixed in here
    ├── settings.py
    ├── urls.py
    └── models.py            ← wrong location
```

### After

```
apis/
├── manage.py
├── db.sqlite3               ← fresh, with custom User
├── db.sqlite3.bak           ← backup of the old one
├── apis/                    ← project package (config only)
│   ├── settings.py
│   └── urls.py
└── store/                   ← app package (the actual code)
    ├── __init__.py
    ├── apps.py
    ├── models.py            ← moved here
    ├── admin.py
    ├── views.py
    ├── tests.py
    └── migrations/
        ├── __init__.py
        └── 0001_initial.py
```

### Changes to `settings.py`

```python
INSTALLED_APPS = [
    # ...
    'store',               # added
]

AUTH_USER_MODEL = 'store.User'   # was 'apis.User'
```

### Other steps

- Installed `Pillow` (required by `ImageField` on Product)
- Backed up `db.sqlite3` → `db.sqlite3.bak` (custom User model can't coexist with existing default `auth_user` table)
- Ran `python manage.py makemigrations store` → created `0001_initial.py`
- Ran `python manage.py migrate` → applied all 19 migrations

---

## 8. Multiple apps per project

A Django project can (and usually should) contain many apps:

```
apis/
├── apis/          ← project (config)
├── store/         ← products, orders
├── accounts/      ← user auth, profiles
├── payments/      ← stripe, invoices
└── reviews/       ← product ratings
```

Apps **can import from each other**:

```python
# payments/models.py
from store.models import Order

class Payment(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT)
```

### When to split

- By **domain concept** (orders, payments, reviews) — not by technical layer
- When `models.py` crosses ~300 lines
- When a feature could plausibly be reused in another project
- **Don't pre-split** — start with one app, add more as features grow

---

## 9. Management commands (the populate script)

### Where management commands must live

```
<app>/management/commands/<command_name>.py
```

Concretely for `store`:

```
store/
└── management/
    ├── __init__.py             ← required (even if empty)
    └── commands/
        ├── __init__.py         ← required (even if empty)
        └── populate_db.py      ← filename = command name
```

The filename **becomes the command name**. So `populate_db.py` → `python manage.py populate_db`.

### The script (final version)

```python
import random
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import lorem_ipsum

from store.models import User, Product, Order, OrderItem


class Command(BaseCommand):
    help = 'Creates application data'

    def handle(self, *args, **kwargs):
        user = User.objects.filter(username='admin').first()
        if not user:
            user = User.objects.create_superuser(username='admin', password='test')

        products = [
            Product(name="A Scanner Darkly", description=lorem_ipsum.paragraph(), price=Decimal('12.99'), stock=4),
            Product(name="Coffee Machine", description=lorem_ipsum.paragraph(), price=Decimal('70.99'), stock=6),
            # ... more products
        ]
        Product.objects.bulk_create(products)
        products = Product.objects.all()

        for _ in range(3):
            order = Order.objects.create(user=user)
            for product in random.sample(list(products), 2):
                OrderItem.objects.create(order=order, product=product, quantity=random.randint(1, 3))
```

### Bugs fixed from the original

| Bug | Fix |
|-----|-----|
| `from api.models import ...` | `from store.models import ...` (app is `store`, not `api`) |
| `from django.contrib.auth.models import User` | Removed — would have shadowed the custom `store.User` |
| Script lived nowhere Django could discover | Placed at `store/management/commands/populate_db.py` |

### Run it

```bash
python manage.py populate_db
```

### Verify discovery

```bash
python manage.py help
```

The command should appear under `[store]` section. If it doesn't show up, an `__init__.py` is missing.

### Idempotency

The User part has `if not user` — safe to re-run. The Products and Orders parts don't — re-running creates duplicates. Add this guard at the top of `handle` if needed:

```python
if Product.objects.exists():
    self.stdout.write('Already populated, skipping.')
    return
```

---

## 10. `__init__.py` files

### What they do

Mark a folder as an importable Python **package**. Without `__init__.py`, `from store.management.commands.populate_db import ...` fails with `ModuleNotFoundError`.

### Rules

- **Each folder needs its own** — they don't inherit from parents or siblings
- **Can be (and usually are) empty** — they're just markers
- **Auto-created by `startapp`** for the standard folders (`migrations/`)
- **Must be created manually** for non-standard folders like `management/` and `commands/`

### Project's full list

```
apis/apis/__init__.py
apis/store/__init__.py
apis/store/migrations/__init__.py
apis/store/management/__init__.py
apis/store/management/commands/__init__.py
```

### Quick scaffold for new commands

```bash
mkdir -p store/management/commands
touch store/management/__init__.py store/management/commands/__init__.py store/management/commands/my_command.py
```

---

## 11. `__pycache__` folders

- Auto-generated by Python — bytecode cache (`.pyc` files) for faster imports
- Filename encodes Python version: `models.cpython-314.pyc`
- **Safe to delete** — Python recreates them automatically
- **Never commit to git** — add `__pycache__/` to `.gitignore`

---

## 12. Django REST Framework setup

Added DRF to the project:

```python
# settings.py
INSTALLED_APPS = [
    # ...
    'store',
    'rest_framework',
]
```

DRF is itself a Django app — once registered in `INSTALLED_APPS`, it provides serializers, viewsets, browsable API, authentication, permissions, etc.

---

## 13. Serializers — the API's view of the model

A serializer is a **translation layer between Python objects and JSON**:

- **Outbound**: Model instance → dict → JSON (response)
- **Inbound**: JSON → dict → validated → Model instance (POST/PUT)

### Our first serializer

```python
# store/serializers.py
from rest_framework import serializers
from .models import Product

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ('name', 'description', 'price', 'stock')
```

### What `fields` controls (bidirectional whitelist)

**Outbound** — only listed fields appear in JSON responses:

```python
ProductSerializer(product).data
# → {"name": "T-shirt", "description": "...", "price": "20.00", "stock": 5}
# id, image, in_stock, orders are NOT included
```

**Inbound** — only listed fields are accepted from incoming JSON. Anything else is silently dropped (mass-assignment protection).

### Why a whitelist matters

- Hides internal fields (passwords, internal IDs, audit timestamps)
- Prevents mass-assignment attacks (clients can't sneak in `is_admin: true`)
- Decouples API from DB schema (rename DB columns without breaking the API)

### Three ways to define field membership

```python
fields = ('id', 'name', 'price')          # whitelist (recommended)
exclude = ('image',)                       # blacklist
fields = '__all__'                         # everything (dangerous — leaks new fields automatically)
```

Avoid `'__all__'` in production — if someone adds `internal_cost` to the model later, it leaks via the API.

### Including a `@property`

Properties aren't auto-included. Declare them explicitly:

```python
class ProductSerializer(serializers.ModelSerializer):
    in_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = ('id', 'name', 'description', 'price', 'stock', 'in_stock')
```

---

## 14. The first view — `product_list`

```python
# store/views.py
from .models import Product
from .serializers import ProductSerializer
from django.http import JsonResponse

def product_list(request):
    products = Product.objects.all()
    serializer = ProductSerializer(products, many=True)
    return JsonResponse({'data': serializer.data})
```

### Key points

- **`many=True`** — tells the serializer to expect a queryset (multiple objects), not a single instance. Returns a list of dicts instead of a single dict.
- **`serializer.data`** — the actual serialized output (a `ReturnList` of dicts), ready to be JSON-encoded.
- **`JsonResponse`** — Django's built-in helper that sets `Content-Type: application/json` and serializes the dict.

### Function-based view vs DRF's APIView

This is a plain Django function view that *uses* a DRF serializer. A more idiomatic DRF version would use `@api_view`, `APIView`, or a `ViewSet` — those give you the browsable API, auth integration, throttling, and content negotiation. We'll likely refactor to that next.

---

## 15. URL routing — the `name` parameter

```python
# store/urls.py
from django.urls import path
from .views import product_list

urlpatterns = [
    path('', product_list, name='product-list'),
]
```

### What `name` does

It's a **stable label** for the URL pattern. The URL works without it, but `name` lets you reference the URL by label instead of hardcoding the path.

### Without `name`

```python
return redirect('/products/')                # hardcoded
<a href="/products/">All</a>                 # hardcoded everywhere
```

If the URL changes from `/products/` to `/api/v2/products/`, every hardcoded reference breaks.

### With `name`

```python
from django.urls import reverse
reverse('product-list')                      # → '/products/'
return redirect('product-list')              # in views
{% url 'product-list' %}                     # in templates
```

The path lives in **one place** (urls.py). Change it there, every `reverse()` follows.

### `reverse()` with parameters

```python
path('products/<int:id>/', product_detail, name='product-detail')

reverse('product-detail', kwargs={'id': 5})  # → '/products/5/'
```

### Namespacing for multiple apps

```python
# project urls.py
path('store/', include('store.urls', namespace='store')),
path('blog/', include('blog.urls', namespace='blog')),

reverse('store:product-list')                # → '/store/'
reverse('blog:product-list')                 # → '/blog/'
```

Both apps can have a `'product-list'` name without conflict.

### Naming convention

Standard pattern: `<resource>-<action>`:

```python
path('', product_list, name='product-list'),
path('<int:id>/', product_detail, name='product-detail'),
path('<int:id>/orders/', product_orders, name='product-orders'),
```

DRF's routers generate names following this exact convention automatically — matching it manually keeps things consistent.

---

## 16. Function-Based Views (FBVs)

**In simple terms**: a view is just a Python function that takes a `request` and returns a `response`. That's it.

```python
def product_list(request):
    products = Product.objects.all()
    serializer = ProductSerializer(products, many=True)
    return JsonResponse({'data': serializer.data})
```

### How the request flows

```
Client GET /products/
        ↓
URL router matches → calls product_list(request)
        ↓
Function returns response → sent back to client
```

### Plain Django FBV vs DRF FBV

- **Plain Django FBV** = function returns `JsonResponse` / `HttpResponse`. Works but verbose for APIs.
- **DRF FBV** = same function with `@api_view(['GET', 'POST', ...])` decorator. Adds JSON parsing, browsable API, content negotiation, automatic 405 if wrong method.

### Other view styles in DRF

| Style                  | When to use                                  |
|------------------------|----------------------------------------------|
| FBV (`@api_view`)      | Simple endpoints, custom logic, learning     |
| `APIView` (CBV)        | Multiple methods on one resource             |
| `ListAPIView` etc.     | Standard CRUD with little customization      |
| `ViewSet` + Router     | Full REST resource — auto-generates URLs     |

Start with FBVs, move to CBVs as patterns repeat.

---

## 17. URL path converters — `<int:pk>`

**In simple terms**: `<int:pk>` is Django's way of saying "match an integer here and pass it to the view as `pk`."

### Anatomy

```
<  int  :  pk  >
   │       │
   │       └── variable name (you choose)
   └────────── converter (must be from a fixed list)
```

### What's strict vs flexible

- **Strict**: brackets `< >`, the colon, and the converter name (must be one of the built-ins below)
- **Flexible**: the variable name (`pk`, `id`, `product_id` — anything you want)

### Built-in converters

| Converter | Matches                                  | Example URL                |
|-----------|------------------------------------------|----------------------------|
| `str`     | Any non-empty string excluding `/`        | `<str:name>`               |
| `int`     | Zero or positive integers                 | `<int:pk>` → `/5/`         |
| `slug`    | Letters, numbers, hyphens, underscores    | `<slug:title>` → `/my-post/` |
| `uuid`    | Hyphenated lowercase UUID                 | `<uuid:order_id>`          |
| `path`    | Any string **including** `/`              | `<path:filename>`          |

### Critical: name must match the view parameter

```python
# urls.py
path('<int:pk>/', product_detail, name='product-detail')

# views.py
def product_detail(request, pk):     # parameter MUST be 'pk'
    ...
```

If you change `<int:pk>` to `<int:id>`, the view function must change to `def product_detail(request, id):`.

### Validation is automatic

If the URL doesn't match the converter, Django returns a 404 *before* your view runs:

| URL request | Result with `<int:pk>` |
|-------------|------------------------|
| `/5/`       | ✅ matches, `pk=5`     |
| `/abc/`     | ❌ 404 (not int)       |
| `/-3/`      | ❌ 404 (negative)      |

### Why `pk` specifically?

Django convention. `pk` = "primary key" — works regardless of the actual column name. DRF's generic views and routers default to `pk` too, so sticking with it keeps everything consistent.

---

## 18. The `Response` ↔ `@api_view` pairing rule

**The error we hit**: `AssertionError: .accepted_renderer not set on Response`

**In simple terms**: if you use DRF's `Response`, you **must** also use `@api_view` (or `APIView`). They come as a pair.

### What went wrong

```python
def product_detail(request, pk):     # ❌ no @api_view decorator
    product = get_object_or_404(Product, pk=pk)
    return Response(serializer.data)  # ❌ Response has no renderer
```

### The fix

```python
@api_view(['GET'])                    # ✅ added decorator
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    return Response(serializer.data)
```

### Why DRF designed it this way

DRF's `Response` is **deferred** — it just holds Python data and trusts a renderer to convert it into the actual HTTP body. The renderer is chosen by **content negotiation** (looking at the client's `Accept` header):

```
Accept: application/json    → JSON renderer
Accept: text/html           → browsable API HTML page
Accept: */*                 → default (JSON)
```

That negotiation step happens inside `@api_view` / `APIView`. Without it, no renderer is attached → assertion error.

### Quick decision table

| You're returning…       | Required setup        | Why                          |
|-------------------------|-----------------------|------------------------------|
| DRF's `Response`        | `@api_view(...)` (FBV) or `APIView` (CBV) | Renderer must be attached |
| Django's `JsonResponse` | Nothing               | Renders to JSON itself        |
| Django's `HttpResponse` | Nothing               | Returns raw bytes/string      |

### The mental rule

```
Response  ←→  @api_view
```

Always paired. Use one without the other and you crash.

### Which to choose?

For an API project where `rest_framework` is already installed:
- **Pick DRF style** (`@api_view` + `Response`) — you get the browsable API for free, and content negotiation handles future HTML/CSV/XML clients.
- **Don't mix styles** within the same file — pick one and stay consistent.

---

## Quick reference: commands run during the day

```bash
# Project setup / restructure
pip install Pillow
mv db.sqlite3 db.sqlite3.bak
python manage.py makemigrations store
python manage.py migrate

# Populate data
python manage.py populate_db

# Verification
python manage.py check
python manage.py help                        # list all commands
python manage.py shell -c "from store.models import User, Product, Order, OrderItem; print(User.objects.count(), Product.objects.count(), Order.objects.count(), OrderItem.objects.count())"

# DRF
pip install djangorestframework               # (assuming this was already done)
python manage.py runserver                   # browse the new endpoint
```

---

## Key takeaways

1. **Junction tables** (`OrderItem`) are the standard pattern for M2M with extra fields.
2. **`through` + `related_name`** are convenience layers; the actual relationship lives in the FKs on the bridge table.
3. **Project ≠ App** — Django enforces the split; the project package isn't automatically an app.
4. **Custom `AUTH_USER_MODEL`** must be set *before* the first migration, or you have to reset the database.
5. **Management commands** live at `<app>/management/commands/<name>.py` and need `__init__.py` at every folder level.
6. **`__init__.py`** is the empty marker file that makes Python treat a folder as an importable package. Each folder needs its own.
7. **Serializers** are bidirectional whitelists — they control what JSON the API exposes (response) and what it accepts (request). Use explicit `fields`, avoid `'__all__'`.
8. **URL `name=`** decouples your code from URL paths — always include it. Pattern: `<resource>-<action>`.
9. **A view = a function that takes `request` and returns a response.** `@api_view` upgrades plain Django FBVs into DRF FBVs (browsable API, JSON parsing, content negotiation).
10. **`<int:pk>` URL syntax is strict** for the converter, flexible for the variable name. The variable name **must** match the view function's parameter name exactly.
11. **DRF `Response` ↔ `@api_view` is a mandatory pair.** Using `Response` without the decorator crashes with `.accepted_renderer not set`. If you don't want DRF's machinery, use Django's `JsonResponse` instead.
