from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Category(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    def __str__(self):
        return self.name

class Product(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    original_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    image = models.ImageField(upload_to='products/', null=True, blank=True)
    stock = models.IntegerField(default=0)
    featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
    
    def get_absolute_url(self):
        return f"/product/{self.id}/"
    
    def get_add_to_cart_url(self):
        return f"/cart/add/{self.id}/"
    
    @property
    def is_in_stock(self):
        return self.stock > 0

    def get_similar_products(self, limit=4):
        """Get similar products based on category and price range"""
        from decimal import Decimal
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Ensure price is Decimal
            price = Decimal(str(self.price))
            
            # Calculate price range
            min_price = price * Decimal('0.7')
            max_price = price * Decimal('1.3')
            
            logger.debug(f"Price: {price}, Min: {min_price}, Max: {max_price}")
            
            similar_products = Product.objects.filter(
                category=self.category,
                price__range=(min_price, max_price)
            ).exclude(id=self.id).order_by('?')[:limit]
            
            return similar_products
            
        except Exception as e:
            logger.error(f"Error in get_similar_products: {str(e)}")
            return Product.objects.filter(category=self.category).exclude(id=self.id).order_by('?')[:limit]

    def get_frequently_bought_together(self, limit=4):
        """Get products frequently bought together based on order history"""
        from django.db.models import Count
        # Get all orders containing this product
        orders = Order.objects.filter(items__product=self)
        # Get products from those orders, excluding the current product
        products = Product.objects.filter(
            cartitem__order__in=orders
        ).exclude(id=self.id).annotate(
            times_bought_together=Count('id')
        ).order_by('-times_bought_together')[:limit]
        return products

    def get_personalized_recommendations(self, user, limit=4):
        """Get personalized recommendations based on user's viewing and purchase history"""
        if not user.is_authenticated:
            return self.get_similar_products(limit)

        # Get products from user's viewing history
        viewed_products = Product.objects.filter(
            productview__user=user
        ).exclude(id=self.id).order_by('-productview__viewed_at')[:limit]

        # If not enough viewed products, add similar products
        if viewed_products.count() < limit:
            similar_products = self.get_similar_products(limit - viewed_products.count())
            return list(viewed_products) + list(similar_products)

        return viewed_products

class ProductImage(models.Model):
    product = models.ForeignKey(Product, related_name='additional_images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='products/')
    
    def __str__(self):
        return f"Image for {self.product.name}"

class Cart(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Cart {self.id}"
    
    def get_total_price(self):
        return sum(item.get_total_price() for item in self.items.all())

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)
    
    def __str__(self):
        return f"{self.quantity} x {self.product.name}"
    
    def get_total_price(self):
        return self.product.price * self.quantity

class Order(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('SHIPPED', 'Shipped'),
        ('DELIVERED', 'Delivered'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    items = models.ManyToManyField(CartItem)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    shipping_address = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Order {self.id} by {self.user.username}"

class ProductView(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-viewed_at']

    def __str__(self):
        return f"{self.user.username} viewed {self.product.name}"

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    default_billing_address = models.TextField(null=True, blank=True)
    phone_number = models.CharField(max_length=15, null=True, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    
    def __str__(self):
        return self.user.username

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(
            user=instance,
            default_billing_address='',
            phone_number=''
        )

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.userprofile.save()
