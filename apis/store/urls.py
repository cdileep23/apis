
from .views import  OrderViewSet, ProductDetailView, ProductListView,ProductInfoView
from django.urls import path
from rest_framework.routers import DefaultRouter

urlpatterns = [
    path('', ProductListView.as_view(), name='product-list'),
    path('info/', ProductInfoView.as_view(), name='product-list-info'),
    path('<int:pk>/', ProductDetailView.as_view(), name='product-detail'),

]   

router=DefaultRouter()
router.register('orders', OrderViewSet, basename='order')
urlpatterns+=router.urls

