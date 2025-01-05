from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from .models import Product, CartItem, Cart, Category, Order, ProductView, UserProfile
from .forms import CustomUserCreationForm
import json

def get_or_create_cart(request):
    """Get or create a cart for the current user or session."""
    if not request.session.session_key:
        request.session.create()
        print(f"Created new session: {request.session.session_key}")
    
    try:
        if request.user.is_authenticated:
            cart, created = Cart.objects.get_or_create(user=request.user)
            print(f"Got cart for authenticated user: {cart.id} (created: {created})")
        else:
            cart_id = request.session.get('cart_id')
            if cart_id:
                try:
                    cart = Cart.objects.get(id=cart_id)
                    print(f"Got existing cart from session: {cart.id}")
                except Cart.DoesNotExist:
                    cart = Cart.objects.create()
                    request.session['cart_id'] = cart.id
                    print(f"Created new cart (session cart not found): {cart.id}")
            else:
                cart = Cart.objects.create()
                request.session['cart_id'] = cart.id
                print(f"Created new cart (no session cart): {cart.id}")
        
        return cart
    except Exception as e:
        print(f"Error in get_or_create_cart: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return None

def get_similar_products(product, limit=4):
    # Get products in the same category
    similar_products = Product.objects.filter(
        category=product.category
    ).exclude(id=product.id)
    
    # Get products with similar price range (±20%)
    min_price = float(product.price) * 0.8
    max_price = float(product.price) * 1.2
    
    price_similar = similar_products.filter(
        price__gte=min_price,
        price__lte=max_price
    )
    
    # Combine and prioritize results
    if price_similar.exists():
        return price_similar.order_by('?')[:limit]
    return similar_products.order_by('?')[:limit]

def get_personalized_recommendations(user, limit=4):
    if not user.is_authenticated:
        return Product.objects.filter(featured=True)[:limit]
    
    # Get user's recently viewed products
    recent_views = ProductView.objects.filter(user=user).select_related('product')[:5]
    
    if not recent_views:
        return Product.objects.filter(featured=True)[:limit]
    
    # Get categories user is interested in
    categories = [view.product.category for view in recent_views]
    
    # Get products from those categories
    recommendations = Product.objects.filter(
        category__in=categories
    ).exclude(
        id__in=[view.product.id for view in recent_views]
    ).order_by('?')[:limit]
    
    return recommendations

def home(request):
    featured_products = Product.objects.filter(featured=True)[:8]
    latest_products = Product.objects.order_by('-created_at')[:8]
    context = {
        'featured_products': featured_products,
        'latest_products': latest_products
    }
    return render(request, 'home.html', context)

def products(request):
    try:
        # Get query parameters
        search_query = request.GET.get('search', '')
        category_id = request.GET.get('category', '')
        sort_by = request.GET.get('sort', '-created_at')  # Default sort by newest
        
        # Start with all products
        products = Product.objects.select_related('category').all()
        
        # Apply search filter
        if search_query:
            products = products.filter(name__icontains=search_query)
        
        # Apply category filter
        if category_id:
            try:
                category_id = int(category_id)
                products = products.filter(category_id=category_id)
            except ValueError:
                pass
        
        # Apply sorting
        valid_sort_options = {
            'price_asc': 'price',
            'price_desc': '-price',
            'name': 'name',
            'newest': '-created_at'
        }
        products = products.order_by(valid_sort_options.get(sort_by, '-created_at'))
        
        # Get all categories for the filter dropdown
        categories = Category.objects.all()
        
        # Calculate discount for each product
        for product in products:
            if product.original_price and product.original_price > product.price:
                product.discount_percent = int(((product.original_price - product.price) / product.original_price) * 100)
            else:
                product.discount_percent = None
        
        context = {
            'products': products,
            'categories': categories,
            'current_category': category_id,
            'current_sort': sort_by,
            'search_query': search_query,
            'error': None
        }
        return render(request, 'products.html', context)
    except Exception as e:
        print(f"Error in products view: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return render(request, 'products.html', {
            'products': [],
            'categories': Category.objects.all(),
            'error': 'An error occurred while loading products. Please try again later.'
        })

def list_products(request):
    products = Product.objects.all()
    categories = Category.objects.all()
    
    print("\nAll Products:")
    for product in products:
        print(f"- {product.name} (Category: {product.category.name}, Price: ${product.price})")
    
    print("\nAll Categories:")
    for category in categories:
        print(f"- {category.name}")
    
    context = {
        'products': products,
        'categories': categories
    }
    return render(request, 'products.html', context)

def product_detail(request, product_id):
    try:
        product = Product.objects.get(id=product_id)
        
        # Record the view if user is authenticated
        if request.user.is_authenticated:
            ProductView.objects.create(user=request.user, product=product)
        
        # Get recommendations with error handling
        try:
            similar_products = product.get_similar_products()
        except Exception as e:
            similar_products = []
            messages.warning(request, "Could not load similar products.")
            
        try:
            frequently_bought = product.get_frequently_bought_together()
        except Exception as e:
            frequently_bought = []
            messages.warning(request, "Could not load frequently bought products.")
            
        try:
            personalized_recommendations = product.get_personalized_recommendations(request.user)
        except Exception as e:
            personalized_recommendations = []
            messages.warning(request, "Could not load personalized recommendations.")
        
        context = {
            'product': product,
            'similar_products': similar_products,
            'frequently_bought': frequently_bought,
            'recommended_products': personalized_recommendations,
        }
        
        return render(request, 'product_detail.html', context)
        
    except Product.DoesNotExist:
        messages.error(request, 'Product not found.')
        return redirect('products')

@csrf_exempt
@require_POST
def add_to_cart(request, product_id):
    """Add a product to the cart."""
    print("\n=== Adding to Cart ===")
    print(f"Session ID: {request.session.session_key}")
    print(f"Product ID: {product_id}")
    print(f"Request Method: {request.method}")
    print(f"Content Type: {request.content_type}")
    print(f"POST data: {request.POST}")
    
    try:
        # Make sure we have a session
        if not request.session.session_key:
            request.session.create()
            request.session.save()
            print(f"Created new session: {request.session.session_key}")
        
        # Get the product first
        try:
            product = Product.objects.select_related('category').get(id=product_id)
            print(f"Found product: {product.name} (ID: {product.id}, Stock: {product.stock})")
        except Product.DoesNotExist:
            print(f"Product not found: {product_id}")
            return JsonResponse({
                'success': False,
                'error': 'Product not found'
            }, status=404)
        except Exception as e:
            print(f"Error getting product: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': 'Error accessing product'
            }, status=500)
        
        # Get quantity from POST data or JSON data
        try:
            if request.content_type == 'application/json':
                data = json.loads(request.body)
                quantity = int(data.get('quantity', 1))
            else:
                quantity = int(request.POST.get('quantity', 1))
            
            print(f"Quantity: {quantity}")
            
            if quantity < 1:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid quantity'
                }, status=400)
        except (ValueError, json.JSONDecodeError) as e:
            print(f"Error parsing quantity: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': 'Invalid quantity'
            }, status=400)
        
        # Check stock
        if quantity > product.stock:
            print(f"Not enough stock. Requested: {quantity}, Available: {product.stock}")
            return JsonResponse({
                'success': False,
                'error': f'Only {product.stock} items available'
            }, status=400)
        
        # Get or create cart
        try:
            cart = get_or_create_cart(request)
            if not cart:
                print("Error creating cart")
                return JsonResponse({
                    'success': False,
                    'error': 'Error creating cart'
                }, status=500)
            
            print(f"Cart ID: {cart.id}")
            print(f"Cart Items: {cart.items.count()}")
            
            # Get or create cart item
            cart_item, created = CartItem.objects.get_or_create(
                cart=cart,
                product=product,
                defaults={'quantity': quantity}
            )
            
            if not created:
                cart_item.quantity += quantity
                if cart_item.quantity > product.stock:
                    print(f"Total quantity exceeds stock. Total: {cart_item.quantity}, Stock: {product.stock}")
                    return JsonResponse({
                        'success': False,
                        'error': f'Only {product.stock} items available'
                    }, status=400)
                cart_item.save()
            
            print(f"Cart item {'created' if created else 'updated'}: {cart_item.quantity}x {product.name}")
            
            # Save the cart ID in session
            request.session['cart_id'] = cart.id
            request.session.save()
            
            # Return success response
            response_data = {
                'success': True,
                'cart_count': cart.items.count(),
                'message': 'Product added to cart successfully'
            }
            print(f"Success! Cart count: {response_data['cart_count']}")
            return JsonResponse(response_data)
            
        except Exception as e:
            print(f"Error managing cart: {str(e)}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            return JsonResponse({
                'success': False,
                'error': 'Error updating cart'
            }, status=500)
        
    except Exception as e:
        print(f"Error in add_to_cart: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
def view_cart(request):
    cart = get_or_create_cart(request)
    cart_items = cart.items.select_related('product', 'product__category').all()
    
    context = {
        'cart': cart,
        'cart_items': cart_items,
    }
    return render(request, 'cart/cart.html', context)

@login_required
def checkout(request):
    cart = get_or_create_cart(request)
    cart_items = cart.items.select_related('product').all()
    
    if not cart_items:
        messages.warning(request, 'Your cart is empty')
        return redirect('view_cart')
    
    context = {
        'cart': cart,
        'cart_items': cart_items,
    }
    return render(request, 'cart/checkout.html', context)

@csrf_exempt
@require_POST
def update_cart(request, item_id):
    try:
        data = json.loads(request.body)
        quantity = int(data.get('quantity', 1))
        
        if quantity < 1:
            return JsonResponse({'success': False, 'error': 'Quantity must be at least 1'})
        
        cart = get_or_create_cart(request)
        cart_item = cart.items.get(id=item_id)
        
        # Check if we have enough stock
        if quantity > cart_item.product.stock:
            return JsonResponse({
                'success': False, 
                'error': f'Only {cart_item.product.stock} items available'
            })
        
        cart_item.quantity = quantity
        cart_item.save()
        
        return JsonResponse({
            'success': True,
            'item_total': float(cart_item.get_total()),
            'cart_total': float(cart.get_total()),
            'cart_subtotal': float(cart.get_total()),
            'cart_count': cart.total_items
        })
        
    except CartItem.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Item not found'})
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid request'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@csrf_exempt
@require_POST
def remove_from_cart(request, item_id):
    try:
        cart = get_or_create_cart(request)
        cart_item = cart.items.get(id=item_id)
        cart_item.delete()
        
        return JsonResponse({
            'success': True,
            'cart_total': float(cart.get_total()),
            'cart_subtotal': float(cart.get_total()),
            'cart_count': cart.total_items
        })
        
    except CartItem.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Item not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def profile(request):
    user = request.user
    orders = Order.objects.filter(user=user).order_by('-created_at')
    return render(request, 'auth/profile.html', {
        'user': user,
        'orders': orders
    })

def register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, 'Account created successfully! You can now log in.')
            return redirect('login')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CustomUserCreationForm()
    return render(request, 'registration/register.html', {'form': form})

def custom_logout(request):
    logout(request)
    messages.success(request, 'You have been successfully logged out.')
    return redirect('home')
