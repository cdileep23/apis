# Day 2

Wiring up nested serializers, computed fields, and URL routing — and learning the framework principles behind each error we hit. Today was less "build new things" and more "learn why the framework reacts the way it does."

---

## Concept 1 — URL routing: `include()` and prefix composition

### The principle

A URL pattern in Django is **always relative** to whatever prefix mounted it. The full path is composed by stacking prefixes from the outside in. Patterns inside an included `urls.py` must **not** start with `/`.

```
project urls.py:    path('products/', include('store.urls'))
                              ↑
                    this prefix is prepended to every pattern in store.urls

store urls.py:      path('orders/', order_list)
                              ↑
                    relative — final URL = /products/orders/
```

### Two errors I hit from this

**(a) The `/orders` 404**

I tried `http://localhost:8000/orders` and got 404. Why? Because `store.urls` was mounted under `products/` in `apis/urls.py`, so `order_list` actually lives at `/products/orders/`. The router tried to match `/orders` against the only top-level prefixes (`admin/`, `products/`), and neither matched.

Two layouts that work:

| Layout | Project urls.py | Resulting URLs |
|---|---|---|
| Nested (current) | `path('products/', include('store.urls'))` | `/products/`, `/products/orders/` |
| Separate includes | `path('products/', include(...))` + `path('orders/', include(...))` | `/products/`, `/orders/` — semantically cleaner |

**(b) The leading-slash bug**

```python
path('/info/', product_info, ...)   # ❌ never matches
path('info/',  product_info, ...)   # ✅ matches /products/info/
```

The leading `/` made Django try to match a URL like `/products//info/` (double slash). URL patterns inside an `include()`d urls.py are concatenated to the prefix as-is, so any leading `/` corrupts the path.

### Mental rule

> The leading `/` belongs to the **mount point**, not the pattern. Patterns are always relative.

---

## Concept 2 — `related_name`: a reverse-accessor name, valid only on relational fields

### What it does

When you declare a relational field (`ForeignKey`, `ManyToManyField`, `OneToOneField`), Django **automatically adds a reverse accessor on the other side** of the relationship. `related_name` controls what that accessor is called.

```python
class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', ...)
    #                                 ↑
    #               adds Order.items so you can do order.items.all()
    #               without it: defaults to order.orderitem_set.all()
```

| Without `related_name` | With `related_name='items'` |
|---|---|
| `order.orderitem_set.all()` | `order.items.all()` |

Pure naming/ergonomics — no DB schema impact.

### The error I hit

```python
order_id = models.UUIDField(
    primary_key=True, default=uuid.uuid4, editable=False,
    related_name='items'    # ❌
)
# TypeError: Field.__init__() got an unexpected keyword argument 'related_name'
```

### The principle behind why scalar fields reject it

`related_name` describes a **reverse relationship**. `UUIDField`, `CharField`, `IntegerField`, `DecimalField` etc. are scalar — they don't relate two tables, they just store a value. There's no "other side" to put an accessor on, so the argument doesn't apply and Django raises `TypeError`.

| Field type | Accepts `related_name`? |
|---|---|
| `ForeignKey`, `ManyToManyField`, `OneToOneField` | ✅ — they have a reverse side |
| `UUIDField`, `CharField`, `IntegerField`, `TextField`, … | ❌ — scalar, no reverse side |

### How `related_name` connects forward to DRF (the link I missed at first)

The `related_name` you pick on the model **becomes the field name** you use for nested serializers:

```python
# models.py
class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items')

# serializers.py
class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    #  ↑
    # MUST match the related_name above. If left as default
    # (orderitem_set), this field name would have to change too,
    # or you'd add source='orderitem_set'.
```

So `related_name` isn't just ergonomic on the ORM side — it shapes the JSON output structure on the API side.

---

## Concept 3 — `__pycache__` and `.pyc` files (and how stale ones can lie to you)

### What they are

Python doesn't directly execute `.py` files — it first **compiles** them into bytecode (a lower-level instruction format) and caches the result inside `__pycache__/`.

```
models.cpython-314.pyc
  │      │       │
  │      │       └── 314 = Python version (3.14)
  │      └────────── cpython = Python implementation (CPython, vs PyPy/Jython)
  └───────────────── source filename (models.py)
```

The version+implementation tag means multiple Python interpreters can share the same source tree without their caches colliding.

### Lifecycle

1. First import → Python compiles `.py` → writes `.pyc` to `__pycache__/`.
2. Next import → Python compares `.py` mtime to `.pyc` mtime.
3. If `.py` is newer → recompile. If not → load `.pyc` directly (faster).

### When the cache lies

I fixed `models.py` on disk, but the traceback **still** showed the buggy `related_name='items'` line. That's because Django's autoreloader was reading from a `.pyc` whose invalidation logic glitched (likely an mtime resolution issue or a partial reload). Solution:

```bash
find apis -name "__pycache__" -type d -exec rm -rf {} +
```

Python regenerates them automatically on next import.

### Principle

`.pyc` files are a **performance optimization** — never load-bearing. Safe to delete anytime. **Never commit** — they contain compiled output that depends on your local Python version.

---

## Concept 4 — `.gitignore` only blocks UNTRACKED files

### The misconception I had

I thought adding `__pycache__/` to `.gitignore` would make git stop tracking the `.pyc` files I'd already committed. It doesn't.

### The actual rule

`.gitignore` only prevents **new, untracked** files from being added. Files that are **already tracked** stay tracked forever — git assumes you committed them on purpose. To untrack them you need:

```bash
git rm -r --cached apis/**/__pycache__
```

- `git rm` → tells git to stop tracking
- `--cached` → keeps the file on disk (only removes from git's index)
- Without `--cached`, the file is also deleted from disk

After this commit, `.gitignore` finally takes effect for those paths.

### Mental model

> `.gitignore` answers "should I start tracking this?" — never "should I stop tracking this?"

---

## Concept 5 — `ModelSerializer` vs plain `Serializer`

### The distinction

| | `ModelSerializer` | `Serializer` |
|---|---|---|
| What it serializes | A Django model instance | Any Python dict / object |
| Requires `Meta` class? | Yes — `Meta.model` must point at the model | No |
| Auto-generates fields | Yes — from the model schema | No — declare every field manually |
| Auto-generates `create()`/`update()` | Yes | No — write them yourself if needed |

### The error I hit

```python
class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order        # ❌ wrong model
        fields = ('product', 'quantity')

# ImproperlyConfigured: Field name `product` is not valid for model `Order`
```

`ModelSerializer` validated `fields` against `Meta.model.product`. `Order` has no `product` field — `OrderItem` does. The fix was `model = OrderItem`.

### Principle

> `Meta.model` is **the schema source of truth** for `ModelSerializer`. Every name in `fields` must be findable on that model — as a field, a `@property`, a method (with arguments-zero), or a related accessor.

### When to use plain `Serializer`

When you're serializing data that isn't tied to a single model. I hit this with `ProductInfoSerializer`:

```python
# views.py
{'products': products_qs, 'count': N, 'max_price': X}   # not a model instance
```

`ModelSerializer` failed (no model to point at). The right choice was the base `Serializer`:

```python
class ProductInfoSerializer(serializers.Serializer):
    products  = ProductSerializer(many=True)
    count     = serializers.IntegerField()
    max_price = serializers.DecimalField(max_digits=10, decimal_places=2)
```

No `Meta` because there's no model — just an explicit shape declaration.

---

## Concept 6 — Computed fields: two patterns, when to pick which

I wanted derived values (`total_price` on Order, `item_subtotal` on OrderItem) in the JSON. DRF gives two ways to do this.

### Pattern A — `SerializerMethodField` (lives in the serializer)

```python
class OrderSerializer(serializers.ModelSerializer):
    total_price = serializers.SerializerMethodField()

    def get_total_price(self, obj):
        return sum(item.product.price * item.quantity for item in obj.items.all())

    class Meta:
        model = Order
        fields = (..., 'total_price')
```

**Naming rule (strict):** the method must be named `get_<field_name>`. DRF looks for that name automatically. Override with `method_name='compute_total'` if you want a different name.

**Signature:** `(self, obj)` — `obj` is the model instance being serialized.

### Pattern B — model `@property` (lives on the model)

```python
class OrderItem(models.Model):
    ...
    @property
    def item_subtotal(self):
        return self.product.price * self.quantity
```

Then just list it in `fields` on the serializer — no extra serializer code:

```python
class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = (..., 'item_subtotal')
```

`ModelSerializer` auto-discovers `@property`s when their name appears in `fields`.

### When to pick which

| Pick `@property` if… | Pick `SerializerMethodField` if… |
|---|---|
| The value is intrinsic to the model (a fact about the row itself) | The value is API-shape only (formatting, joining querysets, request-aware) |
| Other parts of the codebase will reuse it (admin, templates, services) | The computation depends on `self.context['request']` etc. |
| The computation only needs `self` | The serialization needs cross-model logic that doesn't belong on the model |

I picked `@property` for `item_subtotal` (it's an intrinsic fact about an order line) and `SerializerMethodField` for `total_price` (aggregates across the related `items` queryset — arguably could be either, but lives in the serializer for now).

---

## Concept 7 — Source traversal in DRF (`source='product.name'`)

To flatten nested data into the response without nesting a whole serializer:

```python
class OrderItemSerializer(serializers.ModelSerializer):
    product_name  = serializers.CharField(source='product.name', read_only=True)
    product_price = serializers.DecimalField(source='product.price', max_digits=10, decimal_places=2, read_only=True)
```

`source='product.name'` tells DRF: "to fill this field, follow `obj.product.name` on the instance." Dotted paths walk through relations. Without `source`, DRF would look for an attribute literally named `product_name` on `OrderItem` — which doesn't exist.

`read_only=True` keeps these out of write operations (you can't *create* an OrderItem by passing a product name string).

### Alternative — nest the whole product

```python
product = ProductSerializer(read_only=True)
```

Use this when you want the full product object embedded. Use the flattened `source=` approach when you only need 1–2 fields and want a flatter JSON shape.

---

## Concept 8 — Python module imports & the project layout

### The error

```python
from apis.store import models
# ModuleNotFoundError: No module named 'apis.store'
```

### Why it broke

`apis/` is the **project root** — it's the directory `manage.py` lives in. It is **not itself an importable package**. The actual app package is `store/`, importable as just `store`.

```
apis/                    ← cwd when running manage.py (NOT a package)
├── manage.py
├── apis/                ← project package (settings/urls)
└── store/               ← app package (models/views/serializers)
```

Inside the `store` app, models can be imported either as:
- `from .models import Product` (relative — preferred for in-app imports)
- `from store.models import Product` (absolute — preferred for cross-app imports)

`from apis.store import ...` is wrong because there is no `apis` package containing `store` — `apis/` and `store/` are siblings, not parent/child.

---

## Things I asked for plain-English explanation on

Quick recap of the questions I stopped to ask, in case I forget the wording later:

1. **"Why did we pass `related_name` here?"** → it gives the reverse accessor on `Order` a clean name (`order.items.all()` instead of `order.orderitem_set.all()`) AND that name has to match the field name DRF uses for nested serialization.
2. **"What are these `cpython-314.pyc` files?"** → Python bytecode cache; `cpython` = the implementation, `314` = the version. Auto-generated, safe to delete, don't commit.
3. **"This is the format to write function name?"** (about `get_total_price`) → yes, `SerializerMethodField` requires `get_<field_name>`. Override with `method_name=` if you really need a different name.
4. **"Did I add it properly?"** (about `.gitignore`) → the file was right, but `.gitignore` doesn't untrack already-committed files; needed `git rm --cached`.

---

## Quick reference: errors I fixed today

| Error | Cause | Fix |
|---|---|---|
| `404 at /orders` | URL was actually `/products/orders/` due to `include()` prefix | Use the correct path (or restructure URLs) |
| `TypeError: ... unexpected keyword 'related_name'` | `related_name` on a `UUIDField` (and stale `.pyc`) | Remove the kwarg (only valid on relational fields); clear `__pycache__` |
| `Field name 'product' is not valid for model 'Order'` | `OrderItemSerializer.Meta.model = Order` | Change to `model = OrderItem` |
| `Field name 'item_subtotal' is not valid for model 'OrderItem'` | Listed in `fields` but not defined on model or serializer | Added `@property item_subtotal` on `OrderItem` |
| `ModuleNotFoundError: No module named 'apis.store'` | `from apis.store import models` — wrong layout assumption | Removed dead import (the relative `from .models` already covered it) |
| `404 at /products/info/` | URL pattern had a leading `/info/` | Remove leading slash → `info/` |
| `Class ProductInfoSerializer missing "Meta" attribute` | Used `ModelSerializer` for a non-model dict | Switch to `serializers.Serializer` (no `Meta` needed) |
| `.gitignore` not ignoring `.pyc` | Files were already tracked | `git rm -r --cached <paths>` |

---

## Key takeaways

1. **URL prefixes compose from outside in.** Patterns inside an `include()`d `urls.py` are relative — never start them with `/`.
2. **`related_name` is for relational fields only** (FK, M2M, OneToOne). Scalar fields reject it. The name you pick also becomes the nested-serializer field name in DRF.
3. **`.pyc` cache can lie** — when source fixes don't take effect, suspect stale `__pycache__/` and clear it.
4. **`.gitignore` only blocks untracked files.** Already-committed files need `git rm --cached`.
5. **`ModelSerializer` requires `Meta.model`** and validates `fields` against that model. For non-model data, use plain `Serializer`.
6. **Two ways to add computed fields**: `@property` on the model (intrinsic, reusable) or `SerializerMethodField` with `get_<field_name>` (serializer-specific, request-aware).
7. **`source='a.b.c'`** lets a serializer pull nested attributes into a flat JSON field without embedding a whole sub-serializer.
8. **Project root ≠ package.** `apis/` (where `manage.py` lives) isn't importable. The app `store/` is. Use `from .models` inside the app, `from store.models` from outside.
