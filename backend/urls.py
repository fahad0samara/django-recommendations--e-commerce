from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from frontend import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('frontend.urls')),
    path('list-products/', views.list_products, name='list_products'),  
    path('cart/', include([
        path('', views.view_cart, name='view_cart'),
        path('update/<int:item_id>/', views.update_cart, name='update_cart'),
        path('remove/<int:item_id>/', views.remove_from_cart, name='remove_from_cart'),
        path('checkout/', views.checkout, name='checkout'),
    ])),
    
    # Authentication URLs
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', views.custom_logout, name='logout'),
    path('register/', views.register, name='register'),
    path('profile/', views.profile, name='profile'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
