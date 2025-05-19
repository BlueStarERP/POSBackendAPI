from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.contrib.auth.models import User
from .models import Category, Product, Customer, Order, OrderItem, Payment
from .serializers import (
    UserSerializer, CategorySerializer, ProductSerializer,
    CustomerSerializer, OrderSerializer, PaymentSerializer, OrderItemSerializer
)
from django.shortcuts import get_object_or_404
from django.db import transaction

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        category_id = self.request.query_params.get('category_id')
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        return queryset

class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    
    @action(detail=False, methods=['get'])
    def search(self, request):
        query = request.query_params.get('query', '')
        customers = self.queryset.filter(name__icontains=query)
        serializer = self.get_serializer(customers, many=True)
        return Response(serializer.data)

class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=True, methods=['post'])
    def add_item(self, request, pk=None):
        order = self.get_object()
        product_id = request.data.get('product_id')
        quantity = int(request.data.get('quantity', 1))
        
        product = get_object_or_404(Product, pk=product_id)
        
        # Check if item already exists in order
        order_item, created = OrderItem.objects.get_or_create(
            order=order,
            product=product,
            defaults={
                'quantity': quantity,
                'price': product.price,
                'total': product.price * quantity
            }
        )
        
        if not created:
            order_item.quantity += quantity
            order_item.total = order_item.price * order_item.quantity
            order_item.save()
        
        # Update order totals
        self.update_order_totals(order)
        
        return Response({'status': 'item added'}, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'])
    def checkout(self, request, pk=None):
        order = self.get_object()
        payment_data = request.data.get('payment', {})
        
        with transaction.atomic():
            # Update order status
            order.status = 'completed'
            order.save()
            
            # Create payment
            payment_serializer = PaymentSerializer(data=payment_data)
            if payment_serializer.is_valid():
                payment_serializer.save(order=order)
                
                # Update product stock
                for item in order.items.all():
                    product = item.product
                    product.stock_quantity -= item.quantity
                    product.save()
                
                return Response({
                    'order': OrderSerializer(order).data,
                    'payment': payment_serializer.data
                }, status=status.HTTP_200_OK)
            else:
                return Response(payment_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def update_order_totals(self, order):
        items = order.items.all()
        subtotal = sum(item.total for item in items)
        
        # Calculate tax (example: 10% tax)
        tax = subtotal * 0.1
        
        # Apply discount if any
        discount = order.discount
        
        grand_total = subtotal + tax - discount
        
        order.total = subtotal
        order.tax = tax
        order.grand_total = grand_total
        order.save()

class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer