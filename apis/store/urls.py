
from .views import OrderListView, ProductDetailView, ProductListView, UserOrderListView,ProductInfoView
from django.urls import path

urlpatterns = [
    path('', ProductListView.as_view(), name='product-list'),
    path('info/', ProductInfoView.as_view(), name='product-list-info'),
    path('<int:pk>/', ProductDetailView.as_view(), name='product-detail'),
    path('orders/', OrderListView.as_view(), name='order-list'),
    path('my-orders/', UserOrderListView.as_view(), name='user-order-list'),
]   