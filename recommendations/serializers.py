from rest_framework import serializers
from django.db.models import Avg
from .models import (
    Product, Category, UserInteraction, Recommendation,
    ProductRating, ProductView, SearchHistory, ProductTag,
    ProductAttribute, PriceAlert, RecentlyViewed, SeasonalRecommendation,
    MLModel, MLPrediction, ABTestVariant, ABTest, UserSegment,
    UserSegmentMembership, ProductCollectionItem, ProductCollection,
    PersonalizedDiscount, RecommendationExplanation, Cart, CartItem, UserPreference
)

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'image', 'parent']

class ProductTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductTag
        fields = ['id', 'name']

class ProductAttributeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductAttribute
        fields = ['id', 'name', 'value', 'attribute_type']

class ProductRatingSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = ProductRating
        fields = ['id', 'username', 'rating', 'review', 'created_at']
        read_only_fields = ['user']

class RecommendationExplanationSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecommendationExplanation
        fields = [
            'id', 'explanation_type', 'explanation',
            'confidence_score', 'supporting_data', 'created_at'
        ]

class ProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer()
    average_rating = serializers.SerializerMethodField()
    ratings = ProductRatingSerializer(many=True, read_only=True)
    total_views = serializers.SerializerMethodField()
    tags = ProductTagSerializer(many=True, read_only=True)
    attributes = ProductAttributeSerializer(many=True, read_only=True)
    
    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'price', 'category', 'image', 
            'discount', 'rating', 'stock', 'average_rating', 'ratings', 
            'total_views', 'tags', 'attributes', 'created_at', 'updated_at'
        ]
    
    def get_average_rating(self, obj):
        return obj.ratings.aggregate(Avg('rating'))['rating__avg']
    
    def get_total_views(self, obj):
        return obj.views.count()

class UserInteractionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserInteraction
        fields = ['id', 'product', 'interaction_type', 'timestamp']
        read_only_fields = ['user', 'timestamp']

class RecommendationSerializer(serializers.ModelSerializer):
    product = ProductSerializer()
    explanations = RecommendationExplanationSerializer(many=True, read_only=True)
    
    class Meta:
        model = Recommendation
        fields = [
            'id', 'product', 'recommendation_type', 'score',
            'explanation', 'explanations', 'created_at'
        ]
        read_only_fields = ['user', 'created_at']

class ProductViewSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    
    class Meta:
        model = ProductView
        fields = ['id', 'product', 'product_name', 'view_count', 'last_viewed']
        read_only_fields = ['user', 'view_count', 'last_viewed']

class SearchHistorySerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    
    class Meta:
        model = SearchHistory
        fields = ['id', 'query', 'timestamp', 'results_count', 'category', 'category_name']
        read_only_fields = ['user', 'timestamp', 'results_count']

class PriceAlertSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    current_price = serializers.DecimalField(
        source='product.price',
        max_digits=10,
        decimal_places=2,
        read_only=True
    )
    
    class Meta:
        model = PriceAlert
        fields = [
            'id', 'product', 'product_name', 'current_price',
            'target_price', 'alert_type', 'is_active',
            'created_at', 'last_notified'
        ]
        read_only_fields = ['user', 'created_at', 'last_notified']

class RecentlyViewedSerializer(serializers.ModelSerializer):
    product = ProductSerializer()
    
    class Meta:
        model = RecentlyViewed
        fields = ['id', 'product', 'viewed_at']
        read_only_fields = ['user', 'viewed_at']

class SeasonalRecommendationSerializer(serializers.ModelSerializer):
    products = ProductSerializer(many=True, read_only=True)
    
    class Meta:
        model = SeasonalRecommendation
        fields = [
            'id', 'name', 'season_type', 'products',
            'start_date', 'end_date', 'is_active', 'priority'
        ]

class MLModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = MLModel
        fields = [
            'id', 'name', 'model_type', 'version',
            'is_active', 'accuracy', 'last_trained', 'metadata'
        ]

class MLPredictionSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    model_name = serializers.CharField(source='model.name', read_only=True)
    
    class Meta:
        model = MLPrediction
        fields = [
            'id', 'product', 'model_name', 'score',
            'confidence', 'created_at'
        ]
        read_only_fields = ['user', 'created_at']

class ABTestVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ABTestVariant
        fields = ['id', 'name', 'variant_type', 'description', 'configuration']

class ABTestSerializer(serializers.ModelSerializer):
    variants = ABTestVariantSerializer(many=True, read_only=True)
    
    class Meta:
        model = ABTest
        fields = [
            'id', 'name', 'description', 'status',
            'start_date', 'end_date', 'control_group_size',
            'variants', 'created_at', 'updated_at'
        ]

class UserSegmentSerializer(serializers.ModelSerializer):
    member_count = serializers.SerializerMethodField()
    
    class Meta:
        model = UserSegment
        fields = [
            'id', 'name', 'description', 'rules',
            'is_active', 'member_count', 'created_at', 'updated_at'
        ]
    
    def get_member_count(self, obj):
        return obj.usersegmentmembership_set.count()

class UserSegmentMembershipSerializer(serializers.ModelSerializer):
    segment_name = serializers.CharField(source='segment.name', read_only=True)
    
    class Meta:
        model = UserSegmentMembership
        fields = [
            'id', 'segment', 'segment_name',
            'score', 'joined_at', 'updated_at'
        ]
        read_only_fields = ['user', 'joined_at', 'updated_at']

class ProductCollectionItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer()
    
    class Meta:
        model = ProductCollectionItem
        fields = ['id', 'product', 'position', 'added_at']

class ProductCollectionSerializer(serializers.ModelSerializer):
    items = ProductCollectionItemSerializer(
        source='productcollectionitem_set',
        many=True,
        read_only=True
    )
    product_count = serializers.SerializerMethodField()
    
    class Meta:
        model = ProductCollection
        fields = [
            'id', 'name', 'description', 'collection_type',
            'is_active', 'start_date', 'end_date', 'rules',
            'items', 'product_count', 'created_at', 'updated_at'
        ]
    
    def get_product_count(self, obj):
        return obj.products.count()

class PersonalizedDiscountSerializer(serializers.ModelSerializer):
    segments = UserSegmentSerializer(many=True, read_only=True)
    products = ProductSerializer(many=True, read_only=True)
    collections = ProductCollectionSerializer(many=True, read_only=True)
    
    class Meta:
        model = PersonalizedDiscount
        fields = [
            'id', 'name', 'description', 'discount_type',
            'value', 'segments', 'products', 'collections',
            'min_purchase', 'start_date', 'end_date',
            'max_uses', 'current_uses', 'is_active',
            'rules', 'created_at'
        ]

class CartItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer()
    
    class Meta:
        model = CartItem
        fields = ['id', 'product', 'quantity', 'subtotal']

class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = Cart
        fields = ['id', 'user', 'items', 'total_price', 'created_at', 'updated_at']

class UserPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPreference
        fields = ['id', 'user', 'category', 'weight', 'last_interaction']

class RecommendationSerializer(serializers.ModelSerializer):
    product = ProductSerializer()
    
    class Meta:
        model = Recommendation
        fields = ['id', 'user', 'product', 'score', 'explanation', 'created_at']
