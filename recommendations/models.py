from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver

class Category(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(default='')
    image = models.CharField(max_length=100, default='', blank=True)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Categories"
    
    def __str__(self):
        return self.name

class Product(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(default='')
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    discount = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    rating = models.DecimalField(max_digits=3, decimal_places=1, default=0.0)
    stock = models.IntegerField(default=0)
    featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    @property
    def original_price(self):
        if self.discount:
            return float(self.price) / (1 - self.discount/100)
        return None

    def __str__(self):
        return self.name

class UserInteraction(models.Model):
    INTERACTION_TYPES = (
        ('view', 'View'),
        ('cart', 'Add to Cart'),
        ('wishlist', 'Add to Wishlist'),
        ('purchase', 'Purchase'),
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    interaction_type = models.CharField(max_length=10, choices=INTERACTION_TYPES)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['user', 'product', 'interaction_type']),
            models.Index(fields=['timestamp']),
        ]

class ProductSimilarity(models.Model):
    product_a = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='similarities_as_a')
    product_b = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='similarities_as_b')
    similarity_score = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    last_updated = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('product_a', 'product_b')
        indexes = [
            models.Index(fields=['product_a', 'similarity_score']),
            models.Index(fields=['product_b', 'similarity_score']),
        ]

class Recommendation(models.Model):
    RECOMMENDATION_TYPES = (
        ('personal', 'Personalized'),
        ('similar', 'Similar Products'),
        ('trending', 'Trending'),
        ('popular', 'Popular'),
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    recommendation_type = models.CharField(max_length=10, choices=RECOMMENDATION_TYPES)
    score = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    explanation = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        indexes = [
            models.Index(fields=['user', 'recommendation_type', 'score']),
            models.Index(fields=['created_at']),
        ]

class ProductRating(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='ratings')
    rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    review = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'product')
        indexes = [
            models.Index(fields=['product', 'rating']),
            models.Index(fields=['user', 'rating']),
        ]
    
    def __str__(self):
        return f"{self.user.username}'s rating for {self.product.name}"

class ProductView(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='views')
    view_count = models.IntegerField(default=1)
    last_viewed = models.DateTimeField(auto_now=True)
    session_id = models.CharField(max_length=100, blank=True, null=True)
    
    class Meta:
        unique_together = ('user', 'product')
        indexes = [
            models.Index(fields=['product', 'view_count']),
            models.Index(fields=['last_viewed']),
        ]

class SearchHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    query = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)
    results_count = models.IntegerField()
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['query']),
        ]
        verbose_name_plural = 'Search histories'

class ProductTag(models.Model):
    name = models.CharField(max_length=50)
    products = models.ManyToManyField(Product, related_name='tags')
    
    def __str__(self):
        return self.name

class ProductAttribute(models.Model):
    ATTRIBUTE_TYPES = (
        ('text', 'Text'),
        ('number', 'Number'),
        ('boolean', 'Boolean'),
        ('color', 'Color'),
        ('size', 'Size'),
    )
    
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='attributes')
    name = models.CharField(max_length=50)
    value = models.CharField(max_length=255)
    attribute_type = models.CharField(max_length=10, choices=ATTRIBUTE_TYPES)
    
    class Meta:
        unique_together = ('product', 'name')
    
    def __str__(self):
        return f"{self.product.name} - {self.name}: {self.value}"

class PriceAlert(models.Model):
    ALERT_TYPES = (
        ('below', 'Price Below'),
        ('above', 'Price Above'),
        ('percent_change', 'Percentage Change'),
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    target_price = models.DecimalField(max_digits=10, decimal_places=2)
    alert_type = models.CharField(max_length=15, choices=ALERT_TYPES)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    last_notified = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ('user', 'product', 'alert_type')

class RecentlyViewed(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    viewed_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-viewed_at']
        unique_together = ('user', 'product')

class SeasonalRecommendation(models.Model):
    SEASON_TYPES = (
        ('spring', 'Spring'),
        ('summer', 'Summer'),
        ('autumn', 'Autumn'),
        ('winter', 'Winter'),
        ('holiday', 'Holiday'),
        ('custom', 'Custom'),
    )
    
    name = models.CharField(max_length=100)
    season_type = models.CharField(max_length=10, choices=SEASON_TYPES)
    products = models.ManyToManyField(Product, related_name='seasonal_recommendations')
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=0)
    
    def __str__(self):
        return f"{self.name} ({self.season_type})"

class MLModel(models.Model):
    MODEL_TYPES = (
        ('collaborative', 'Collaborative Filtering'),
        ('content_based', 'Content Based'),
        ('hybrid', 'Hybrid'),
    )
    
    name = models.CharField(max_length=100)
    model_type = models.CharField(max_length=15, choices=MODEL_TYPES)
    version = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)
    accuracy = models.FloatField(null=True, blank=True)
    last_trained = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict)
    
    def __str__(self):
        return f"{self.name} v{self.version}"

class MLPrediction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    model = models.ForeignKey(MLModel, on_delete=models.CASCADE)
    score = models.FloatField()
    confidence = models.FloatField()
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        unique_together = ('user', 'product', 'model')
        indexes = [
            models.Index(fields=['user', 'score']),
            models.Index(fields=['created_at']),
        ]

class ABTest(models.Model):
    TEST_STATUS = (
        ('draft', 'Draft'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('archived', 'Archived')
    )
    
    name = models.CharField(max_length=100)
    description = models.TextField()
    status = models.CharField(max_length=10, choices=TEST_STATUS, default='draft')
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    control_group_size = models.FloatField(default=0.5)  # Percentage of users in control group
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} ({self.status})"

class ABTestVariant(models.Model):
    VARIANT_TYPES = (
        ('control', 'Control Group'),
        ('test', 'Test Group')
    )
    
    test = models.ForeignKey(ABTest, on_delete=models.CASCADE, related_name='variants')
    name = models.CharField(max_length=100)
    variant_type = models.CharField(max_length=10, choices=VARIANT_TYPES)
    description = models.TextField()
    configuration = models.JSONField(default=dict)  # Store variant-specific settings
    
    def __str__(self):
        return f"{self.test.name} - {self.name}"

class UserSegment(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    rules = models.JSONField(default=dict)  # Store segment rules (age, location, etc.)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name

class UserSegmentMembership(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    segment = models.ForeignKey(UserSegment, on_delete=models.CASCADE)
    score = models.FloatField(default=1.0)  # How well user matches segment
    joined_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('user', 'segment')

class ProductCollection(models.Model):
    COLLECTION_TYPES = (
        ('manual', 'Manually Curated'),
        ('dynamic', 'Dynamically Generated'),
        ('seasonal', 'Seasonal Collection'),
        ('trending', 'Trending Products')
    )
    
    name = models.CharField(max_length=100)
    description = models.TextField(default='')
    collection_type = models.CharField(max_length=10, choices=COLLECTION_TYPES)
    products = models.ManyToManyField(Product, through='ProductCollectionItem')
    is_active = models.BooleanField(default=True)
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    rules = models.JSONField(default=dict, null=True, blank=True)  # For dynamic collections
    image = models.ImageField(upload_to='collections/', null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name

class ProductCollectionItem(models.Model):
    collection = models.ForeignKey(ProductCollection, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    position = models.IntegerField(default=0)
    added_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['position']
        unique_together = ('collection', 'product')

class PersonalizedDiscount(models.Model):
    DISCOUNT_TYPES = (
        ('percentage', 'Percentage Off'),
        ('fixed', 'Fixed Amount Off'),
        ('buy_x_get_y', 'Buy X Get Y'),
        ('bundle', 'Bundle Discount')
    )
    
    name = models.CharField(max_length=100)
    description = models.TextField()
    discount_type = models.CharField(max_length=15, choices=DISCOUNT_TYPES)
    value = models.DecimalField(max_digits=10, decimal_places=2)
    segments = models.ManyToManyField(UserSegment, blank=True)
    products = models.ManyToManyField(Product, blank=True)
    collections = models.ManyToManyField(ProductCollection, blank=True)
    min_purchase = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    max_uses = models.IntegerField(null=True, blank=True)
    current_uses = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    rules = models.JSONField(default=dict)  # Additional rules for discount
    created_at = models.DateTimeField(default=timezone.now)
    
    def __str__(self):
        return self.name

class RecommendationExplanation(models.Model):
    EXPLANATION_TYPES = (
        ('similar_users', 'Similar Users'),
        ('purchase_history', 'Based on Purchase History'),
        ('view_history', 'Based on Viewing History'),
        ('trending', 'Trending in Your Area'),
        ('popular', 'Popular in Your Category'),
        ('personalized', 'Personalized for You'),
        ('segment', 'Popular in Your Segment')
    )
    
    recommendation = models.ForeignKey(Recommendation, on_delete=models.CASCADE, related_name='explanations')
    explanation_type = models.CharField(max_length=20, choices=EXPLANATION_TYPES)
    explanation = models.TextField()
    confidence_score = models.FloatField()
    supporting_data = models.JSONField(default=dict)  # Store data supporting the explanation
    created_at = models.DateTimeField(default=timezone.now)
    
    def __str__(self):
        return f"{self.recommendation.product.name} - {self.explanation_type}"

class UserPreference(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    favorite_categories = models.ManyToManyField(Category, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username}'s preferences"

class Discount(models.Model):
    DISCOUNT_TYPES = [
        ('percentage', 'Percentage'),
        ('fixed', 'Fixed Amount'),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(default='')
    discount_type = models.CharField(max_length=10, choices=DISCOUNT_TYPES, default='percentage')
    value = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(default=timezone.now)
    products = models.ManyToManyField(Product, related_name='discounts', blank=True)
    collections = models.ManyToManyField(ProductCollection, related_name='discounts', blank=True)
    max_uses = models.IntegerField(null=True, blank=True)
    current_uses = models.IntegerField(default=0)
    min_purchase = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name

class Cart(models.Model):
    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_total(self):
        return sum(item.get_total() for item in self.items.all())
    
    def get_items_count(self):
        return sum(item.quantity for item in self.items.all())
    
    def __str__(self):
        return f"Cart for {self.user.username}"

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_total(self):
        return self.product.price * self.quantity
    
    def __str__(self):
        return f"{self.quantity}x {self.product.name} in cart"

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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order #{self.id} - {self.user.username}"
