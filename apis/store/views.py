
# Create your views here.
from django.db.models import Max
from .models import Product,Order,User
from .serializers import ProductInfoSerializer, ProductSerializer,OrderSerializer,OrderCreateSerializer,UserSerializer
from django.shortcuts import get_object_or_404
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated,IsAdminUser,AllowAny
from rest_framework.views import APIView
from apis.filters import ProductFilter,InStockFilterBackend,OrderFilter
from rest_framework import filters
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
"""

function based view for product list

@api_view(['GET'])
def product_list(request):
    products=Product.objects.all()
    serializer=ProductSerializer(products, many=True)

    return Response(serializer.data)


"""



'Class based view for product list'

class ProductListView(generics.ListCreateAPIView):
    queryset = Product.objects.order_by('name')
    serializer_class = ProductSerializer
    filterset_class = ProductFilter
    filter_backends = [DjangoFilterBackend, filters.SearchFilter,filters.OrderingFilter,InStockFilterBackend]
    search_fields = ['=name','description']
    ordering_fields = ['price', 'name']
    pagination_class = PageNumberPagination
    pagination_class.page_size = 5

    def get_permissions(self):
        self.permission_classes=[AllowAny]

        if self.request.method == 'POST':
            self.permission_classes=[IsAdminUser]
        return super().get_permissions()

"""
class based view for product create

class ProductCreateView(generics.CreateAPIView):
    model = Product
    serializer_class = ProductSerializer

     def create(self, request, *args, **kwargs):
        print("Creating a new product with data:", request.data)
        return super().create(request, *args, **kwargs) 

"""
   


"""
function based view for product detail

@api_view(['GET'])
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    serializer = ProductSerializer(product)
    return Response(serializer.data)
"""

class ProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

    def get_permissions(self):
        self.permission_classes=[AllowAny]

        if self.request.method in ['PUT','PATCH', 'DELETE']:
            self.permission_classes=[IsAdminUser]
        return super().get_permissions()

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



class OrderViewSet(viewsets.ModelViewSet):
      queryset=Order.objects.prefetch_related('items__product')
      serializer_class=OrderSerializer
      permission_classes=[AllowAny]
      pagination_class=None
      filterset_class=OrderFilter
      filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
      ordering_fields = ['created_at']
      
      def get_serializer_class(self):
         return super().get_serializer_class() if self.action in ['list', 'retrieve'] else OrderCreateSerializer

      def get_queryset(self):
          
          queryset=super().get_queryset()
          if self.request.user.is_staff:
              return queryset.filter(user=self.request.user)
          return queryset

      @action(detail=False, methods=['get'],url_path='user-orders', permission_classes=[IsAuthenticated])
      def user_order(self,request):
          user=self.request.user
          orders=self.queryset.filter(user=user)
          serializer=self.get_serializer(orders, many=True)
          return Response(serializer.data)


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
    
class UserListView(generics.ListAPIView):
    queryset=User.objects.all()
    serializer_class=UserSerializer
    pagination_class=None