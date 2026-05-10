# Day 5

**Session 1** — stepped back from writing views to see the **landscape** of DRF view types: how function-based views, `APIView`, generic views, and ViewSets relate to each other, and where the boilerplate-vs-control tradeoff sits at each level. Also mapped out what's still ahead in DRF (auth, custom permissions, throttling, deeper serializers, schemas, testing) so the next sessions have direction.

No code today — pure conceptual scaffolding. The point was to make sure I can *place* anything new I encounter into the right slot of the mental model.

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
