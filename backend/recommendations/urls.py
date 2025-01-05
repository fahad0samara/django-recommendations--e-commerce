from django.urls import path
from . import views, frontend_views

urlpatterns = [
    # Frontend Views
    path('', frontend_views.HomeView.as_view(), name='home'),
    path('products/', frontend_views.ProductListView.as_view(), name='products'),
    path('products/<int:pk>/', frontend_views.ProductDetailView.as_view(), name='product_detail'),
    
    # User Profile
    path('profile/', frontend_views.ProfileView.as_view(), name='profile'),
    path('profile/edit/', frontend_views.ProfileUpdateView.as_view(), name='profile_edit'),
    path('orders/', frontend_views.OrderListView.as_view(), name='orders'),
    
    # Cart and Checkout
    path('cart/', frontend_views.CartView.as_view(), name='cart'),
    path('cart/add/<int:product_id>/', frontend_views.add_to_cart, name='add_to_cart'),
    path('cart/remove/<int:cart_item_id>/', frontend_views.remove_from_cart, name='remove_from_cart'),
    path('cart/update/<int:cart_item_id>/', frontend_views.update_cart_quantity, name='update_cart_quantity'),
    path('checkout/', frontend_views.checkout, name='checkout'),
    
    # Discounts and Recommendations
    path('discounts/', frontend_views.DiscountListView.as_view(), name='discounts'),
    path('api/recommendations/', views.get_recommendations, name='get_recommendations'),
]
