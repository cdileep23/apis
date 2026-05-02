
from .views import order_list, product_detail, product_list,product_info
from django.urls import path

urlpatterns = [
    path('', product_list, name='product-list'),
    path('info/', product_info, name='product-list-info'),
    path('<int:pk>/', product_detail, name='product-detail'),
    path('orders/', order_list, name='order-list'),
]   