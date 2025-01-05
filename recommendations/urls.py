from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views, frontend_views

# Create a router and register our viewsets
router = DefaultRouter()
router.register(r'products', views.ProductViewSet)
router.register(r'recommendations', views.RecommendationViewSet)
router.register(r'user-interactions', views.UserInteractionViewSet)
router.register(r'product-views', views.ProductViewViewSet, basename='product-view')
router.register(r'search-history', views.SearchHistoryViewSet, basename='search-history')
router.register(r'product-tags', views.ProductTagViewSet)
router.register(r'price-alerts', views.PriceAlertViewSet, basename='price-alert')
router.register(r'recently-viewed', views.RecentlyViewedViewSet, basename='recently-viewed')
router.register(r'seasonal-recommendations', views.SeasonalRecommendationViewSet)
router.register(r'ml-predictions', views.MLPredictionViewSet, basename='ml-prediction')
router.register(r'ab-tests', views.ABTestViewSet)
router.register(r'user-segments', views.UserSegmentViewSet)
router.register(r'product-collections', views.ProductCollectionViewSet)
router.register(r'personalized-discounts', views.PersonalizedDiscountViewSet)
router.register(r'cart', views.CartViewSet, basename='cart')

urlpatterns = [
    # API endpoints
    path('api/', include(router.urls)),
    
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
    
    # Additional frontend URLs
    path('cart/', views.view_cart, name='view_cart'),
    path('products/', views.product_list, name='product_list'),
    path('products/<int:product_id>/', views.product_detail, name='product_detail'),
]
