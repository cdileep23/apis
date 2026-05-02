
# Create your views here.
from django.db.models import Max
from .models import Product,Order
from .serializers import ProductInfoSerializer, ProductSerializer,OrderSerializer
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.response import Response

@api_view(['GET'])
def product_list(request):
    products=Product.objects.all()
    serializer=ProductSerializer(products, many=True)

    return Response(serializer.data)

@api_view(['GET'])
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    serializer = ProductSerializer(product)
    return Response(serializer.data)


@api_view(['GET'])
def order_list(request):

    orders=Order.objects.all()
    serializer=OrderSerializer(orders, many=True)

    return Response(serializer.data)


@api_view(['GET'])
def product_info(request):
    products=Product.objects.all()
    count=products.count()
    max_price=products.aggregate(max_price=Max('price'))['max_price']
    serializer=ProductInfoSerializer({'products':products,'count':count,'max_price':max_price})
    return Response(serializer.data)