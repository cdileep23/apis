# Day 1

First day of the Django + DRF e-commerce project. Restructured the project into proper apps, modeled the Order/Product/OrderItem domain, set up the custom user, wrote a populate script, and built the first DRF endpoint end-to-end (serializer → view → URL). Notes are organized by concept and framework principle so I can re-open them in six months and reload context fast.

---

## Concept 1 — Many-to-Many relationships and the junction table pattern

### The setup

- One **Order** contains many **Products**.
- One **Product** appears in many **Orders**.
- That's many-to-many — and **it cannot be represented with a single ForeignKey** in either direction.

### Why a bridge/junction table is the right answer

A junction table sits between the two and resolves the M2M with two ForeignKeys. In our case it's `OrderItem`, and it carries an **extra field** (`quantity`) that doesn't logically belong on either Order or Product alone.

```
Order  (1) ──< (many) OrderItem (many) >── (1)  Product
```

- One Order → many OrderItems (via `order_id` FK)
- One Product → many OrderItems (via `product_id` FK)
- The pair of FKs is **the M2M relationship**

### Worked example

| Product | id | name | price |
|---|---|---|---|
|  | 1 | T-shirt | 20 |
|  | 2 | Jeans | 50 |
|  | 3 | Sneakers | 80 |

| Order | order_id | user | status |
|---|---|---|---|
|  | A | Alice | CONFIRMED |
|  | B | Bob | PENDING |

| OrderItem (bridge) | id | order_id | product_id | quantity |
|---|---|---|---|---|
|  | 1 | A | 1 | 2 |
|  | 2 | A | 2 | 1 |
|  | 3 | B | 1 | 3 |
|  | 4 | B | 3 | 1 |

T-shirt (id=1) appears in **both** orders A and B — that's M2M in action.

### Why not a simpler representation?

| Attempted shortcut | Why it fails |
|---|---|
| Single `product_id` FK on Order | Only one product per order |
| Comma-separated product IDs in a string | No quantity, no FK integrity, no joins |
| Repeating Order rows once per product | Duplicates Order data, integrity nightmare |
| Separate `OrderItem` table (junction) | Normalized, supports `quantity`, FK-integrity intact |

### Principle

> When two entities have a many-to-many relationship **and the relationship itself carries data** (quantity, role, joined_at, …), the data lives on a junction table — never crammed into either side.

---

## Concept 2 — `through=` and `related_name` on `ManyToManyField`

```python
products = models.ManyToManyField(Product, through='OrderItem', related_name='orders')
```

### `through='OrderItem'` — STRICT RULE when extras are needed

Tells Django **don't auto-create a hidden join table — use this model as the bridge**. Without it, Django silently creates `apis_order_products` with just `(order_id, product_id)` columns and there's nowhere for `quantity` to live.

> If your M2M needs to carry any extra field, `through=` is **required**, not optional.

### `related_name='orders'` — ergonomic only

Controls the name of the **reverse accessor** on the other side:

| Direction | Without `related_name` | With `related_name='orders'` |
|---|---|---|
| Order → Products | `order.products.all()` | `order.products.all()` (same) |
| Product → Orders | `product.order_set.all()` | `product.orders.all()` |

Pure naming — no DB schema impact. (More on `related_name` in [day2.md](day2.md), Concept 2 — including the strict rule that it's invalid on scalar fields.)

---

## Concept 3 — Direct vs indirect relationships (and the SQL behind M2M)

### There is no direct FK between Order and Product

Neither table has a column pointing at the other. **The relationship is carried entirely by `OrderItem`** — the JOIN through OrderItem *is* the relationship.

### What `order.products.all()` actually runs

```sql
SELECT product.*
FROM apis_product AS product
INNER JOIN apis_orderitem AS orderitem
    ON product.id = orderitem.product_id
WHERE orderitem.order_id = 'A';
```

> The M2M field is **purely Python sugar**. The SQL is identical whether you write `order.products.all()` (using the M2M field) or `Product.objects.filter(orderitem__order=order)` (without it).

### Inspecting the SQL Django will run

```python
qs = order.products.all()
print(qs.query)        # prints the raw SQL
```

### The duplicate-row gotcha

If the same product appears in multiple OrderItem rows in the same order (e.g. someone added 2 T-shirts twice), `order.products.all()` returns the product **multiple times**. Two ways to handle:

```python
order.products.distinct()                # dedupe
order.items.all()                         # iterate OrderItems and read .product (cleaner — keeps quantity)
```

### M2M field — keep it or drop it?

| Accessor | Pros | Cons |
|---|---|---|
| `order.products.all()` | Reads naturally for product displays | Loses quantity; needs `.distinct()` |
| `order.items.all()` (via `related_name`) | Always gives quantity; no duplicates | Slightly more verbose |

For a real e-commerce flow you almost always need `quantity`, so the M2M field becomes dead weight and many projects drop it.

---

## Concept 4 — Project ≠ App in Django

This was the biggest mental-model shift today.

### The error that taught me

```
LookupError: No installed app with label 'apis'
```

I'd put `models.py` inside the **project package** (`apis/apis/models.py`) and set `AUTH_USER_MODEL = 'apis.User'`. But `INSTALLED_APPS` didn't contain `'apis'`, so Django couldn't find the model.

### The principle

Django was designed assuming **one project = many apps**. The project package holds **configuration** (`settings.py`, `urls.py`, `wsgi.py`, `asgi.py`); apps hold **features** (models, views, serializers, migrations). Auto-promoting the project package to an app would mix the two and get confusing as the codebase grows.

| Project package | App package |
|---|---|
| `settings.py`, `urls.py`, `wsgi.py`, `asgi.py` | `models.py`, `views.py`, `admin.py`, `migrations/` |
| Configuration only | Feature code only |
| Listed nowhere — Django finds it via `DJANGO_SETTINGS_MODULE` | Listed in `INSTALLED_APPS` |

### Two ways to fix the LookupError

| Option | What | Pros | Cons |
|---|---|---|---|
| A — Promote project to app | Add `'apis'` to `INSTALLED_APPS` | Quick, no file moves | Mixes config + feature code |
| B — Make a real app and move models | Create `store/`, move models there, register `'store'` | Clean separation, scales | More upfront file work |

I chose B.

### What B actually involved

```
Before                           After
apis/                            apis/
├── manage.py                    ├── manage.py
├── db.sqlite3                   ├── db.sqlite3       ← fresh, with custom User
└── apis/                        ├── db.sqlite3.bak   ← backup
    ├── settings.py              ├── apis/            ← project (config only)
    ├── urls.py                  │   ├── settings.py
    └── models.py  ❌            │   └── urls.py
                                 └── store/           ← app (the actual code)
                                     ├── __init__.py
                                     ├── apps.py
                                     ├── models.py    ✅ moved here
                                     ├── admin.py
                                     ├── views.py
                                     └── migrations/
                                         ├── __init__.py
                                         └── 0001_initial.py
```

```python
# settings.py changes
INSTALLED_APPS = [..., 'store']           # added
AUTH_USER_MODEL = 'store.User'            # was 'apis.User'
```

---

## Concept 5 — `AUTH_USER_MODEL`: STRICT timing rule

```python
AUTH_USER_MODEL = 'store.User'
```

### The rule

> A custom `AUTH_USER_MODEL` **must be set before the first migration runs**. After the default `auth_user` table exists in the database, swapping the user model in mid-flight is a hard problem — Django's solution in practice is "wipe the database and re-migrate."

### What I had to do

- Backed up `db.sqlite3` → `db.sqlite3.bak`
- Deleted the original db
- Set `AUTH_USER_MODEL = 'store.User'`
- Ran `python manage.py makemigrations store` → created `0001_initial.py` with the custom User
- Ran `python manage.py migrate` → applied all 19 migrations against the fresh db

### Lesson

For a brand-new Django project, **decide whether you need a custom user model first** — even if you only do `class User(AbstractUser): pass` for now. Adding the substitution later is painful.

---

## Concept 6 — Multi-app architecture

A Django project can (and usually should) contain many apps:

```
apis/
├── apis/        ← project (config)
├── store/       ← products, orders
├── accounts/    ← auth, profiles
├── payments/    ← stripe, invoices
└── reviews/     ← ratings
```

Apps can import from each other freely:

```python
# payments/models.py
from store.models import Order

class Payment(models.Model):
    order = models.ForeignKey(Order, on_delete=models.PROTECT)
```

### When to split (principle, not strict rule)

- Split by **domain concept** (orders, payments, reviews) — not by technical layer (models, views, etc.)
- Consider a split when `models.py` crosses ~300 lines
- Consider a split when a feature could plausibly be reused in another project
- **Don't pre-split** — start with one app, peel off another when the seam is obvious

---

## Concept 7 — Management commands: STRICT location rule

### The strict path

> A custom command must live at exactly `<app>/management/commands/<command_name>.py`. Django auto-discovers commands by walking `INSTALLED_APPS` and looking for that exact subpath. Anywhere else and `python manage.py <command>` won't see it.

```
store/
└── management/
    ├── __init__.py             ← required (even if empty)
    └── commands/
        ├── __init__.py         ← required (even if empty)
        └── populate_db.py      ← filename = command name
```

The **filename becomes the command name**: `populate_db.py` → `python manage.py populate_db`.

### The script (final, working version)

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

### Bugs I had to fix in the original

| Bug | Fix |
|---|---|
| `from api.models import ...` | `from store.models import ...` (app is `store`, not `api`) |
| `from django.contrib.auth.models import User` | Removed — would shadow the custom `store.User` |
| File lived in a random folder | Moved to `store/management/commands/populate_db.py` |

### Verify discovery

```bash
python manage.py help     # the new command should appear under [store]
```

If it doesn't show up, an `__init__.py` is missing somewhere along the path.

### Idempotency note

The User part has `if not user` — safe to re-run. Products and Orders aren't guarded — re-running creates duplicates. Add this if needed:

```python
if Product.objects.exists():
    self.stdout.write('Already populated, skipping.')
    return
```

---

## Concept 8 — `__init__.py`: STRICT package-marker rule

### What it does

Marks a folder as an importable Python **package**. Without `__init__.py`, `from store.management.commands.populate_db import ...` fails with `ModuleNotFoundError`.

### Strict rules

> - **Each folder needs its own.** They don't inherit from parents or siblings.
> - **Can be empty** — they're just markers.
> - **Auto-created** by `startapp` for the standard folders (`migrations/`).
> - **Must be created manually** for non-standard folders like `management/` and `commands/`.

### This project's full list

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

## Concept 9 — Serializers as bidirectional translators

### What a serializer is

A serializer is a **translation layer between Python objects and JSON** — and it works in **both** directions:

- **Outbound** (response): Model instance → dict → JSON
- **Inbound** (POST/PUT): JSON → dict → validated → Model instance

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

### What `fields` controls — bidirectional whitelist

**Outbound** — only listed fields appear in JSON responses:

```python
ProductSerializer(product).data
# → {"name": "T-shirt", "description": "...", "price": "20.00", "stock": 5}
# id, image, in_stock, orders are NOT included
```

**Inbound** — only listed fields are accepted from incoming JSON. Anything else is **silently dropped** (this is actually mass-assignment protection — see below).

### Why a whitelist matters

- Hides internal fields (passwords, internal IDs, audit timestamps)
- Prevents **mass-assignment attacks** — clients can't sneak in `is_admin: true`
- Decouples API from DB schema (rename DB columns without breaking the API)

### Three ways to define field membership — and which to pick

```python
fields  = ('id', 'name', 'price')   # whitelist  (recommended)
exclude = ('image',)                # blacklist
fields  = '__all__'                 # everything (dangerous in production)
```

> Avoid `'__all__'` in production. If a field like `internal_cost` gets added to the model later, it'll silently leak through the API.

### Including a `@property` — STRICT: must be declared explicitly

`ModelSerializer` auto-generates fields from the model's **database columns**. `@property` methods are not columns, so they aren't auto-included. You must declare them explicitly:

```python
class ProductSerializer(serializers.ModelSerializer):
    in_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = ('id', 'name', 'description', 'price', 'stock', 'in_stock')
```

Note `read_only=True` — you can't *write* a `@property`, only read it. (More on this in [day2.md](day2.md), Concept 6, where I learned the alternative pattern: `SerializerMethodField` with the strict `get_<field_name>` naming rule.)

---

## Concept 10 — What a view actually is

> **A view is just a Python function that takes a `request` and returns a `response`.** That's the whole abstraction.

### Our first view

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

### Request flow

```
Client GET /products/
        ↓
URL router matches → calls product_list(request)
        ↓
Function returns response → sent back to client
```

### Two key serializer-side details

- **`many=True`** — tells the serializer to expect a queryset (multiple objects), not a single instance. Returns a list of dicts instead of a single dict.
- **`serializer.data`** — the actual serialized output (a `ReturnList`), ready for JSON encoding.

### Plain Django FBV vs DRF FBV

- **Plain Django FBV** = function returns `JsonResponse` / `HttpResponse`. Works but verbose for APIs.
- **DRF FBV** = same function with `@api_view(['GET', 'POST', ...])` decorator. Adds JSON parsing, browsable API, content negotiation, automatic 405 for wrong methods.

### Other view styles in DRF (when to graduate)

| Style | When to use |
|---|---|
| FBV (`@api_view`) | Simple endpoints, custom logic, learning |
| `APIView` (CBV) | Multiple HTTP methods on one resource |
| `ListAPIView`, etc. | Standard CRUD with little customization |
| `ViewSet` + Router | Full REST resource — auto-generates URLs |

Start with FBVs, move to CBVs when patterns repeat.

---

## Concept 11 — URL `name=` and the decoupling principle

```python
# store/urls.py
from django.urls import path
from .views import product_list

urlpatterns = [
    path('', product_list, name='product-list'),
]
```

### What `name` does

It's a **stable label** for the URL pattern. The URL works without it — but `name` lets you reference the URL by label instead of hardcoding the path everywhere.

### Without `name` (don't do this)

```python
return redirect('/products/')               # hardcoded
<a href="/products/">All</a>                # hardcoded
```

If `/products/` ever changes to `/api/v2/products/`, **every hardcoded reference breaks**.

### With `name` (the right way)

```python
from django.urls import reverse
reverse('product-list')                     # → '/products/'
return redirect('product-list')             # in views
{% url 'product-list' %}                    # in templates
```

The path lives in **one place** (urls.py). Change it there, every `reverse()` call follows.

### `reverse()` with parameters

```python
path('products/<int:id>/', product_detail, name='product-detail')
reverse('product-detail', kwargs={'id': 5})  # → '/products/5/'
```

### Namespacing for multiple apps

```python
# project urls.py
path('store/', include('store.urls', namespace='store')),
path('blog/',  include('blog.urls',  namespace='blog')),

reverse('store:product-list')               # → '/store/'
reverse('blog:product-list')                # → '/blog/'
```

Both apps can have a `'product-list'` name without conflict.

### Naming convention (not strict, but useful)

```python
path('',                product_list,    name='product-list'),
path('<int:id>/',       product_detail,  name='product-detail'),
path('<int:id>/orders/', product_orders, name='product-orders'),
```

DRF's routers auto-generate names following `<resource>-<action>`. Matching it manually keeps things consistent across the codebase.

---

## Concept 12 — URL path converters: `<int:pk>`

> `<int:pk>` is Django's way of saying "match an integer here and pass it to the view as the parameter `pk`."

### Anatomy

```
<  int  :  pk  >
   │       │
   │       └── variable name (you choose)
   └────────── converter (must come from a fixed list)
```

### What's STRICT vs flexible

- **Strict**: brackets `< >`, the colon, and the converter name (must be one of the built-ins below)
- **Flexible**: the variable name (`pk`, `id`, `product_id` — anything you want)

### Built-in converters

| Converter | Matches | Example URL |
|---|---|---|
| `str` | Any non-empty string excluding `/` | `<str:name>` |
| `int` | Zero or positive integers | `<int:pk>` → `/5/` |
| `slug` | Letters, numbers, hyphens, underscores | `<slug:title>` → `/my-post/` |
| `uuid` | Hyphenated lowercase UUID | `<uuid:order_id>` |
| `path` | Any string **including** `/` | `<path:filename>` |

### STRICT RULE: variable name MUST match the view parameter

```python
# urls.py
path('<int:pk>/', product_detail, name='product-detail')

# views.py
def product_detail(request, pk):     # parameter MUST be named 'pk'
    ...
```

Change `<int:pk>` to `<int:id>` in urls.py and the view function signature **must change** to `def product_detail(request, id):`. Mismatch → `TypeError: got an unexpected keyword argument 'pk'`.

### Validation is automatic

If the URL doesn't match the converter, Django returns 404 *before* your view runs:

| URL request | Result with `<int:pk>` |
|---|---|
| `/5/` | matches, `pk=5` |
| `/abc/` | 404 (not int) |
| `/-3/` | 404 (negative) |

### Why `pk` specifically?

Django convention. `pk` = "primary key" — works regardless of the underlying column name. DRF's generic views and routers also default to `pk`, so sticking with it keeps everything consistent.

---

## Concept 13 — DRF `Response` ↔ `@api_view`: STRICT mandatory pairing

### The error that taught me

```
AssertionError: .accepted_renderer not set on Response
```

> If you use DRF's `Response`, you **must** also use `@api_view` (or `APIView`). They are a mandatory pair — using one without the other crashes.

### What went wrong

```python
def product_detail(request, pk):     # ❌ no @api_view decorator
    product = get_object_or_404(Product, pk=pk)
    return Response(serializer.data) # ❌ Response has no renderer attached
```

### The fix

```python
@api_view(['GET'])                   # ✅ decorator added
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    return Response(serializer.data)
```

### The principle behind why

DRF's `Response` is **deferred** — it just holds Python data and trusts a renderer to convert it into the actual HTTP body. The renderer is chosen by **content negotiation** (looking at the client's `Accept` header):

```
Accept: application/json    → JSON renderer
Accept: text/html           → browsable API HTML page
Accept: */*                 → default (JSON)
```

That negotiation step happens **inside** `@api_view` / `APIView`. Without it, no renderer is attached → assertion error.

### Quick decision table

| You're returning… | Required setup | Why |
|---|---|---|
| DRF's `Response` | `@api_view(...)` (FBV) or `APIView` (CBV) | Renderer must be attached |
| Django's `JsonResponse` | Nothing | Renders to JSON itself |
| Django's `HttpResponse` | Nothing | Returns raw bytes/string |

### The mental rule

```
Response  ←→  @api_view
```

Always paired. Use one without the other and you crash.

### Which style to choose for an API project?

- **Pick DRF style** (`@api_view` + `Response`). You get the browsable API for free, and content negotiation handles future HTML/CSV/XML clients automatically.
- **Don't mix styles** within the same file — pick one and stay consistent.

---

## Things I asked for plain-English explanation on (Day 1)

Recap of the questions where I stopped to ask for the *why* behind something — useful for re-anchoring six months from now.

1. **"Why does the LookupError say no installed app with label 'apis'?"** → because the project package isn't an app by default. Project ≠ app — the project holds config, apps hold features. Either register the project as an app (option A) or move models into a real app (option B, what I did).
2. **"What's `through=` actually doing?"** → it tells Django which existing model to use as the M2M bridge instead of auto-creating a hidden one. Required when the bridge needs extra fields like `quantity`.
3. **"What's `related_name` for?"** → renames the reverse accessor so you can write `product.orders.all()` instead of the default `product.order_set.all()`. Pure ergonomics — no DB impact. (Strict-rule deep dive in [day2.md](day2.md).)
4. **"What's `__init__.py` for and why do I need so many?"** → marker file that says "this folder is a Python package, you can `import` from it." Each folder needs its own — they don't inherit.
5. **"Why does `python manage.py populate_db` say 'Unknown command'?"** → the file isn't at `<app>/management/commands/<name>.py`, or an `__init__.py` is missing in the chain. The path is strict.
6. **"What does `name='product-list'` on a path do? Things still work without it."** → it's a label for `reverse()` so you don't hardcode URL strings everywhere. Saves you when the URL changes later.
7. **"Why is `<int:pk>` written like that? Can I change `pk`?"** → the converter (`int`, `str`, `slug`, `uuid`, `path`) is strict; the variable name is yours to choose — but it must match the view function's parameter name exactly.
8. **"What's the deal with this `accepted_renderer not set` error?"** → DRF's `Response` is deferred; it needs `@api_view` or `APIView` to attach a renderer via content negotiation. They're a mandatory pair.

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
python manage.py help                  # list all commands (custom one shows under [store])
python manage.py shell -c "from store.models import User, Product, Order, OrderItem; print(User.objects.count(), Product.objects.count(), Order.objects.count(), OrderItem.objects.count())"

# DRF
pip install djangorestframework        # (assuming first time)
python manage.py runserver             # browse the new endpoint
```

---

## Strict rules I learnt today (cheat sheet)

| # | Rule | Why it's strict |
|---|---|---|
| 1 | M2M with extras → `through=` is required | Otherwise Django creates a hidden join table with no room for the extras |
| 2 | `AUTH_USER_MODEL` must be set BEFORE the first migration | Swapping it after `auth_user` exists is effectively a database reset |
| 3 | Custom commands must live at `<app>/management/commands/<name>.py` | Django's discovery walks that exact subpath in each `INSTALLED_APPS` entry |
| 4 | Every package folder needs its own `__init__.py` | Python's import system uses it as the package marker |
| 5 | `@property` on a model must be declared explicitly in the serializer | `ModelSerializer` only auto-generates fields from DB columns |
| 6 | URL path converter variable name must match the view parameter name | The router passes the matched value as a kwarg using that exact name |
| 7 | DRF `Response` requires `@api_view` (FBV) or `APIView` (CBV) | `Response` is deferred — needs the decorator/CBV to attach a renderer |
| 8 | Don't use `fields = '__all__'` in production serializers | New model fields silently leak through the API |

---

## Key takeaways

1. **Junction tables** (`OrderItem`) are the standard pattern for M2M with extra fields. The two FKs *are* the relationship.
2. **`through=` and `related_name`** are convenience layers; the actual relationship lives in the FKs on the bridge table.
3. **Project ≠ App.** Django enforces the split — the project package isn't automatically an app. Splitting them is a feature, not a chore.
4. **Custom `AUTH_USER_MODEL` first, migrate second** — otherwise reset the database.
5. **Management commands** have a strict location (`<app>/management/commands/<name>.py`) and need `__init__.py` at every folder level.
6. **`__init__.py`** is the marker file that turns a folder into an importable Python package. Each folder needs its own.
7. **Serializers are bidirectional whitelists** — they shape both response JSON and accepted request JSON. Use explicit `fields`. Avoid `'__all__'`.
8. **A view = a function that takes `request` and returns a response.** `@api_view` upgrades a plain Django FBV into a DRF FBV (browsable API, JSON parsing, content negotiation).
9. **URL `name=`** decouples your code from URL paths — use it everywhere. Pattern: `<resource>-<action>`.
10. **`<int:pk>` URL syntax**: converter is strict, variable name is flexible — but the variable name **must** match the view function's parameter exactly.
11. **DRF `Response` ↔ `@api_view` is a mandatory pair.** Using `Response` without the decorator crashes with `.accepted_renderer not set`. If you don't want DRF's machinery, return Django's `JsonResponse` instead.
