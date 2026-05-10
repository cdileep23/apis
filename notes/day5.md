# Day 5

**Session 1** — stepped back from writing views to see the **landscape** of DRF view types: how function-based views, `APIView`, generic views, and ViewSets relate to each other, and where the boilerplate-vs-control tradeoff sits at each level. Also mapped out what's still ahead in DRF (auth, custom permissions, throttling, deeper serializers, schemas, testing) so the next sessions have direction.

No code in session 1 — pure conceptual scaffolding. The point was to make sure I can *place* anything new I encounter into the right slot of the mental model.

**Session 2** — put session 1 into practice. Replaced `OrderListView` + `UserOrderListView` (two generic views) with a single `OrderViewSet` wired up by a `DefaultRouter`. Added a custom `@action` for "my orders," a custom `OrderFilter` with a date cast, and built a writable `OrderCreateSerializer` that handles **nested item payloads** — which forced me to learn three new serializer patterns (nested-must-be-`ModelSerializer`, `transaction.atomic` for compound writes, and `required=False` + `pop(default)` semantics for partial updates).

---

## Concept 1 — Two axes, not one ladder

The classification I had in my head was wrong: I was thinking of FBV → APIView → Generic → ViewSet as a single ladder. It's actually **two independent decisions**:

```
Axis 1: How is the view defined?
   ├── Function-based  (@api_view decorator)
   └── Class-based     (inherit from a class)

Axis 2 (CBV only): How much does DRF do for you?
   ├── APIView       — write def get/post yourself
   ├── Generic view  — declare queryset + serializer_class, mixins do the rest
   └── ViewSet       — one class for both list-URL and detail-URL, router auto-wires
```

So "FBV vs CBV" answers **how the view is defined**; "APIView vs Generic vs ViewSet" answers **how much repetition DRF removes for you** — but only inside the CBV branch.

### Principle

> Don't picture one ladder — picture a fork (FBV / CBV), and then inside CBV a ladder of three rungs. Confusing the two axes is what made the family tree feel chaotic.

---

## Concept 2 — `APIView`: the foundation (recap)

Rawest CBV. You write the verb methods.

```python
class ProductInfoView(APIView):
    def get(self, request):
        ...
        return Response(...)
```

DRF gives you: `Request`, `Response`, content negotiation, auth, permissions, throttling. **You give it:** the verb handlers and what they return.

**Use when:** the response shape doesn't fit "CRUD on a single model." Aggregates (`{products, count, max_price}`), dashboards, RPC-style endpoints.

---

## Concept 3 — Generic views: declarative CRUD (recap with the mixin lens)

```python
class ProductListView(generics.ListCreateAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
```

The new framing for me: a generic view is just **`GenericAPIView` + one or more mixins**:

```
ListAPIView          = GenericAPIView + ListModelMixin
CreateAPIView        = GenericAPIView + CreateModelMixin
ListCreateAPIView    = GenericAPIView + ListModelMixin + CreateModelMixin
RetrieveUpdateDestroyAPIView
                     = GenericAPIView + Retrieve + Update + Destroy mixins
```

Each mixin contributes one **action method** (`list()`, `create()`, `retrieve()`, `update()`, `destroy()`). The generic view classes wire those action methods to HTTP verbs:

```python
class ListCreateAPIView(ListModelMixin, CreateModelMixin, GenericAPIView):
    def get(self, request, *a, **kw):  return self.list(request, *a, **kw)
    def post(self, request, *a, **kw): return self.create(request, *a, **kw)
```

This matters because **ViewSets reuse the exact same mixins** — they just bind them differently.

### Principle

> Mixins are the building blocks; generic views and ViewSets are two different ways of stacking them. The mixin's job (`list`, `create`, `retrieve`...) is the same regardless of which one consumes it.

---

## Concept 4 — ViewSets: bundling list-URL + detail-URL into one class

Generic views fix repetition **within one URL**. ViewSets fix repetition **across two related URLs** (collection + detail).

The pain point a ViewSet solves:

```python
# With generic views — TWO classes, TWO url entries, queryset/serializer declared TWICE
class ProductListView(generics.ListCreateAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

class ProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Product.objects.all()        # ← duplicated
    serializer_class = ProductSerializer    # ← duplicated

urlpatterns = [
    path('products/', ProductListView.as_view()),
    path('products/<int:pk>/', ProductDetailView.as_view()),
]
```

Replaced by one ViewSet:

```python
class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
```

And one router registration:

```python
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register('products', ProductViewSet)

urlpatterns = router.urls
# auto-generates BOTH /products/ AND /products/<pk>/
```

### Principle

> Generic views remove boilerplate **within** a URL. ViewSets remove boilerplate **across** the two URLs of a CRUD resource. They solve different layers of repetition.

---

## Concept 5 — The big conceptual shift: actions vs verbs

This is the part that bends your brain coming from generic views.

**Generic view world:** the method name *is* the HTTP verb.

```python
def get(self, request, ...):    # ← method name = verb
def post(self, request, ...):
```

**ViewSet world:** methods are named by **action**, not verb.

```python
def list(self, request):      # GET on /products/
def retrieve(self, request, pk): # GET on /products/<pk>/
def create(self, request):    # POST on /products/
def update(self, request, pk):   # PUT on /products/<pk>/
def partial_update(self, request, pk): # PATCH on /products/<pk>/
def destroy(self, request, pk):  # DELETE on /products/<pk>/
```

The router maps `(URL shape, verb) → action`:

| URL | Verb | Action called |
|---|---|---|
| `/products/` | GET | `list()` |
| `/products/` | POST | `create()` |
| `/products/<pk>/` | GET | `retrieve()` |
| `/products/<pk>/` | PUT | `update()` |
| `/products/<pk>/` | PATCH | `partial_update()` |
| `/products/<pk>/` | DELETE | `destroy()` |

Same verb (GET) maps to **different actions** depending on whether the URL has a `pk`. That dispatch logic is what `as_view({...})` and the router set up for you.

### Why the shift makes sense

In a generic view, a class corresponds to **one URL**, so "the GET handler" is unambiguous. In a ViewSet, a class corresponds to **multiple URLs**, so naming methods by verb would clash (which `get` is "list" and which is "retrieve"?). Naming by action removes the ambiguity.

### Principle

> Generic view = one URL → method named by verb. ViewSet = multiple URLs → method named by action. The router translates between (URL, verb) and action. Once you internalize that, ViewSets stop feeling magical — they're just a different naming scheme for the same mixin work.

---

## Concept 6 — The ViewSet family

The same kind of ladder as generics:

| Class | Provides |
|---|---|
| `ViewSet` | Bare. You write `list`, `retrieve`, etc. yourself (analogous to `APIView`). |
| `GenericViewSet` | Adds `queryset` / `serializer_class` machinery. No actions yet. |
| `ReadOnlyModelViewSet` | `list` + `retrieve` only. |
| `ModelViewSet` | Full CRUD: `list`, `retrieve`, `create`, `update`, `partial_update`, `destroy`. |

`ModelViewSet` is the ViewSet equivalent of "use `ListCreateAPIView` + `RetrieveUpdateDestroyAPIView` together at one resource." It's where most full-CRUD endpoints land.

`GenericViewSet` is the building-block: combine it with whatever mixins you actually want.

```python
class FeedViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                  viewsets.GenericViewSet):
    queryset = Post.objects.all()
    serializer_class = PostSerializer
    # → list + retrieve only, no create/update/destroy
```

### Principle

> `ModelViewSet` is the convenience class. `GenericViewSet` + mixins is the precision tool. Same relationship as `ListCreateAPIView` (convenience) vs `GenericAPIView + ListModelMixin + CreateModelMixin` (precision).

---

## Concept 7 — `@action`: where ViewSets really pay off

ViewSets aren't just sugar for "two views in one class." Their unique power is **adding endpoints beyond CRUD** without spinning up a new view class.

```python
class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

    @action(detail=False, methods=['get'])
    def featured(self, request):
        # GET /products/featured/
        qs = self.get_queryset().filter(is_featured=True)
        return Response(self.get_serializer(qs, many=True).data)

    @action(detail=True, methods=['post'])
    def restock(self, request, pk=None):
        # POST /products/<pk>/restock/
        product = self.get_object()
        product.stock += request.data['quantity']
        product.save()
        return Response({'stock': product.stock})
```

| Decorator | URL pattern | Use for |
|---|---|---|
| `@action(detail=False)` | `/products/<action>/` | Operations on the **collection** (search, featured, summary) |
| `@action(detail=True)` | `/products/<pk>/<action>/` | Operations on **one object** (publish, restock, archive) |

The router auto-registers these — no `path()` entries needed. To do the equivalent with generic views, each `@action` would have to be its own view class with its own URL.

### Principle

> ViewSets shine when a resource has CRUD **plus** ad-hoc operations. `@action` lets you keep them all in one class with shared queryset/serializer/permissions. That's where the boilerplate savings stop being theoretical.

---

## Concept 8 — Routers: URL wiring as a side effect of registration

Routers are what makes ViewSets feel different from generics in the URL conf:

```python
router = DefaultRouter()
router.register('products', ProductViewSet)
router.register('orders',   OrderViewSet)

urlpatterns = router.urls
```

That replaces:

```python
urlpatterns = [
    path('products/', ProductViewSet.as_view({'get': 'list', 'post': 'create'})),
    path('products/<int:pk>/', ProductViewSet.as_view({
        'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'
    })),
    path('products/featured/', ProductViewSet.as_view({'get': 'featured'})),
    path('products/<int:pk>/restock/', ProductViewSet.as_view({'post': 'restock'})),
    # ... and the same five lines again for OrderViewSet
]
```

The router walks the ViewSet class, finds the standard CRUD actions and any `@action`-decorated methods, and emits `path()` entries for each one with the right `as_view({...})` mapping.

### `DefaultRouter` vs `SimpleRouter`

| | `SimpleRouter` | `DefaultRouter` |
|---|---|---|
| URL prefix | none extra | adds a root view at `/` listing all registered resources |
| Format suffixes | no | yes (`/products/.json`, `/products/.api`) |
| Trailing slash | configurable | enforced |

Use `DefaultRouter` for browsable, public-facing APIs; `SimpleRouter` when you want minimal extras.

### Principle

> Routers reframe URL routing from **"declare each path"** to **"register each resource."** You hand them a ViewSet class; they figure out the URLs. That's why ViewSets and routers are inseparable in practice — the ViewSet abstraction only pays off when something automates the URL side too.

---

## Concept 9 — The decision tree, finalized

Now I can pick the right tool by asking three questions:

```
Q1: Does the response shape match CRUD-on-one-model?
   NO  → APIView. Custom shapes (aggregates, dashboards) live here.
   YES → continue.

Q2: Does the resource have BOTH a collection URL (/products/) AND
     a detail URL (/products/<pk>/)?
   NO  → Generic view. (e.g. just one of the two URLs.)
   YES → continue.

Q3: Does the resource have ad-hoc endpoints beyond CRUD
     (/products/featured/, /products/<pk>/restock/)?
   YES → ViewSet (definitely — `@action` is the killer feature).
   NO  → ViewSet is still the cleaner choice (one class, router-wired)
         but two generic views also work.
```

### Principle

> Pick the lowest-abstraction tool that doesn't force duplication. If two generic views would share a queryset/serializer/permissions block, that's the signal to lift up to a ViewSet. If your endpoint doesn't fit CRUD at all, drop down to `APIView`.

---

# Session 2 — putting it into practice

## Concept 10 — `ModelViewSet` + router, replacing two views with one

Before — two view classes, two URL entries, queryset/serializer declared twice:

```python
class OrderListView(generics.ListAPIView):
    queryset = Order.objects.prefetch_related('items__product')
    serializer_class = OrderSerializer

class UserOrderListView(generics.ListAPIView):
    queryset = Order.objects.prefetch_related('items__product')
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

# urls.py
path('orders/', OrderListView.as_view()),
path('my-orders/', UserOrderListView.as_view()),
```

After — one ViewSet, one router registration, full CRUD plus the "my orders" extra:

```python
# views.py
class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.prefetch_related('items__product')
    serializer_class = OrderSerializer
    permission_classes = [AllowAny]
    pagination_class = None
    filterset_class = OrderFilter
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    ordering_fields = ['created_at']

# urls.py
router = DefaultRouter()
router.register('orders', OrderViewSet, basename='order')
urlpatterns += router.urls
```

The router auto-emits `/orders/` (list, create) and `/orders/<pk>/` (retrieve, update, partial_update, destroy) — six endpoints from one class.

### `pagination_class = None`

Even though `REST_FRAMEWORK.DEFAULT_PAGINATION_CLASS` is set globally, assigning `None` to the view's `pagination_class` opts this view out. Useful when the response is naturally bounded (one user's recent orders) and the pagination envelope just adds noise.

### `basename='order'` — when is it required?

The router infers `basename` from `queryset.model._meta.object_name`. That works when `queryset = ...` is set as a class attribute. The moment you override `get_queryset()` (so the router can't find the model on the class), or your queryset uses dynamic logic, the router can't infer the name and you'd hit `AssertionError: 'basename' argument not specified`. Setting it explicitly always is the safe habit.

### Principle

> The router takes a ViewSet class and a URL prefix; it produces the full set of CRUD URLs (plus any `@action` URLs) automatically. The boilerplate that disappears is the URL conf, not the view body.

---

## Concept 11 — `@action` for non-CRUD endpoints

The "my orders" endpoint doesn't fit a CRUD slot — it's "list orders, but filter to the current user." `@action` lets it live on the same ViewSet:

```python
@action(detail=False, methods=['get'], url_path='user-orders',
        permission_classes=[IsAuthenticated])
def user_order(self, request):
    user = self.request.user
    orders = self.queryset.filter(user=user)
    serializer = self.get_serializer(orders, many=True)
    return Response(serializer.data)
```

URL: `GET /orders/user-orders/`.

### The three knobs that matter

| Knob | What it controls |
|---|---|
| `detail=False` | URL is `/orders/<action>/` — collection-scoped, no `pk` kwarg |
| `detail=True` | URL is `/orders/<pk>/<action>/` — object-scoped, gets `pk` kwarg |
| `methods=['get']` | Which HTTP verbs this action handles |
| `url_path='user-orders'` | Override the URL segment (default: method name with `_` → `-`) |
| `permission_classes=[...]` | Per-action permission override — independent of the ViewSet's defaults |

### Why per-action permissions are nicer than `get_permissions()`

The ViewSet itself uses `[AllowAny]`, but `user_order` requires login. With `@action(permission_classes=[IsAuthenticated])`, the override is **declared next to the action**, not buried in a per-verb conditional inside `get_permissions()`. Easier to read, easier to change.

### Principle

> `@action` is for "this resource has CRUD plus *additional* operations." Each extra operation gets its own URL and permissions, but shares the queryset, serializer, filter backends, and pagination of the parent ViewSet. That's where ViewSets stop being syntactic sugar over generic views.

---

## Concept 12 — Custom `FilterSet` with a derived field (the `__date` cast)

`Order.created_at` is a `DateTimeField`. Filtering by date alone (ignoring the time) needs a SQL-side cast — without it, `?created_at=2026-05-10` would compare against the full timestamp and almost always miss.

```python
class OrderFilter(django_filters.FilterSet):
    created_at = django_filters.DateFilter(field_name='created_at__date')
    class Meta:
        model = Order
        fields = {'status': ['exact'], 'created_at': ['gt','exact','lt']}
```

The explicit `DateFilter(field_name='created_at__date')` overrides what `Meta.fields` would auto-generate. `field_name='created_at__date'` is the ORM telling Postgres: cast `created_at` to a `DATE` before comparing. The cast happens **in SQL**, so the index on `created_at` can still be used (with a date-range rewrite) instead of fetching every row into Python.

### The shape of URLs this enables

| URL | SQL effect |
|---|---|
| `?created_at=2026-05-10` | `WHERE created_at::date = '2026-05-10'` |
| `?created_at__gt=2026-05-09` | `WHERE created_at > '2026-05-09'` |
| `?status=pending` | `WHERE status = 'pending'` |

### Principle

> When a column doesn't have the right shape for the URL param you want to expose, override the auto-generated filter with an explicit `Filter` class and use `field_name='col__lookup'` to push the transformation into SQL. Don't filter post-query in Python — you'll lose the index.

---

## Concept 13 — `get_queryset()` for per-request narrowing inside a ViewSet

Same hook as on generic views; same semantics. Inside a ViewSet, it gates **all** the standard CRUD actions plus any `@action` that calls `self.get_queryset()`:

```python
def get_queryset(self):
    queryset = super().get_queryset()
    if self.request.user.is_staff:
        return queryset.filter(user=self.request.user)
    return queryset
```

> **Flag for later:** the textbook "owner-only" pattern is the inverse — staff sees all, regular users see only their own. The current code does the opposite. Worth revisiting when permissions are tightened up in the auth session, especially since the ViewSet is currently `[AllowAny]`.

### Principle

> `get_queryset()` is the single chokepoint where row-level visibility is enforced. Putting it on the ViewSet narrows every read endpoint at once — list, retrieve, the `@action`s — without scattering `.filter(user=...)` across each handler.

---

## Concept 14 — Writable nested serializers (the part DRF doesn't do for you)

The `OrderCreateSerializer` accepts payloads like:

```json
{
  "user": 1, "status": "pending",
  "items": [
    {"product": 5, "quantity": 2},
    {"product": 7, "quantity": 1}
  ]
}
```

The structure looks like this:

```python
class OrderCreateSerializer(serializers.ModelSerializer):
    class OrderItemCreateSerializer(serializers.ModelSerializer):
        class Meta:
            model = OrderItem
            fields = ('product', 'quantity')

    items = OrderItemCreateSerializer(many=True, required=False)

    class Meta:
        model = Order
        fields = ('user', 'status', 'items')
        extra_kwargs = {'user': {'write_only': True}}
```

### The trap I fell into: nested serializer must be a `ModelSerializer`

I first wrote the inner class as `serializers.Serializer` (not `ModelSerializer`) but kept `Meta.model = OrderItem`. **Plain `Serializer` ignores `Meta`** — it only generates fields when the parent is a `ModelSerializer`. Result: the nested serializer had **zero fields**, validation silently passed everything, and `validated_data['items']` was a list of empty dicts. The bug was invisible until I tried to `OrderItem.objects.create(**item_data)` and got "missing required argument: product."

The fix: change the base class to `serializers.ModelSerializer`. Now `Meta` actually does its job.

### The other thing DRF doesn't do: write the nested data

`ModelSerializer.create()` defaults to `Model.objects.create(**validated_data)`. That fails the moment `validated_data` contains nested data — `Order.objects.create(items=[...])` errors because `Order` has no `items` argument. **Nested writes are a manual override:**

```python
def create(self, validated_data):
    items_data = validated_data.pop('items', [])
    with transaction.atomic():
        order = Order.objects.create(**validated_data)
        for item_data in items_data:
            OrderItem.objects.create(order=order, **item_data)
    return order
```

The pattern: pop the nested key out of `validated_data`, create the parent, then create each child explicitly with the parent attached.

### Principle

> Nested serializers do **validation** for free; they do **not** do **writing** for free. Override `create()` and `update()` whenever you have a nested writable field — split off the nested data, create the parent, then create the children manually.

---

## Concept 15 — `transaction.atomic` for compound writes

Whenever a single logical operation requires multiple DB writes (create order + create N items), wrap the whole thing in a transaction:

```python
from django.db import transaction

with transaction.atomic():
    order = Order.objects.create(**validated_data)
    for item_data in items_data:
        OrderItem.objects.create(order=order, **item_data)
```

If any single `OrderItem.objects.create` fails halfway through, **all earlier writes (including the order itself) roll back**. Without `atomic`, you'd be left with an `Order` with some items, or no items — partial state that breaks invariants.

### Why update needs it even more than create

Update first deletes existing items, then creates new ones:

```python
def update(self, instance, validated_data):
    items_data = validated_data.pop('items', None)
    with transaction.atomic():
        instance = super().update(instance, validated_data)
        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                OrderItem.objects.create(order=instance, **item_data)
    return instance
```

The delete happens *before* the recreate. If create fails in the middle, **the original items are gone**. The atomic block ensures: either both delete and recreate succeed, or neither happens — the DB is back to its pre-request state on failure.

### Principle

> Anytime a single endpoint does more than one DB write, wrap it in `transaction.atomic()`. The cost is one keyword; the alternative is partial failures that corrupt your data — and the corruption may not surface until much later.

---

## Concept 16 — `required=False` + `pop(default)` for partial-update semantics

For PATCH support, the client should be able to send a **partial** payload that omits `items` ("update status only, leave items alone"):

```python
items = OrderItemCreateSerializer(many=True, required=False)
```

Then in `update`:

```python
items_data = validated_data.pop('items', None)
if items_data is not None:
    instance.items.all().delete()
    for item_data in items_data:
        OrderItem.objects.create(order=instance, **item_data)
```

### The three states this expresses

| Client sent | `items_data` value | Result |
|---|---|---|
| `"items": [...]` (non-empty) | the list | Replace items with this list |
| `"items": []` | `[]` (empty list) | Delete all items |
| field omitted | `None` | Leave existing items unchanged |

The `is not None` check distinguishes "omitted" from "empty list." Without it, an empty list would be indistinguishable from omission, and you'd have no way to express "delete all items."

For `create`, the same `required=False` + default lets the field be omitted (creates an order with no items). I used `pop('items', [])` there because the loop is a no-op on an empty list — cleaner than guarding with a conditional.

### Principle

> `pop('items', None)` followed by `if items_data is not None:` lets the API express **three** states (set, empty, omitted). Flattening to two states throws away expressive power that PATCH needs to be useful.

---

## Concept 17 — `UserSerializer` as a read-only sidecar

```python
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('username', 'email', 'is_staff')
```

Three fields, all chosen for **what to show**, not "what's in the model." A serializer is a **public contract** — every field listed becomes part of the API surface area.

### What's deliberately missing

- `password` — never serializable, even with `write_only=True` (use a separate registration serializer for that).
- `id` / `pk` — usually omitted when `username` is the human-facing identifier; including both leaks an internal detail.
- `last_login`, `date_joined`, `groups`, `permissions` — Django auth internals, not API consumers' business.

### Why `is_staff` is included but read-only

It's useful for clients to know "is this user an admin" so the UI can render an admin badge. But the field must never be **writable** from the API — that would be a privilege escalation. `ModelSerializer` defaults to writable; for fields like `is_staff`, you'd use `extra_kwargs = {'is_staff': {'read_only': True}}` to lock it down explicitly. (TODO: when I wire this serializer into a write endpoint, add that lock.)

### Principle

> Treat every serializer's `fields` list as a **public contract**. Each field is something you commit to keeping stable; each writable field is a security decision. Default to listing fewer fields and adding more only when a client actually needs them.

---

## Roadmap forward — what's still ahead in DRF

Mapping out the territory so future sessions have direction.

### A. Things directly inside DRF

| Topic | What it gives me |
|---|---|
| **`@action` and routers** in practice | Refactor existing views to a ViewSet, see the wiring savings |
| **Authentication classes** — `Token`, JWT (SimpleJWT) | Real login flow; stateless auth for SPA/mobile |
| **Custom permissions** — `BasePermission`, `has_object_permission` | "Owner-only" access patterns (`IsOwnerOrReadOnly`) |
| **Throttling** — `AnonRateThrottle`, `UserRateThrottle` | Rate-limit clients |
| **Serializers, deeper** — nested, `SerializerMethodField`, `to_representation`, validators | Real-world serialization (the part where most bugs live) |
| **`HyperlinkedModelSerializer`** | URLs instead of bare IDs in responses |
| **Renderers / parsers** | JSON vs browsable API vs CSV; multipart for file upload |
| **Versioning** — `URLPathVersioning` etc. | Evolve API without breaking old clients |
| **Schema / OpenAPI** — `drf-spectacular` | Auto-generate Swagger docs |
| **Testing** — `APIClient`, `APITestCase` | Endpoint-level test coverage |

### B. Django-side companions

| Topic | Why it pairs with DRF |
|---|---|
| `select_related` (other half of N+1 fix) | FK / OneToOne joins |
| `F()` and `Q()` expressions | DB-side updates and complex OR queries |
| `annotate()` / `aggregate()` | Lift Python derivations into SQL |
| Signals | React to model changes |
| Custom managers / querysets | `Product.objects.in_stock()` reusable shortcuts |
| Caching (`@cache_page`, Redis) | Performance for read-heavy endpoints |
| Celery | Async/background tasks |
| Channels | WebSockets, real-time |

### C. Wider ecosystem (when DRF stops being enough)

- Async views (Django 4.1+) for I/O-heavy endpoints
- GraphQL (`graphene-django`, `strawberry`) when clients want field-level control
- Django Ninja — FastAPI-style alternative to DRF
- gRPC for internal service-to-service APIs

---

## Suggested next sessions

A reasonable order from where I am:

1. **ViewSets + routers + `@action`** — refactor `ProductListView` + `ProductDetailView` into one `ProductViewSet`, feel the difference firsthand.
2. **Authentication: `TokenAuthentication`, then JWT (SimpleJWT)** — the API only becomes "real" once it has login.
3. **Custom permissions** — write `IsOwnerOrReadOnly` for orders.
4. **Serializer depth** — nested `OrderItemSerializer` inside `OrderSerializer`, `SerializerMethodField`, validators.
5. **Throttling** — quick win, gives a feel for `REST_FRAMEWORK` settings layering.
6. **Testing with `APIClient`** — add tests for what already exists.
7. **`drf-spectacular`** — instant Swagger docs.
8. **Caching + Celery** — when performance/async work shows up.

---

## Key takeaways

1. **FBV vs CBV is one axis; APIView vs Generic vs ViewSet is a separate axis** that only applies inside CBV. Two decisions, not one ladder.
2. **`APIView` is the foundation** — you write the verb methods. Use for non-CRUD response shapes.
3. **Generic views = `GenericAPIView` + mixins.** The mixin contributes an action method (`list`, `create`, etc.); the generic view binds it to a verb (`get`, `post`).
4. **ViewSets reuse the same mixins**, but bind them by **action name**, not verb. The router handles `(URL, verb) → action` dispatch.
5. **Pick a generic view to fix repetition within one URL; pick a ViewSet to fix repetition across two related URLs.** Different layers of duplication.
6. **`@action` is where ViewSets stop being just sugar.** Custom endpoints (`/products/featured/`, `/products/<pk>/restock/`) live in the same class, share queryset/serializer/permissions, get auto-wired by the router.
7. **`ModelViewSet` is the convenience; `GenericViewSet + mixins` is the precision tool.** Same relationship as `ListCreateAPIView` vs raw `GenericAPIView + mixins`.
8. **Routers register resources, not paths.** `router.register('products', ProductViewSet)` emits all the `path()` entries — including `@action` ones — automatically.
9. **The decision tree:** custom shape → `APIView`. CRUD on one URL → generic. CRUD across two URLs (especially with extras) → ViewSet.
10. **What's left in DRF lives mostly off the request-handling layer** — auth, permissions, throttling, deeper serializers, schemas, testing. Those are the next sessions.
11. **`pagination_class = None`** opts a single view out of the project-wide `DEFAULT_PAGINATION_CLASS`. Use when the response is naturally bounded.
12. **`basename=` on `router.register` is required** the moment you override `get_queryset()` (the router can't infer the model). Always setting it is the safe habit.
13. **`@action(permission_classes=[...])`** declares the override **next to the action**. Cleaner than per-verb branching in `get_permissions()` for non-CRUD endpoints.
14. **For `DateTimeField` columns, `field_name='col__date'`** pushes the date cast into SQL so the index can still be used. Never filter post-query in Python.
15. **Nested serializers must be `ModelSerializer`** if you rely on `Meta.model = ...` to generate fields. Plain `Serializer` silently ignores `Meta`, leaving the nested class with zero fields and `validated_data` full of empty dicts.
16. **Nested serializers do validation, not writing.** Override `create()` and `update()`: pop nested data, create the parent, create children explicitly with the FK attached.
17. **Wrap multi-write operations in `transaction.atomic()`.** Especially update — delete-then-recreate without a transaction means a mid-loop failure leaves you with the original items gone and the new ones not yet created.
18. **`required=False` + `pop(field, None)` + `is not None` check** lets PATCH express three states: set / empty / omitted. Flattening to two throws away the expressive power that makes PATCH useful.
19. **A serializer's `fields` list is a public contract.** Each writable field is a security decision (`is_staff` writable = privilege escalation). Default to fewer fields; add more only when a client needs them.
