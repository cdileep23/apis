from django.db import transaction
from rest_framework import serializers
from .models import Product, Order, OrderItem, User

class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ('description','name','price','stock')

    def validate_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Price must be a positive number.")
        return value
    

class OrderItemSerializer(serializers.ModelSerializer):
    # product = ProductSerializer(read_only=True)
    product_name=serializers.CharField(source='product.name', read_only=True)
    product_price=serializers.DecimalField(source='product.price', max_digits=10, decimal_places=2, read_only=True)
    class Meta:
        model = OrderItem
        fields = ('product_name', 'product_price', 'quantity','item_subtotal')

class OrderCreateSerializer(serializers.ModelSerializer):
    class OrderItemCreateSerializer(serializers.ModelSerializer):
        class Meta:
            model = OrderItem
            fields = ('product', 'quantity')

    items = OrderItemCreateSerializer(many=True, required=False)

    class Meta:
        model = Order
        fields = ('user', 'status', 'items')
        extra_kwargs = {
            'user': {'write_only': True}
        }

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        with transaction.atomic():
            order = Order.objects.create(**validated_data)
            for item_data in items_data:
                OrderItem.objects.create(order=order, **item_data)
        return order

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if items_data is not None:
                instance.items.all().delete()
                for item_data in items_data:
                    OrderItem.objects.create(order=instance, **item_data)
        return instance

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True,read_only=True)
    total_price = serializers.SerializerMethodField()
    order_id=serializers.UUIDField(read_only=True)
    def get_total_price(self, obj):
        total = sum(item.product.price * item.quantity for item in obj.items.all())
        return total
    class Meta:
        model = Order
        fields = ('order_id','created_at','user','status','items','total_price')


class ProductInfoSerializer(serializers.Serializer):
    products = ProductSerializer(many=True)
    count = serializers.IntegerField()
    max_price = serializers.DecimalField(max_digits=10, decimal_places=2)

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ( 'username', 'email','is_staff')