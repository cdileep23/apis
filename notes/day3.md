# Day 3

**Session 1** — switched the API from function-based views to DRF's class-based generic views, learned how DRF resolves a single object behind the scenes, dropped in `django-silk` to actually *see* the SQL my views run, and used `prefetch_related` to fix the N+1 query problem. Also picked up the difference between filtering on a real DB column vs a Python `@property`.

**Session 2** — added write endpoints. Started with a standalone `CreateAPIView`, then collapsed list+create into a single `ListCreateAPIView` and detail+update+delete into `RetrieveUpdateDestroyAPIView`. Learned how `CreateAPIView` wires `POST → create()` internally via `CreateModelMixin`, and used `get_permissions()` to apply different permissions per HTTP verb (anyone can read, only admins can write).

---

## Concept 1 — Class-based views in DRF (generics)

### The shift

Yesterday everything was a `@api_view` function. Today the same endpoints became classes:

```python
# Before
@api_view(['GET'])
def product_list(request):
    products = Product.objects.all()
    serializer = ProductSerializer(products, many=True)
    return Response(serializer.data)

# After
class ProductListView(generics.ListAPIView):
    queryset = Product.objects.filter(stock__gt=0)
    serializer_class = ProductSerializer
```

The class version replaces ~5 lines of imperative code with **two declarative attributes**. Everything else (the GET handler, pagination hooks, filter hooks, the `Response`) is inherited.

### The generic views I used today

| Generic | What it does | I used it for |
|---|---|---|
| `ListAPIView` | GET → list of objects | `ProductListView`, `OrderListView`, `UserOrderListView` |
| `RetrieveAPIView` | GET → single object by pk | `ProductDetailView` |
| `APIView` | Bare class, you write `def get/post(...)` | `ProductInfoView` (custom shape, no model 1:1) |

### Wiring CBVs into URLs

CBVs need `.as_view()` because the URL resolver expects a **callable**, and a class itself isn't one in the way Django wants. `as_view()` returns a function that, when called with a request, instantiates the class fresh per-request and dispatches to the right method.

```python
path('', ProductListView.as_view(), name='product-list')
#                       ↑
#       NOT ProductListView — that would pass the class object,
#       which Django can't call as a view.
```

### When to drop down to plain `APIView`

`ProductInfoView` doesn't fit a generic — it returns a custom dict (`products`, `count`, `max_price`) that isn't a single queryset or instance:

```python
class ProductInfoView(APIView):
    def get(self, request):
        products = Product.objects.all()
        count = products.count()
        max_price = products.aggregate(max_price=Max('price'))['max_price']
        serializer = ProductInfoSerializer({
            'products': products, 'count': count, 'max_price': max_price
        })
        return Response(serializer.data)
```

Rule of thumb:

> Generic if your endpoint matches one of CRUD-on-a-model. `APIView` if the response shape is custom or aggregates across multiple models.

---

## Concept 2 — How `RetrieveAPIView` actually finds one object

I only declared `queryset = Product.objects.all()` and `serializer_class = ProductSerializer`. So how does it know to return *one* product when the URL has an ID?

### The chain

```
GET /products/5/
   │
   ▼
URL: path('<int:pk>/', ProductDetailView.as_view())
   → captures pk=5 as a URL kwarg → self.kwargs = {'pk': 5}
   │
   ▼
RetrieveAPIView.get()  →  RetrieveModelMixin.retrieve()
   │
   ▼
get_object():
    queryset = self.get_queryset()              # Product.objects.all()
    filter_kwargs = {self.lookup_field: self.kwargs[self.lookup_url_kwarg or self.lookup_field]}
    # → {'pk': 5}
    obj = get_object_or_404(queryset, **filter_kwargs)
    # → SELECT * FROM store_product WHERE id = 5
    return obj
   │
   ▼
serializer = self.get_serializer(obj)
return Response(serializer.data)
```

### The two attributes that drive the lookup

`GenericAPIView` defines defaults so I don't have to:

| Attribute | Default | What it controls |
|---|---|---|
| `lookup_field` | `'pk'` | Which **model field** to filter on |
| `lookup_url_kwarg` | `None` (falls back to `lookup_field`) | Which **URL kwarg** to read from `self.kwargs` |

So out of the box: read `pk` from the URL, filter the queryset by `pk=<that value>`. To use a different scheme:

```python
class ProductDetailView(generics.RetrieveAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    lookup_field = 'slug'             # filter on Product.slug
    lookup_url_kwarg = 'product_slug' # read from /products/<product_slug>/
```

### Principle

> CBVs look magical, but they're just inheritance. Anything you can't see in your subclass is somewhere up the MRO chain — `get_object`, `get_queryset`, `get_serializer`, `dispatch`. They're all overridable hooks.

---

## Concept 3 — `get_queryset()` override for per-request filtering

`queryset = ...` is fine when the queryset is the same for every request. But "list **my** orders" depends on who's logged in — so I needed the queryset to vary per request.

```python
class UserOrderListView(generics.ListAPIView):
    queryset = Order.objects.prefetch_related('items__product')
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return self.queryset.filter(user=user)
```

### Why override `get_queryset` instead of mutating `queryset`

The class attribute `queryset` is **shared across all instances of the class** (and across all requests). If I tried to do `self.queryset = self.queryset.filter(...)` in some method, I'd be filtering the same QuerySet object every request, eventually compounding filters.

`get_queryset` is the correct hook because:
- DRF calls it once per request inside `get_object` / `list()`.
- I can read `self.request`, `self.kwargs`, `self.action` (for ViewSets) — all request-scoped state.
- `self.queryset` is treated as a **template** I derive from with `.filter(...)`, never mutated in place.

### Principle

> `queryset = ...` is the static base. `get_queryset(self)` is the dynamic, per-request derivation. Override the method, never mutate the attribute.

---

## Concept 4 — `permission_classes` and `IsAuthenticated`

```python
permission_classes = [IsAuthenticated]
```

This is a **list** because permissions stack with AND semantics — every class in the list must return `True` for the request to proceed. DRF runs them in `dispatch()` before your view code ever sees the request.

`IsAuthenticated` returns `True` only if `request.user.is_authenticated` is True (i.e., a logged-in user, not `AnonymousUser`). Failing it returns HTTP 401.

Other common ones: `AllowAny` (default), `IsAdminUser`, `IsAuthenticatedOrReadOnly` (anyone reads, only authed users write).

### Principle

> Permissions are a precondition layer. They run before the view, decide pass/fail, and never look at response data. Authorization decisions that depend on the *object being returned* belong in `has_object_permission` (object-level perms), not list-level perms.

---

## Concept 5 — The N+1 query problem and `prefetch_related`

### The problem

Without prefetching, serializing a list of orders triggers an explosion of queries:

```
1 query   → SELECT * FROM store_order
N queries → for each order: SELECT * FROM store_orderitem WHERE order_id = ?
N×M       → for each item: SELECT * FROM store_product WHERE id = ?
```

10 orders with 5 items each = **61 queries**. Linear in the data — fine in dev, lethal in prod.

### The fix

```python
queryset = Order.objects.prefetch_related('items__product')
```

Django runs **3 queries total**, regardless of how many orders:

```sql
SELECT * FROM store_order;
SELECT * FROM store_orderitem WHERE order_id IN (...);
SELECT * FROM store_product   WHERE id       IN (...);
```

It then stitches the rows together in Python and caches the related objects on each instance, so the serializer's `order.items.all()` and `item.product` accesses hit the cache instead of the DB.

### `prefetch_related` vs `select_related`

| | `select_related` | `prefetch_related` |
|---|---|---|
| Mechanism | SQL `JOIN` (one query) | Separate query per relation, joined in Python |
| Use for | `ForeignKey`, `OneToOne` (single related row) | `ManyToMany`, reverse `ForeignKey` (many related rows) |
| Why not always JOIN? | A JOIN to a many-side multiplies rows — `prefetch_related` avoids that |

`Order → items` is a reverse FK (many items per order), so `prefetch_related` is the right tool. `JOIN`ing would multiply rows by the number of items.

### The `__` traversal notation

```
prefetch_related('items__product')
                   │       │
                   │       └── from each OrderItem, follow `product` (FK → Product)
                   └── from Order, follow `items` (reverse FK via related_name='items')
```

Each `__` is **one hop across a relationship**. The same notation shows up everywhere in the ORM:

```python
Order.objects.filter(items__product__price__gt=100)
#                    └─hop─┘ └─hop─┘ └field┘ └lookup┘
# "orders containing an item whose product costs > 100"
```

---

## Concept 6 — Filtering on a `@property` doesn't work (and why)

### The error

```python
queryset = Product.objects.filter(in_stock=True)
# FieldError: Cannot resolve keyword 'in_stock' into field.
# Choices are: description, id, image, name, orderitem, orders, price, stock
```

### Why

`in_stock` is a Python `@property` on the model:

```python
@property
def in_stock(self):
    return self.stock > 0
```

It runs **in Python, after a row is loaded**. `.filter(...)` translates into SQL `WHERE`, and SQL can only reference real columns — it has no way to execute Python code on the database side. Django lists the actual columns in the error message to make this concrete.

### The fix

Filter on the underlying column with the `__gt` ("greater than") lookup:

```python
queryset = Product.objects.filter(stock__gt=0)
```

This generates `WHERE stock > 0` — same semantics as the property, but expressed in SQL.

### When you really do want to filter "on the property"

If the computation were complex and reused, you'd express it in SQL via `annotate()`:

```python
from django.db.models import Case, When, BooleanField, Value

Product.objects.annotate(
    in_stock=Case(
        When(stock__gt=0, then=Value(True)),
        default=Value(False),
        output_field=BooleanField(),
    )
).filter(in_stock=True)
```

The annotation is computed **in SQL**, so `.filter()` can reference it.

### Principle

> `.filter()` operates in SQL. `@property` operates in Python. The bridge is `annotate()` — it lifts a Python-style derivation into a SQL expression Django can filter on.

---

## Concept 7 — `django-silk`: actually seeing the queries

Reading "N+1 problem" in docs is one thing; watching Silk show 60 queries on a single endpoint is another.

### Setup (the three things that need to line up)

```python
# settings.py
INSTALLED_APPS = [..., 'silk']
MIDDLEWARE     = [..., 'silk.middleware.SilkyMiddleware']

# project urls.py
path('silk/', include('silk.urls', namespace='silk'))
```

After `python manage.py migrate`, hit any endpoint, then visit `/silk/` to see request timings, the SQL each request ran, and the call sites that triggered each query.

### The error I hit

```
ImportError: Module "silk.middleware" does not define a "SilkMiddleware" attribute/class
AttributeError: module 'silk.middleware' has no attribute 'SilkMiddleware'.
                Did you mean: 'SilkyMiddleware'?
```

I'd written `SilkMiddleware`. The actual class name is `SilkyMiddleware` (Silk → "silky"). Django's helpful "Did you mean…?" pointed straight at it.

### Why it's a middleware

A middleware sits in the request/response chain and can observe **every** request. Silk uses that position to (1) record start/end timestamps, (2) hook into Django's DB cursor to capture each SQL query, (3) attach all of it to a per-request record viewable in the dashboard. Code-level instrumentation (decorators, profilers) can't do this without you adding it to every view.

### Principle

> Middleware = the request lifecycle's universal observation point. Anything that should apply to "every request" with zero per-view changes — auth, logging, profiling, CORS, response compression — is a middleware.

---

## Concept 8 — Admin inlines for related models

Editing an `Order` and its `OrderItem`s on **separate** admin pages is annoying. `TabularInline` embeds the child rows directly in the parent's edit page.

```python
# admin.py
from django.contrib import admin
from .models import Order, OrderItem

class OrderItemInline(admin.TabularInline):
    model = OrderItem

class OrderAdmin(admin.ModelAdmin):
    inlines = [OrderItemInline]

admin.site.register(Order, OrderAdmin)
```

### How Django knows how to wire them

`OrderItem` already has `order = ForeignKey(Order, related_name='items')`. The admin uses that FK to:
1. Discover the relationship direction (Order → many OrderItems).
2. Render a table of OrderItem rows on the Order detail page, with an "Add another OrderItem" row at the bottom.
3. Save the children with the right `order_id` automatically.

`TabularInline` renders rows compactly (one item per table row). `StackedInline` is the alternative — each item gets a full form block, useful when there are many fields.

### Principle

> The admin's inline machinery is driven entirely by the existing FK. You don't tell the admin how the relationship works — it reads it off the model.

---

# Session 2 — write endpoints, combined generics, per-method permissions

## Concept 9 — `CreateAPIView` and what `POST` really does

A standalone create endpoint:

```python
class ProductCreateView(generics.CreateAPIView):
    serializer_class = ProductSerializer
```

That's it. No `queryset` needed (you're not reading anything), only a serializer. So what's actually happening when a POST hits this view?

### The class hierarchy

```
CreateAPIView
  └── CreateModelMixin + GenericAPIView
            └── APIView
                  └── django.views.View
```

`CreateAPIView` itself is tiny — it just binds **POST → `self.create()`**:

```python
class CreateAPIView(mixins.CreateModelMixin, GenericAPIView):
    def post(self, request, *args, **kwargs):
        return self.create(request, *args, **kwargs)
```

Any verb other than POST returns `405 Method Not Allowed`.

### Request lifecycle for `POST /products/create/`

1. URL resolver → `ProductCreateView.as_view()(request)`.
2. `APIView.dispatch()`:
   - wraps the Django `HttpRequest` in a DRF `Request` (gives `.data`, content negotiation, auth)
   - runs `perform_authentication` → `check_permissions` → `check_throttles`
   - dispatches the verb → `self.post`
3. `post()` calls `self.create(request, ...)` from `CreateModelMixin`:

   ```python
   def create(self, request, *args, **kwargs):
       serializer = self.get_serializer(data=request.data)
       serializer.is_valid(raise_exception=True)
       self.perform_create(serializer)
       headers = self.get_success_headers(serializer.data)
       return Response(serializer.data, status=201, headers=headers)
   ```
4. `get_serializer()` reads `self.serializer_class` and instantiates it with `data=request.data`.
5. `is_valid(raise_exception=True)` — failures bubble up as `ValidationError`, DRF's exception handler turns them into a `400`.
6. `perform_create(serializer)` calls `serializer.save()` → `ProductSerializer.create(validated_data)` → `Product.objects.create(**validated_data)`.
7. Response is rendered as JSON, returned with `201 Created`.

### The `model = ...` gotcha

```python
class ProductCreateView(generics.CreateAPIView):
    model = Product             # ← ignored by DRF
    serializer_class = ProductSerializer
```

DRF's generics use `queryset` / `get_queryset()`, **not** `model`. The `model` attribute is a holdover from older Django CBVs and does nothing here. The model is reached via the serializer's `Meta.model`.

### Hooks worth knowing

| Hook | When to override |
|---|---|
| `get_serializer_class()` | Different serializer for read vs write (e.g. write-only fields) |
| `perform_create(serializer)` | Inject request-scoped data — `serializer.save(user=self.request.user)` |
| `get_serializer_context()` | Pass extra info into the serializer |
| `create(request, ...)` | Last-resort: full control of the flow (logging, custom response shape) |

### Principle

> The "magic" of a generic view is just two layers: a verb-handler method (`post`) on the generic class, and a mixin method (`create`) that does the work. To customize, override the smallest hook — `perform_create` for what to save, `get_serializer_class` for how to validate, `create` only when neither is enough.

---

## Concept 10 — Combining generics: `ListCreateAPIView`, `RetrieveUpdateDestroyAPIView`

`ProductListView` was a `ListAPIView` (read-only). Adding a separate `ProductCreateView` for POST means two URL routes for the same resource. DRF ships combined generics that fold both verbs into one view at one URL:

```python
class ProductListView(generics.ListCreateAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    # GET  /products/  → list
    # POST /products/  → create
```

```python
class ProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    # GET    /products/<pk>/ → retrieve
    # PUT    /products/<pk>/ → update      (full replace)
    # PATCH  /products/<pk>/ → partial_update
    # DELETE /products/<pk>/ → destroy
```

### How they're built

Each combined view is just a stack of mixins:

```python
class ListCreateAPIView(ListModelMixin, CreateModelMixin, GenericAPIView):
    def get(self, request, *a, **kw):  return self.list(request, *a, **kw)
    def post(self, request, *a, **kw): return self.create(request, *a, **kw)

class RetrieveUpdateDestroyAPIView(RetrieveModelMixin, UpdateModelMixin,
                                   DestroyModelMixin, GenericAPIView):
    def get(...):    return self.retrieve(...)
    def put(...):    return self.update(...)
    def patch(...):  return self.partial_update(...)
    def delete(...): return self.destroy(...)
```

So the "combined" generic is purely a matter of which mixins are bolted onto `GenericAPIView` and which verbs are wired up.

### The full ladder

| Generic | Verbs | Mixins |
|---|---|---|
| `ListAPIView` | GET (list) | List |
| `CreateAPIView` | POST | Create |
| `RetrieveAPIView` | GET (one) | Retrieve |
| `UpdateAPIView` | PUT, PATCH | Update |
| `DestroyAPIView` | DELETE | Destroy |
| `ListCreateAPIView` | GET, POST | List + Create |
| `RetrieveUpdateAPIView` | GET, PUT, PATCH | Retrieve + Update |
| `RetrieveDestroyAPIView` | GET, DELETE | Retrieve + Destroy |
| `RetrieveUpdateDestroyAPIView` | GET, PUT, PATCH, DELETE | Retrieve + Update + Destroy |

### Principle

> Pick the combined generic that matches the URL's verbs, not one generic per verb. `/products/` serves list+create at one path; `/products/<pk>/` serves retrieve+update+delete at another. Two routes, two views, full CRUD.

---

## Concept 11 — `get_permissions()` for per-method permissions

`permission_classes = [...]` applies the **same** permissions to every verb the view handles. But on a `ListCreateAPIView`, I want anyone (even anonymous) to read, and only admins to write. That's per-verb logic, so I override `get_permissions`:

```python
class ProductListView(generics.ListCreateAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

    def get_permissions(self):
        self.permission_classes = [AllowAny]
        if self.request.method == 'POST':
            self.permission_classes = [IsAdminUser]
        return super().get_permissions()
```

```python
class ProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

    def get_permissions(self):
        self.permission_classes = [AllowAny]
        if self.request.method in ['PUT', 'PATCH', 'DELETE']:
            self.permission_classes = [IsAdminUser]
        return super().get_permissions()
```

### How DRF actually uses it

Inside `APIView.dispatch()` → `initial(request)` → `check_permissions(request)`, DRF calls `self.get_permissions()` to get the **list of permission instances** to enforce on this request:

```python
# default in APIView
def get_permissions(self):
    return [permission() for permission in self.permission_classes]
```

It just instantiates the class-level list. Overriding the method gives you a chance to **mutate `self.permission_classes` based on `self.request`** before the parent instantiates them.

### Step-by-step on a request

1. Request arrives → `dispatch()` runs.
2. `check_permissions(request)` is called.
3. It calls `self.get_permissions()` — my version.
4. Default is set: `self.permission_classes = [AllowAny]`.
5. If the verb is a write verb, override to `[IsAdminUser]`.
6. `super().get_permissions()` returns instantiated `[AllowAny()]` or `[IsAdminUser()]`.
7. DRF iterates them, calling `.has_permission(request, view)`. Any `False` → `403` (or `401` if unauthenticated).

### Why mutating `self.permission_classes` is safe here

Class attributes are usually shared across instances, but `as_view()` instantiates the view **fresh per request**, so writing to `self.permission_classes` doesn't leak across requests. Still, the cleaner version skips the mutation and just returns instances directly:

```python
def get_permissions(self):
    if self.request.method in ['PUT', 'PATCH', 'DELETE']:
        return [IsAdminUser()]
    return [AllowAny()]
```

Same behavior, no `super()` call, no instance state being rewritten.

### Principle

> `permission_classes` is the static default; `get_permissions()` is the per-request override. Use the method whenever the same view handles multiple verbs with different access rules — read open, write restricted is the canonical case.

---

## Quick reference: errors I fixed today

| Error | Cause | Fix |
|---|---|---|
| `AttributeError: module 'silk.middleware' has no attribute 'SilkMiddleware'` | Wrong class name | Use `SilkyMiddleware` |
| `FieldError: Cannot resolve keyword 'in_stock'` | Filtering on a `@property`, not a DB field | `.filter(stock__gt=0)` instead of `.filter(in_stock=True)` |

---

## Key takeaways

1. **CBV generics replace boilerplate with declaration.** `ListAPIView`, `RetrieveAPIView` give you the GET handler; you only declare `queryset` and `serializer_class`.
2. **`as_view()` is mandatory** when wiring CBVs into URLs — Django's resolver needs a callable, not a class.
3. **`RetrieveAPIView` resolves the object** via `get_object()` → `lookup_field` (model side) + `lookup_url_kwarg` (URL side) → `queryset.get(...)` → `get_object_or_404`.
4. **Override `get_queryset(self)`, never mutate `self.queryset`.** Class attributes are shared; the method is per-request.
5. **`permission_classes` runs before the view.** Each class's `has_permission` is a precondition; failures short-circuit with 401/403.
6. **`prefetch_related` solves N+1** for many-side relations; `select_related` does the same for FK/OneToOne via JOIN. The `__` notation chains hops (`items__product`).
7. **You can't filter on a `@property`.** SQL doesn't run Python — filter on the underlying column or use `annotate()` to lift the derivation into SQL.
8. **Silk shows the actual SQL** every request runs. Always wire it up early — N+1 is invisible until you can see it.
9. **`TabularInline` reads the FK** to embed child editing in the parent's admin page. Zero extra config.
10. **`CreateAPIView` is just `POST → create()` from `CreateModelMixin`.** The real work — validate, save, return 201 — is in the mixin's `create()`. Override `perform_create` to inject request data, `get_serializer_class` for read/write splits, `create` only for full custom flow.
11. **`model = ...` is ignored by DRF generics.** They use `queryset` / `get_queryset()`. The model is reached via the serializer's `Meta.model`.
12. **Combine CRUD on a single URL with the combined generics.** `ListCreateAPIView` for the collection route, `RetrieveUpdateDestroyAPIView` for the detail route. Two views = full CRUD.
13. **Per-verb permissions go in `get_permissions()`.** `permission_classes` is the static default; the method overrides per-request. Canonical pattern: `AllowAny` for read verbs, `IsAdminUser` for write verbs.
