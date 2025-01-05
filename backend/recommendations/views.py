from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from django.core.cache import cache
from datetime import datetime, timedelta
import numpy as np
from .models import Product, Cart, CartItem, Recommendation, UserPreference
from .serializers import (
    ProductSerializer,
    CartSerializer,
    CartItemSerializer,
    RecommendationSerializer,
    UserPreferenceSerializer
)

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

    def get_content_features(self, product):
        """Extract content features from product attributes"""
        features = {
            'category': product.category,
            'price': float(product.price),
            'name_tokens': set(product.name.lower().split()),
            'description_tokens': set(product.description.lower().split())
        }
        return features

    def calculate_similarity(self, features1, features2):
        """Calculate similarity between two products based on their features"""
        # Category similarity
        category_similarity = 1.0 if features1['category'] == features2['category'] else 0.0
        
        # Price similarity (normalized)
        price_diff = abs(features1['price'] - features2['price'])
        price_similarity = 1.0 / (1.0 + price_diff)
        
        # Text similarity using Jaccard similarity
        name_similarity = len(features1['name_tokens'].intersection(features2['name_tokens'])) / \
                         len(features1['name_tokens'].union(features2['name_tokens']))
        desc_similarity = len(features1['description_tokens'].intersection(features2['description_tokens'])) / \
                         len(features1['description_tokens'].union(features2['description_tokens']))
        
        # Weighted combination
        weights = {'category': 0.3, 'price': 0.2, 'name': 0.2, 'description': 0.3}
        total_similarity = (
            weights['category'] * category_similarity +
            weights['price'] * price_similarity +
            weights['name'] * name_similarity +
            weights['description'] * desc_similarity
        )
        return total_similarity

    @action(detail=True, methods=['get'])
    def similar_products(self, request, pk=None):
        """Get similar products based on content features"""
        product = self.get_object()
        cache_key = f'similar_products_{product.id}'
        
        # Try to get from cache first
        cached_results = cache.get(cache_key)
        if cached_results:
            return Response(cached_results)
        
        # Calculate similarities
        product_features = self.get_content_features(product)
        similar_products = []
        
        for other_product in Product.objects.exclude(id=product.id):
            other_features = self.get_content_features(other_product)
            similarity = self.calculate_similarity(product_features, other_features)
            similar_products.append({
                'product': ProductSerializer(other_product).data,
                'similarity': similarity,
                'explanation': self.generate_similarity_explanation(product, other_product, similarity)
            })
        
        # Sort by similarity
        similar_products.sort(key=lambda x: x['similarity'], reverse=True)
        
        # Cache the results for 24 hours
        cache.set(cache_key, similar_products[:5], 60*60*24)
        
        return Response(similar_products[:5])

    def generate_similarity_explanation(self, product1, product2, similarity):
        """Generate human-readable explanation for product similarity"""
        reasons = []
        
        if product1.category == product2.category:
            reasons.append(f"Both products are in the {product1.category} category")
        
        price_diff = abs(float(product1.price) - float(product2.price))
        if price_diff < 10:
            reasons.append("Products are in a similar price range")
        
        # Add more specific reasons based on features
        
        confidence = "high" if similarity > 0.8 else "medium" if similarity > 0.5 else "low"
        
        return {
            'reasons': reasons,
            'confidence': confidence,
            'similarity_score': round(similarity * 100, 2)
        }

class CartViewSet(viewsets.ModelViewSet):
    serializer_class = CartSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Cart.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class CartItemViewSet(viewsets.ModelViewSet):
    serializer_class = CartItemSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return CartItem.objects.filter(cart__user=self.request.user)

    def perform_create(self, serializer):
        cart, _ = Cart.objects.get_or_create(user=self.request.user)
        serializer.save(cart=cart)

class RecommendationViewSet(viewsets.ModelViewSet):
    serializer_class = RecommendationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Recommendation.objects.filter(user=self.request.user)

    @action(detail=False, methods=['get'])
    def personalized(self, request):
        """Get personalized recommendations based on user preferences and behavior"""
        user = request.user
        cache_key = f'personalized_recommendations_{user.id}'
        
        # Try to get from cache first
        cached_results = cache.get(cache_key)
        if cached_results:
            return Response(cached_results)
        
        # Get user preferences
        preferences = UserPreference.objects.filter(user=user)
        
        # Get user's purchase history
        cart_items = CartItem.objects.filter(cart__user=user)
        purchased_products = [item.product for item in cart_items]
        
        # Calculate recommendations
        recommendations = self.calculate_recommendations(user, preferences, purchased_products)
        
        # Cache the results for 6 hours
        cache.set(cache_key, recommendations, 60*60*6)
        
        return Response(recommendations)

    def calculate_recommendations(self, user, preferences, purchased_products):
        """Calculate personalized recommendations using a hybrid approach"""
        recommendations = []
        
        # Content-based filtering
        if preferences.exists():
            content_based_recs = self.get_content_based_recommendations(preferences)
            recommendations.extend(content_based_recs)
        
        # Collaborative filtering
        if purchased_products:
            collab_recs = self.get_collaborative_recommendations(user, purchased_products)
            recommendations.extend(collab_recs)
        
        # Add seasonal recommendations if available
        seasonal_recs = self.get_seasonal_recommendations()
        if seasonal_recs:
            recommendations.extend(seasonal_recs)
        
        # Remove duplicates and sort by confidence
        unique_recs = {}
        for rec in recommendations:
            product_id = rec['product']['id']
            if product_id not in unique_recs or rec['confidence'] > unique_recs[product_id]['confidence']:
                unique_recs[product_id] = rec
        
        sorted_recs = sorted(unique_recs.values(), key=lambda x: x['confidence'], reverse=True)
        return sorted_recs[:10]

    def get_content_based_recommendations(self, preferences):
        """Get recommendations based on user preferences"""
        recommendations = []
        
        for pref in preferences:
            similar_products = Product.objects.filter(
                Q(category=pref.preferred_category) |
                Q(price__range=(pref.min_price, pref.max_price))
            )
            
            for product in similar_products:
                confidence = self.calculate_preference_match(product, pref)
                if confidence > 0.5:  # Only include if confidence is above threshold
                    recommendations.append({
                        'product': ProductSerializer(product).data,
                        'confidence': confidence,
                        'source': 'content',
                        'explanation': f"Matches your preferences in {pref.preferred_category}"
                    })
        
        return recommendations

    def get_collaborative_recommendations(self, user, purchased_products):
        """Get recommendations based on similar users' purchases"""
        recommendations = []
        
        # Find users who bought similar products
        similar_users = Cart.objects.filter(
            items__product__in=purchased_products
        ).exclude(user=user).values('user').distinct()
        
        # Get products bought by similar users
        similar_user_products = CartItem.objects.filter(
            cart__user__in=similar_users
        ).exclude(
            product__in=purchased_products
        ).values('product').distinct()
        
        for product_data in similar_user_products:
            product = Product.objects.get(id=product_data['product'])
            confidence = self.calculate_collaborative_confidence(product, purchased_products)
            recommendations.append({
                'product': ProductSerializer(product).data,
                'confidence': confidence,
                'source': 'collaborative',
                'explanation': "Other users who bought similar products also bought this"
            })
        
        return recommendations

    def get_seasonal_recommendations(self):
        """Get seasonal recommendations based on current time"""
        current_month = datetime.now().month
        season_map = {
            (12, 1, 2): 'Winter',
            (3, 4, 5): 'Spring',
            (6, 7, 8): 'Summer',
            (9, 10, 11): 'Fall'
        }
        
        current_season = next(
            season for months, season in season_map.items() 
            if current_month in months
        )
        
        seasonal_products = Product.objects.filter(seasonal_category=current_season)
        
        return [{
            'product': ProductSerializer(product).data,
            'confidence': 0.7,  # Base confidence for seasonal recommendations
            'source': 'seasonal',
            'explanation': f"Popular during {current_season}"
        } for product in seasonal_products]

    def calculate_preference_match(self, product, preference):
        """Calculate how well a product matches user preferences"""
        score = 0.0
        weights = {'category': 0.6, 'price': 0.4}
        
        if product.category == preference.preferred_category:
            score += weights['category']
        
        if preference.min_price <= product.price <= preference.max_price:
            score += weights['price']
        
        return score

    def calculate_collaborative_confidence(self, product, purchased_products):
        """Calculate confidence score for collaborative filtering recommendations"""
        # Simple implementation - can be enhanced with more sophisticated algorithms
        base_confidence = 0.6
        category_matches = sum(1 for p in purchased_products if p.category == product.category)
        confidence_boost = min(0.3, category_matches * 0.1)
        return base_confidence + confidence_boost
from rest_framework import viewsets, status, filters, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404, render
from django.db.models import Count, Q
from django.utils import timezone
from django.db import transaction
from datetime import timedelta
from .models import (
    Product, UserInteraction, Recommendation,
    ProductRating, ProductView, SearchHistory,
    ProductTag, PriceAlert, RecentlyViewed, SeasonalRecommendation, MLPrediction,
    ABTest, UserSegment, ProductCollection, PersonalizedDiscount,
    RecommendationExplanation, Category, ProductCollectionItem, Discount, Cart, CartItem
)
from .engine import RecommendationEngine
from .serializers import (
    ProductSerializer, UserInteractionSerializer,
    RecommendationSerializer, ProductRatingSerializer,
    ProductViewSerializer, SearchHistorySerializer,
    ProductTagSerializer, PriceAlertSerializer, RecentlyViewedSerializer,
    SeasonalRecommendationSerializer, MLPredictionSerializer,
    ABTestSerializer, UserSegmentSerializer, ProductCollectionSerializer,
    PersonalizedDiscountSerializer, RecommendationExplanationSerializer,
    UserSegmentMembershipSerializer, ProductCollectionItemSerializer,
    CategorySerializer
)

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description', 'category__name', 'tags__name']
    ordering_fields = ['created_at', 'price', 'name', 'average_rating']
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        
        # Record product view and recently viewed
        if request.user.is_authenticated:
            # Update view count
            view, created = ProductView.objects.get_or_create(
                user=request.user,
                product=instance,
                defaults={'view_count': 1}
            )
            if not created:
                view.view_count += 1
                view.save()
            
            # Update recently viewed
            RecentlyViewed.objects.get_or_create(
                user=request.user,
                product=instance
            )
        
        serializer = self.get_serializer(instance)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def similar_products(self, request, pk=None):
        engine = RecommendationEngine()
        similar_products = engine.get_similar_products(pk)
        serializer = self.get_serializer(similar_products, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def frequently_bought_together(self, request, pk=None):
        engine = RecommendationEngine()
        products = engine.get_frequently_bought_together(pk)
        serializer = self.get_serializer(products, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def rate(self, request, pk=None):
        product = self.get_object()
        rating = request.data.get('rating')
        review = request.data.get('review', '')
        
        if not rating or not isinstance(rating, int) or rating < 1 or rating > 5:
            return Response(
                {'error': 'Please provide a valid rating between 1 and 5'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        rating_obj, created = ProductRating.objects.update_or_create(
            user=request.user,
            product=product,
            defaults={'rating': rating, 'review': review}
        )
        
        serializer = ProductRatingSerializer(rating_obj)
        return Response(serializer.data)
    
    @action(detail=True)
    def similar_by_attributes(self, request, pk=None):
        product = self.get_object()
        similar_products = Product.objects.filter(
            attributes__name__in=product.attributes.values_list('name', flat=True),
            attributes__value__in=product.attributes.values_list('value', flat=True)
        ).exclude(id=product.id).distinct()
        
        serializer = self.get_serializer(similar_products, many=True)
        return Response(serializer.data)
    
    @action(detail=True)
    def price_history(self, request, pk=None):
        # This is a placeholder for price history functionality
        # You would need to implement price tracking in a separate model
        return Response({"message": "Price history feature coming soon"})

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

class ProductCollectionViewSet(viewsets.ModelViewSet):
    queryset = ProductCollection.objects.all()
    serializer_class = ProductCollectionSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    
    @action(detail=True, methods=['post'])
    def add_product(self, request, pk=None):
        collection = self.get_object()
        product_id = request.data.get('product_id')
        position = request.data.get('position', 0)
        
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return Response(
                {'error': 'Product not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        item, created = ProductCollectionItem.objects.get_or_create(
            collection=collection,
            product=product,
            defaults={'position': position}
        )
        
        if not created:
            item.position = position
            item.save()
        
        serializer = ProductCollectionItemSerializer(item)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def reorder_products(self, request, pk=None):
        collection = self.get_object()
        product_positions = request.data.get('positions', [])
        
        with transaction.atomic():
            for pos_data in product_positions:
                ProductCollectionItem.objects.filter(
                    collection=collection,
                    product_id=pos_data['product_id']
                ).update(position=pos_data['position'])
        
        serializer = self.get_serializer(collection)
        return Response(serializer.data)

class RecommendationViewSet(viewsets.ModelViewSet):
    queryset = Recommendation.objects.all()
    serializer_class = RecommendationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Recommendation.objects.filter(user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def personalized(self, request):
        engine = RecommendationEngine()
        recommendations = engine.get_personalized_recommendations(request.user.id)
        
        # Add explanations to recommendations
        for rec in recommendations:
            explanation = RecommendationExplanation.objects.create(
                recommendation=rec,
                explanation_type='personalized',
                explanation='Based on your browsing and purchase history',
                confidence_score=0.85,
                supporting_data={
                    'user_interactions': UserInteraction.objects.filter(
                        user=request.user,
                        product=rec.product
                    ).count(),
                    'similar_users_purchased': True
                }
            )
        
        serializer = self.get_serializer(recommendations, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def trending(self, request):
        # Get trending products based on views and interactions in the last 7 days
        last_week = timezone.now() - timedelta(days=7)
        trending_products = Product.objects.filter(
            Q(views__last_viewed__gte=last_week) |
            Q(userinteraction__timestamp__gte=last_week)
        ).annotate(
            activity_count=Count('views') + Count('userinteraction')
        ).order_by('-activity_count')[:10]
        
        serializer = ProductSerializer(trending_products, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def category_recommendations(self, request):
        category_id = request.query_params.get('category_id')
        if not category_id:
            return Response(
                {'error': 'category_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get recommendations based on category and user's past interactions
        recommendations = Recommendation.objects.filter(
            user=request.user,
            product__category_id=category_id
        ).order_by('-score')[:10]
        
        serializer = self.get_serializer(recommendations, many=True)
        return Response(serializer.data)

class UserInteractionViewSet(viewsets.ModelViewSet):
    queryset = UserInteraction.objects.all()
    serializer_class = UserInteractionSerializer
    permission_classes = [IsAuthenticated]
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class ProductViewViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProductViewSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return ProductView.objects.filter(user=self.request.user)

class SearchHistoryViewSet(viewsets.ModelViewSet):
    serializer_class = SearchHistorySerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return SearchHistory.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(
            user=self.request.user,
            results_count=Product.objects.filter(
                Q(name__icontains=serializer.validated_data['query']) |
                Q(description__icontains=serializer.validated_data['query'])
            ).count()
        )

class ProductTagViewSet(viewsets.ModelViewSet):
    queryset = ProductTag.objects.all()
    serializer_class = ProductTagSerializer
    permission_classes = [IsAuthenticated]
    
    @action(detail=True)
    def products(self, request, pk=None):
        tag = self.get_object()
        products = tag.products.all()
        serializer = ProductSerializer(products, many=True)
        return Response(serializer.data)

class PriceAlertViewSet(viewsets.ModelViewSet):
    serializer_class = PriceAlertSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return PriceAlert.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
    
    @action(detail=False)
    def active(self, request):
        alerts = self.get_queryset().filter(is_active=True)
        serializer = self.get_serializer(alerts, many=True)
        return Response(serializer.data)

class RecentlyViewedViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = RecentlyViewedSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return RecentlyViewed.objects.filter(user=self.request.user)

class SeasonalRecommendationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SeasonalRecommendation.objects.filter(is_active=True)
    serializer_class = SeasonalRecommendationSerializer
    
    @action(detail=False)
    def current(self, request):
        today = timezone.now().date()
        current_seasons = self.queryset.filter(
            start_date__lte=today,
            end_date__gte=today
        ).order_by('-priority')
        serializer = self.get_serializer(current_seasons, many=True)
        return Response(serializer.data)

class MLPredictionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MLPredictionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return MLPrediction.objects.filter(
            user=self.request.user,
            model__is_active=True
        ).order_by('-score', '-confidence')
    
    @action(detail=False)
    def top_recommendations(self, request):
        limit = int(request.query_params.get('limit', 10))
        predictions = self.get_queryset()[:limit]
        serializer = self.get_serializer(predictions, many=True)
        return Response(serializer.data)

class ABTestViewSet(viewsets.ModelViewSet):
    queryset = ABTest.objects.all()
    serializer_class = ABTestSerializer
    
    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        test = self.get_object()
        if test.status != 'draft':
            return Response(
                {'error': 'Test can only be started from draft status'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        test.status = 'running'
        test.start_date = timezone.now()
        test.save()
        
        serializer = self.get_serializer(test)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        test = self.get_object()
        if test.status != 'running':
            return Response(
                {'error': 'Only running tests can be stopped'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        test.status = 'completed'
        test.end_date = timezone.now()
        test.save()
        
        serializer = self.get_serializer(test)
        return Response(serializer.data)

class UserSegmentViewSet(viewsets.ModelViewSet):
    queryset = UserSegment.objects.all()
    serializer_class = UserSegmentSerializer
    
    @action(detail=True)
    def members(self, request, pk=None):
        segment = self.get_object()
        memberships = segment.usersegmentmembership_set.all()
        serializer = UserSegmentMembershipSerializer(memberships, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def evaluate_users(self, request, pk=None):
        segment = self.get_object()
        # This would typically be a background task
        # For demo purposes, we'll do it synchronously
        users = User.objects.all()
        for user in users:
            score = self.evaluate_user_for_segment(user, segment)
            if score > 0:
                UserSegmentMembership.objects.update_or_create(
                    user=user,
                    segment=segment,
                    defaults={'score': score}
                )
        return Response({'status': 'User evaluation completed'})
    
    def evaluate_user_for_segment(self, user, segment):
        # This is a simplified example
        # In reality, you would evaluate the user against segment.rules
        return random.random()  # For demo purposes

class PersonalizedDiscountViewSet(viewsets.ModelViewSet):
    queryset = PersonalizedDiscount.objects.all()
    serializer_class = PersonalizedDiscountSerializer
    
    @action(detail=False)
    def available_for_user(self, request):
        if not request.user.is_authenticated:
            return Response([])
        
        now = timezone.now()
        user_segments = UserSegmentMembership.objects.filter(
            user=request.user
        ).values_list('segment_id', flat=True)
        
        discounts = self.queryset.filter(
            Q(segments__id__in=user_segments) |
            Q(segments__isnull=True),
            is_active=True,
            start_date__lte=now,
            end_date__gte=now,
            current_uses__lt=models.F('max_uses')
        ).distinct()
        
        serializer = self.get_serializer(discounts, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def apply_discount(self, request, pk=None):
        discount = self.get_object()
        product_id = request.data.get('product_id')
        
        if not discount.is_active:
            return Response(
                {'error': 'This discount is not active'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if discount.max_uses and discount.current_uses >= discount.max_uses:
            return Response(
                {'error': 'This discount has reached its usage limit'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return Response(
                {'error': 'Product not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Calculate discounted price
        original_price = product.price
        if discount.discount_type == 'percentage':
            discounted_price = original_price * (1 - discount.value / 100)
        else:  # fixed amount
            discounted_price = max(0, original_price - discount.value)
        
        return Response({
            'product_id': product.id,
            'original_price': original_price,
            'discounted_price': discounted_price,
            'savings': original_price - discounted_price
        })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.shortcuts import redirect
from django.contrib import messages
import json
from .models import Product, Cart, CartItem

@login_required
@require_POST
def add_to_cart(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    cart, created = Cart.objects.get_or_create(user=request.user)
    
    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        defaults={'quantity': 1}
    )
    
    if not created:
        cart_item.quantity += 1
        cart_item.save()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'message': f'{product.name} added to cart',
            'cart_total': float(cart.get_total()),
            'cart_items': cart.get_items_count()
        })
    
    messages.success(request, f'{product.name} added to cart')
    return redirect('products')

@login_required
@require_POST
def remove_from_cart(request, item_id):
    cart_item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
    cart = cart_item.cart
    cart_item.delete()
    
    return JsonResponse({
        'success': True,
        'message': 'Item removed from cart',
        'cart_total': float(cart.get_total()),
        'cart_items': cart.get_items_count()
    })

@login_required
@require_POST
def update_cart_quantity(request, item_id):
    cart_item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
    
    try:
        data = json.loads(request.body)
        quantity = int(data.get('quantity', 1))
        if quantity < 1:
            return JsonResponse({
                'success': False,
                'error': 'Quantity must be at least 1'
            }, status=400)
        
        cart_item.quantity = quantity
        cart_item.save()
        
        cart = cart_item.cart
        return JsonResponse({
            'success': True,
            'message': 'Cart updated',
            'cart_total': float(cart.get_total()),
            'cart_items': cart.get_items_count()
        })
    except (ValueError, json.JSONDecodeError):
        return JsonResponse({
            'success': False,
            'error': 'Invalid quantity'
        }, status=400)

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import Product, Cart, CartItem

@login_required
def get_recommendations(request):
    # Simple recommendation: return 4 random products
    products = Product.objects.order_by('?')[:4]
    recommendations = []
    for product in products:
        recommendations.append({
            'id': product.id,
            'name': product.name,
            'price': str(product.price),
            'description': product.description,
            'image_url': product.image.url if product.image else None,
        })
    return JsonResponse({'recommendations': recommendations})

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        cart, created = Cart.objects.get_or_create(user=request.user)
        
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': 1}
        )
        
        if not created:
            cart_item.quantity += 1
            cart_item.save()
        
        # Calculate cart total
        cart_total = sum(item.product.price * item.quantity for item in cart.items.all())
        cart_items = cart.items.count()
        
        return JsonResponse({
            'message': f'Added {product.name} to cart',
            'cart_total': f'{cart_total:.2f}',
            'cart_items': cart_items
        })
    
    return JsonResponse({'error': 'Invalid request method'}, status=400)

@login_required
def remove_from_cart(request, product_id):
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    cart_item.delete()
    
    return JsonResponse({
        'message': 'Item removed from cart',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

@login_required
def update_cart_item(request, product_id):
    try:
        quantity = int(request.POST.get('quantity', 1))
    except ValueError:
        return JsonResponse({'error': 'Invalid quantity'}, status=400)
    
    cart = get_object_or_404(Cart, user=request.user)
    cart_item = get_object_or_404(CartItem, cart=cart, product_id=product_id)
    
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        cart_item.delete()
    
    return JsonResponse({
        'message': 'Cart updated',
        'cart_total': str(cart.get_total()),
        'cart_items': cart.items.count(),
    })

from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
