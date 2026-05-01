
from .views import product_detail, product_list
from django.urls import path

urlpatterns = [
    path('', product_list, name='product-list'),
    path('<int:pk>/', product_detail, name='product-detail'),
]   