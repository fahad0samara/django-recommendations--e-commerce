from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, TemplateView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.urls import reverse_lazy
from django.http import JsonResponse
from django.contrib import messages
from .models import Product, Category, Recommendation, Cart, CartItem, PersonalizedDiscount, UserSegment, UserSegmentMembership, UserProfile, Order
from django.contrib.auth.models import User
from django.db.models import Q, Count
from django.utils import timezone

class HomeView(TemplateView):
    template_name = 'home.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['featured_products'] = Product.objects.filter(featured=True)[:6]
        context['recent_products'] = Product.objects.order_by('-created_at')[:4]
        context['categories'] = Category.objects.annotate(product_count=Count('products'))
        
        if self.request.user.is_authenticated:
            context['recommendations'] = Recommendation.objects.filter(
                user=self.request.user
            ).select_related('product')[:4]
        
        return context

class ProductListView(ListView):
    model = Product
    template_name = 'products.html'
    context_object_name = 'products'
    paginate_by = 12

    def get_queryset(self):
        queryset = Product.objects.all()
        category_id = self.request.GET.get('category')
        search = self.request.GET.get('search')
        
        if category_id:
            queryset = queryset.filter(category_id=category_id)
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | 
                Q(description__icontains=search)
            )
        return queryset.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Category.objects.all()
        
        # Get selected category
        category_id = self.request.GET.get('category')
        if category_id:
            context['selected_category'] = get_object_or_404(Category, id=category_id)
            
        return context

class ProductDetailView(DetailView):
    model = Product
    template_name = 'product_detail.html'
    context_object_name = 'product'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.get_object()
        context['related_products'] = Product.objects.filter(
            category=product.category
        ).exclude(id=product.id)[:4]
        return context

class CartView(LoginRequiredMixin, TemplateView):
    template_name = 'cart/cart.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cart, created = Cart.objects.get_or_create(user=self.request.user)
        context['cart_items'] = cart.items.all()
        context['total'] = sum(item.product.price * item.quantity for item in cart.items.all())
        return context

class DiscountListView(ListView):
    template_name = 'discounts/list.html'
    context_object_name = 'products'

    def get_queryset(self):
        return Product.objects.filter(discount__gt=0).order_by('-discount')

class ProfileView(LoginRequiredMixin, DetailView):
    model = UserProfile
    template_name = 'profile.html'
    context_object_name = 'profile'
    
    def get_object(self):
        return self.request.user.userprofile

class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = UserProfile
    template_name = 'profile_edit.html'
    fields = ['avatar', 'bio', 'phone_number', 'address']
    success_url = reverse_lazy('profile')
    
    def get_object(self):
        return self.request.user.userprofile

class OrderListView(LoginRequiredMixin, ListView):
    model = Order
    template_name = 'orders.html'
    context_object_name = 'orders'
    
    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).order_by('-created_at')

class RegisterView(CreateView):
    form_class = UserCreationForm
    template_name = 'auth/register.html'
    success_url = reverse_lazy('login')
    
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'Account created successfully! Please login.')
        return response

@login_required
def add_to_cart(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    cart_item, created = CartItem.objects.get_or_create(
        user=request.user,
        product=product,
        defaults={'quantity': 1}
    )
    if not created:
        cart_item.quantity += 1
        cart_item.save()
    
    messages.success(request, f'{product.name} added to cart!')
    return JsonResponse({'status': 'success'})

@login_required
def remove_from_cart(request, cart_item_id):
    cart_item = get_object_or_404(CartItem, id=cart_item_id, user=request.user)
    cart = cart_item.cart
    cart_item.delete()
    
    return JsonResponse({
        'cart_total': float(cart.get_total()),
        'cart_items': cart.get_items_count()
    })

@login_required
def update_cart_quantity(request, cart_item_id):
    cart_item = get_object_or_404(CartItem, id=cart_item_id, user=request.user)
    try:
        data = json.loads(request.body)
        quantity = int(data.get('quantity', 1))
        if quantity < 1:
            return JsonResponse({'error': 'Quantity must be at least 1'})
        
        cart_item.quantity = quantity
        cart_item.save()
        
        cart = cart_item.cart
        return JsonResponse({
            'cart_total': float(cart.get_total()),
            'cart_items': cart.get_items_count()
        })
    except (ValueError, json.JSONDecodeError):
        return JsonResponse({'error': 'Invalid quantity'}, status=400)

@login_required
def checkout(request):
    cart_items = CartItem.objects.filter(user=request.user)
    if not cart_items:
        messages.error(request, 'Your cart is empty!')
        return redirect('cart')
    
    total = sum(item.get_total() for item in cart_items)
    order = Order.objects.create(user=request.user, total_amount=total)
    order.items.set(cart_items)
    cart_items.delete()
    
    messages.success(request, 'Order placed successfully!')
    return redirect('order_detail', pk=order.pk)

class DiscountsView(LoginRequiredMixin, TemplateView):
    template_name = 'discounts.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now()
        
        # Get user's active discounts
        user_discounts = PersonalizedDiscount.objects.filter(
            user=self.request.user,
            valid_from__lte=now,
            valid_until__gte=now
        )

        # Get segment-based discounts
        user_segments = UserSegmentMembership.objects.filter(
            user=self.request.user
        ).values_list('segment', flat=True)
        
        segment_discounts = PersonalizedDiscount.objects.filter(
            segment__in=user_segments,
            valid_from__lte=now,
            valid_until__gte=now
        )

        # Combine and remove duplicates
        all_discounts = user_discounts.union(segment_discounts)
        
        context.update({
            'featured_discount': all_discounts.first(),
            'other_discounts': all_discounts[1:],
        })
        return context
