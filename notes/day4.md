# Day 4

**Session 1** — turned `ProductListView` into a queryable list endpoint. Wired up `django-filter` for declarative field filtering, `SearchFilter` for free-text search across columns, `OrderingFilter` for URL-driven sorting, a custom `InStockFilterBackend` to always hide out-of-stock items, and `PageNumberPagination` so big collections don't dump everything at once. Also fixed two import-time errors that bricked `runserver` — a missing comma in `INSTALLED_APPS` and an illegal relative import.

---

## Concept 1 — The `filter_backends` pipeline

The mental model that makes everything else click: DRF doesn't have one "filter system." It has a **list of filter backends**, each of which takes a queryset and returns a (usually narrower) queryset. They run in order, threading the queryset through.

```python
class ProductListView(generics.ListCreateAPIView):
    queryset = Product.objects.order_by('name')
    filter_backends = [
        DjangoFilterBackend,    # ?name__icontains=phone&price__lt=500
        filters.SearchFilter,   # ?search=phone
        filters.OrderingFilter, # ?ordering=-price
        InStockFilterBackend,   # always: stock > 0
    ]
```

### What `list()` actually does

```python
# inside ListModelMixin.list()
queryset = self.filter_queryset(self.get_queryset())
# self.filter_queryset runs every backend:
def filter_queryset(self, queryset):
    for backend in list(self.filter_backends):
        queryset = backend().filter_queryset(self.request, queryset, self)
    return queryset
```

Each backend gets `(request, queryset, view)`, reads whatever it needs off `request.query_params`, and returns the filtered queryset. The output of one becomes the input of the next.

### Principle

> A "filter backend" is just a callable that narrows a queryset based on the request. The whole chain — django-filter, search, ordering, my custom in-stock filter — is the same shape, applied in sequence. There's no special machinery; it's a pipeline of functions.

---

## Concept 2 — `django-filter` and declarative `FilterSet`

`DjangoFilterBackend` reads URL params and translates them into `.filter(...)` calls. Which params it accepts is declared on a `FilterSet`:

```python
# apis/filters.py
import django_filters
from store.models import Product

class ProductFilter(django_filters.FilterSet):
    class Meta:
        model = Product
        fields = {
            'name':  ['iexact', 'icontains'],
            'price': ['exact', 'gt', 'lt', 'range'],
        }
```

Wired onto the view:

```python
filterset_class = ProductFilter
filter_backends = [DjangoFilterBackend, ...]
```

### What URLs this enables

| URL | Generated SQL |
|---|---|
| `?name__icontains=phone` | `WHERE name ILIKE '%phone%'` |
| `?name__iexact=Phone` | `WHERE LOWER(name) = LOWER('Phone')` |
| `?price__lt=500` | `WHERE price < 500` |
| `?price__gt=100&price__lt=500` | `WHERE price > 100 AND price < 500` |
| `?price__range=100,500` | `WHERE price BETWEEN 100 AND 500` |

Each entry in the `fields` dict becomes a URL param of the form `<field>__<lookup>`. The lookups are the standard ORM lookups — `iexact`, `icontains`, `gt`, `lt`, `range`, `in`, `startswith`, etc.

### Two ways to declare `fields`

```python
# Shorthand: every field gets exact-match lookup only
fields = ['name', 'price']
# → ?name=Phone, ?price=499  (no ?price__lt=...)

# Dict form: per-field lookups
fields = {'name': ['iexact', 'icontains'], 'price': ['gt', 'lt']}
```

Use the dict form whenever you want range/contains lookups — the list form is exact-match only.

### Principle

> `FilterSet` is the **whitelist** of what URL params your endpoint accepts. Anything not declared is silently ignored — that's a feature, not a bug. It prevents arbitrary filter expressions from leaking into your queryset.

---

## Concept 3 — `SearchFilter`: free-text search across columns

`DjangoFilterBackend` is column-precise (`?name__icontains=...`). `SearchFilter` is the opposite — one `?search=` param, fuzzy-matched across multiple fields:

```python
filter_backends = [..., filters.SearchFilter]
search_fields = ['=name', 'description']
```

`?search=phone` runs:

```sql
WHERE name = 'phone' OR description ILIKE '%phone%'
```

### The prefix characters

`search_fields` entries can be prefixed to control the lookup:

| Prefix | Lookup | Example |
|---|---|---|
| (none) | `icontains` (case-insensitive substring) | `'description'` → `description ILIKE '%term%'` |
| `^` | `istartswith` | `'^name'` → `name ILIKE 'term%'` |
| `=` | `iexact` (exact, case-insensitive) | `'=name'` → `LOWER(name) = LOWER('term')` |
| `@` | full-text search (Postgres only) | `'@body'` → `to_tsvector(body) @@ to_tsquery(...)` |
| `$` | regex | `'$slug'` → `slug ~* 'term'` |

I used `'=name'` for exact name match and `'description'` for substring — so `?search=phone` finds products literally named "phone" *or* whose description mentions phones.

### `SearchFilter` vs `FilterSet`

| | `SearchFilter` | `FilterSet` |
|---|---|---|
| URL shape | `?search=term` | `?name__icontains=term&price__lt=500` |
| Number of fields | One query, many fields (OR'd) | One param per field/lookup |
| Use case | "global search bar" | "advanced filters" UI |

They compose. `?search=phone&price__lt=500` runs both.

### Principle

> `SearchFilter` is the search-bar; `FilterSet` is the column-filters panel. Different UX, different SQL shape — and they stack because they're independent backends in the pipeline.

---

## Concept 4 — `OrderingFilter`: URL-driven sorting

```python
filter_backends = [..., filters.OrderingFilter]
ordering_fields = ['price', 'name']
```

| URL | SQL |
|---|---|
| `?ordering=price` | `ORDER BY price ASC` |
| `?ordering=-price` | `ORDER BY price DESC` |
| `?ordering=price,name` | `ORDER BY price ASC, name ASC` |
| `?ordering=-price,name` | `ORDER BY price DESC, name ASC` |

The `-` prefix flips to descending. Comma chains tiebreakers.

### Why `ordering_fields` is required

It's a whitelist. Without it, clients could pass `?ordering=secret_field` and infer column existence — or worse, sort on a column that's expensive to sort without an index. Declaring `ordering_fields = ['price', 'name']` rejects anything else with a 400.

### Default ordering

The base `queryset` already has `.order_by('name')`, so `?ordering=...` *overrides* it per-request. If no `?ordering=` is passed, the queryset's default applies. There's also `ordering = 'price'` on the view as a class-level fallback that beats the queryset's `.order_by()`.

### Principle

> Ordering is request-scoped, but the **set of allowed orderings is view-scoped** (the whitelist). Always declare `ordering_fields` — it's the difference between a controlled API and a leaky one.

---

## Concept 5 — Custom filter backend: `InStockFilterBackend`

Not every filter needs to be URL-driven. Some are policy: "this endpoint never returns out-of-stock products, period." That's a custom backend:

```python
# apis/filters.py
from rest_framework import filters

class InStockFilterBackend(filters.BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        return queryset.filter(stock__gt=0)
```

Plugged into the view's chain:

```python
filter_backends = [DjangoFilterBackend, filters.SearchFilter,
                   filters.OrderingFilter, InStockFilterBackend]
```

### Why this is the right place for it

I could've put `.filter(stock__gt=0)` directly on the `queryset = ...` line. But:

- **As a backend**, it's reusable — drop the same class onto any view that needs in-stock-only.
- **It runs after** the user's filters, so `?price__lt=500` and `?search=phone` still apply. It just adds the additional `stock > 0` clause at the end.
- **It separates policy from data**. The base queryset says "all products"; the backend says "but never show OOS on this endpoint." That distinction matters when the same model is used by an admin view that *should* see OOS items.

### When to use a custom backend vs `get_queryset()`

| Use a custom backend | Use `get_queryset()` |
|---|---|
| Cross-cutting rule reused across views | One-off, view-specific filter |
| Wants to compose with other backends | Wants final say over the queryset |
| Stateless w.r.t. the view | Needs `self.kwargs`, `self.request.user`, etc. |

`InStockFilterBackend` is cross-cutting — any view selling products to customers should hide OOS. So it's a backend, not a `get_queryset` override.

### Principle

> A custom `BaseFilterBackend` is the cleanest way to express *policy filters* — rules that apply regardless of the request. They compose with URL-driven backends and live separately from view code.

---

## Concept 6 — Pagination: chunking the response

Without pagination, `GET /products/` returns the entire table. Fine with 12 rows; ruinous with 12 million. DRF ships pagination as a separate, pluggable layer.

### Per-view: `PageNumberPagination`

```python
from rest_framework.pagination import PageNumberPagination

class ProductListView(generics.ListCreateAPIView):
    ...
    pagination_class = PageNumberPagination
    pagination_class.page_size = 5
```

| URL | Behavior |
|---|---|
| `?page=1` | first 5 rows |
| `?page=2` | next 5 rows |
| `?page=3` | next 5 rows, etc. |

The response wraps the list in a metadata envelope:

```json
{
  "count": 42,
  "next": "http://.../products/?page=3",
  "previous": "http://.../products/?page=1",
  "results": [ ... 5 products ... ]
}
```

Clients page by following `next` until it's `null`.

### Global default: `LimitOffsetPagination`

In `settings.py`:

```python
REST_FRAMEWORK = {
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 100,
}
```

This sets a project-wide default. Any view that doesn't set its own `pagination_class` paginates with `LimitOffsetPagination`, page size 100. URLs look like `?limit=10&offset=20`.

### `PageNumberPagination` vs `LimitOffsetPagination` vs `CursorPagination`

| | URL shape | Best for |
|---|---|---|
| `PageNumberPagination` | `?page=N` | Stable, finite collections; UI with page links |
| `LimitOffsetPagination` | `?limit=L&offset=O` | Arbitrary windows; API consumers that want "skip the first 200" |
| `CursorPagination` | `?cursor=...` (opaque) | Large, append-only feeds; avoids skipping problems on inserts |

`PageNumberPagination` is fine for products. For an event log where rows get inserted constantly, `CursorPagination` is the right answer — page numbers shift when new rows arrive.

### The gotcha — `pagination_class.page_size = 5` mutates the class

```python
pagination_class = PageNumberPagination
pagination_class.page_size = 5   # ← mutates the class itself, not just this view
```

This sets `page_size` on the `PageNumberPagination` class, which is shared across **every** view that uses it. If two views both did this with different sizes, the second one would silently change the first. The clean version is to subclass:

```python
class FivePerPage(PageNumberPagination):
    page_size = 5

class ProductListView(...):
    pagination_class = FivePerPage
```

Same behavior, no shared mutation, no leak across views.

### Principle

> Pagination is a separate layer from filtering — first the backends narrow the queryset, *then* the paginator slices it. Set a project-wide default in `REST_FRAMEWORK`, override per-view only when the page size or strategy genuinely differs.

---

## Concept 7 — Where to put `filters.py`: relative imports and package boundaries

I hit `ImportError: attempted relative import beyond top-level package` because `views.py` had:

```python
from ..apis.filters import ProductFilter   # ← bad
```

### Why it failed

The directory structure:

```
apis/                  ← outer dir (manage.py here, sys.path root)
├── manage.py
├── apis/              ← project package (settings.py, urls.py, filters.py)
└── store/             ← app package (models.py, views.py)
```

`store` and `apis` (the inner one) are **both top-level packages** — siblings under `sys.path`. From `store/views.py`, going up one level (`..`) would mean leaving the `store` package, but there's no parent package to land in — `store` is already at the top. So `..apis` is "go above top-level, then into a sibling," which Python rejects.

### The fix — absolute import

```python
from apis.filters import ProductFilter, InStockFilterBackend
```

`apis` is importable directly because it's on `sys.path`. No `..` needed.

### The cleaner fix — move the file

Filters are app concerns, not project concerns. They should live in `store/filters.py` next to the model they filter. Then:

```python
from .filters import ProductFilter, InStockFilterBackend
```

A simple relative import, no cross-package gymnastics. Worth doing later — for now the absolute import works.

### Principle

> Relative imports (`.`, `..`) only navigate **inside a single package**. Going from one top-level package to another is always an absolute import. The `..` operator can't escape the top of its own package.

---

## Concept 8 — Settings registration gotcha: comma-less list literals

The error that cost me ten minutes: `ModuleNotFoundError: No module named 'silkdjango_filters'`.

The cause:

```python
INSTALLED_APPS = [
    ...
    'silk'           # ← no comma!
    'django_filters'
]
```

Python concatenates **adjacent string literals at parse time**. So `'silk' 'django_filters'` becomes the single string `'silkdjango_filters'`, and Django dutifully tries to import it as a module.

### How to spot it

The error message (`No module named 'silkdjango_filters'`) is the giveaway — a string concatenation of two app names you recognize. Always read it as "Python merged these two literals" and look at the surrounding lines for a missing comma.

### The fix

```python
INSTALLED_APPS = [
    ...
    'silk',
    'django_filters',
]
```

Trailing commas after every entry — habit-forming. They make insertion/deletion safe and prevent this exact bug.

### Principle

> Adjacent string literals are silently concatenated in Python. Always end every list/tuple element with a comma — it costs nothing and prevents an entire class of "module not found" mysteries.

---

## Quick reference: errors I fixed today

| Error | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'silkdjango_filters'` | Missing comma between `'silk'` and `'django_filters'` in `INSTALLED_APPS` | Add comma; use trailing comma on every entry |
| `ImportError: attempted relative import beyond top-level package` | `from ..apis.filters import ...` from a sibling top-level package | Use absolute import: `from apis.filters import ...` |

---

## Key takeaways

1. **`filter_backends` is a pipeline.** Each backend takes a queryset, narrows it, returns it. Order matters — backends compose left-to-right.
2. **`FilterSet` whitelists URL params.** `fields = {'price': ['gt', 'lt', 'range']}` enables `?price__gt=`, `?price__lt=`, `?price__range=`. Anything else is silently ignored — that's protection, not a bug.
3. **`SearchFilter` is the search-bar; `FilterSet` is column filters.** Different shapes, both URL-driven, fully composable.
4. **`OrderingFilter` always needs `ordering_fields`.** It's the whitelist of sortable columns. Without it, clients could probe schema or hit unindexed sorts.
5. **Custom `BaseFilterBackend` is for policy filters.** "Never show OOS on this endpoint" is reusable across views; that's the case for a backend, not a `get_queryset` override.
6. **Pagination is its own layer.** Backends filter, then paginator slices. Set `DEFAULT_PAGINATION_CLASS` and `PAGE_SIZE` globally in `REST_FRAMEWORK`; override per-view only when needed.
7. **`pagination_class.page_size = 5` mutates the shared class.** Subclass instead — it's two extra lines and removes a cross-view footgun.
8. **Relative imports can't escape their top-level package.** Sibling packages need absolute imports. Better still: keep filters in the app (`store/filters.py`).
9. **Adjacent string literals get concatenated by Python.** `'silk' 'django_filters'` → `'silkdjango_filters'`. Trailing commas everywhere are cheap insurance.
