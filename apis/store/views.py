
# Create your views here.
from django.db.models import Max
from .models import Product,Order
from .serializers import ProductInfoSerializer, ProductSerializer,OrderSerializer
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

"""

function based view for product list

@api_view(['GET'])
def product_list(request):
    products=Product.objects.all()
    serializer=ProductSerializer(products, many=True)

    return Response(serializer.data)


"""



'Class based view for product list'

class ProductListView(generics.ListAPIView):
    queryset = Product.objects.filter(stock__gt=0)
    serializer_class = ProductSerializer




"""
function based view for product detail

@api_view(['GET'])
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    serializer = ProductSerializer(product)
    return Response(serializer.data)
"""

class ProductDetailView(generics.RetrieveAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

"""
function based view for order list
@api_view(['GET'])
def order_list(request):

    orders=Order.objects.prefetch_related('items__product')
    serializer=OrderSerializer(orders, many=True)

    return Response(serializer.data)

"""

"""
class based view for order list
"""

class OrderListView(generics.ListAPIView):
    queryset=Order.objects.prefetch_related('items__product')
    serializer_class=OrderSerializer

class UserOrderListView(generics.ListAPIView):
    queryset=Order.objects.prefetch_related('items__product')
    serializer_class=OrderSerializer
    permission_classes=[IsAuthenticated]

    def get_queryset(self):
        user=self.request.user
        return self.queryset.filter(user=user)


"""
function based view for product info

@api_view(['GET'])
def product_info(request):
    products=Product.objects.all()
    count=products.count()
    max_price=products.aggregate(max_price=Max('price'))['max_price']
    serializer=ProductInfoSerializer({'products':products,'count':count,'max_price':max_price})
    return Response(serializer.data)

"""

class ProductInfoView(APIView):
    def get(self, request):
        products=Product.objects.all()
        count=products.count()
        max_price=products.aggregate(max_price=Max('price'))['max_price']
        serializer=ProductInfoSerializer({'products':products,'count':count,'max_price':max_price})
        return Response(serializer.data)