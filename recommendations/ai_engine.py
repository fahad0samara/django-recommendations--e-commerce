import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from django.db.models import Count, Avg, F, Q
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
from .models import (
    Product, UserInteraction, Recommendation, 
    SeasonalRecommendation, ProductAttribute,
    RecommendationExplanation, UserSegment,
    ProductSimilarity
)

class AIRecommendationEngine:
    def __init__(self):
        self.tfidf = TfidfVectorizer(
            stop_words='english',
            ngram_range=(1, 2),  # Consider bigrams
            max_features=5000    # Limit features for better performance
        )
        
    def prepare_content_features(self):
        """Prepare content features using product descriptions and attributes"""
        cache_key = 'content_features'
        cached_data = cache.get(cache_key)
        
        if cached_data:
            return cached_data
            
        products = Product.objects.prefetch_related('tags', 'attributes', 'category').all()
        
        # Enhanced feature creation
        descriptions = []
        for p in products:
            # Combine multiple sources of text data with appropriate weighting
            features = [
                p.name * 3,  # Weight name more heavily
                p.description,
                p.category.name * 2,
                ' '.join([t.name * 2 for t in p.tags.all()]),
                ' '.join([f"{a.name}_{a.value}" for a in p.attributes.all()])
            ]
            descriptions.append(' '.join(features))
            
        features = self.tfidf.fit_transform(descriptions)
        
        # Cache the results for 1 hour
        cache.set(cache_key, (features, products), 3600)
        
        return features, products
        
    def get_user_preferences(self, user_id):
        """Get user preferences based on interactions with time decay"""
        cache_key = f'user_preferences_{user_id}'
        cached_prefs = cache.get(cache_key)
        
        if cached_prefs:
            return cached_prefs
            
        # Calculate time-based weights
        now = timezone.now()
        recent_window = now - timedelta(days=7)
        month_window = now - timedelta(days=30)
        
        preferences = UserInteraction.objects.filter(
            user_id=user_id
        ).annotate(
            time_weight=Case(
                When(created_at__gte=recent_window, then=2.0),
                When(created_at__gte=month_window, then=1.5),
                default=1.0,
                output_field=FloatField(),
            ),
            weighted_score=(
                F('time_weight') * (
                    Count('id') + 
                    Coalesce(F('rating'), 0) * 2 +
                    Case(
                        When(interaction_type='purchase', then=3),
                        When(interaction_type='cart', then=2),
                        When(interaction_type='wishlist', then=1.5),
                        default=1,
                        output_field=FloatField(),
                    )
                )
            )
        ).values('product').annotate(
            interaction_score=Avg('weighted_score')
        ).order_by('-interaction_score')
        
        # Cache for 15 minutes
        cache.set(cache_key, preferences, 900)
        
        return preferences
        
    def get_similar_products(self, product_id, n=5):
        """Find similar products based on content and collaborative data"""
        cache_key = f'similar_products_{product_id}_{n}'
        cached_similar = cache.get(cache_key)
        
        if cached_similar:
            return cached_similar
            
        # Get pre-computed similarities
        similar_products = list(ProductSimilarity.objects.filter(
            product_a_id=product_id
        ).select_related('product_b').order_by('-similarity_score')[:n])
        
        if not similar_products:
            # Fallback to content-based similarity
            features, products = self.prepare_content_features()
            product_idx = [i for i, p in enumerate(products) if p.id == product_id][0]
            similarities = cosine_similarity(features[product_idx:product_idx+1], features).flatten()
            similar_indices = similarities.argsort()[-n-1:-1][::-1]
            similar_products = [products[i] for i in similar_indices if products[i].id != product_id]
            
            # Store similarities for future use
            ProductSimilarity.objects.bulk_create([
                ProductSimilarity(
                    product_a_id=product_id,
                    product_b=products[i],
                    similarity_score=similarities[i]
                ) for i in similar_indices if products[i].id != product_id
            ])
        
        # Cache for 1 hour
        cache.set(cache_key, similar_products, 3600)
        
        return similar_products
        
    def get_collaborative_recommendations(self, user_id, n=5):
        """Get recommendations based on similar users with seasonal adjustments"""
        cache_key = f'collab_recommendations_{user_id}_{n}'
        cached_recs = cache.get(cache_key)
        
        if cached_recs:
            return cached_recs
            
        user_prefs = self.get_user_preferences(user_id)
        if not user_prefs:
            return []
            
        # Find similar users considering user segments
        user_segments = UserSegment.objects.filter(
            usersegmentmembership__user_id=user_id
        ).values_list('id', flat=True)
        
        similar_users = UserInteraction.objects.filter(
            Q(product__in=user_prefs.values_list('product', flat=True)) |
            Q(user__usersegmentmembership__segment_id__in=user_segments)
        ).exclude(
            user_id=user_id
        ).values(
            'user'
        ).annotate(
            similarity=Count('id')
        ).order_by('-similarity')[:10]
        
        # Get current seasonal recommendations
        current_season = SeasonalRecommendation.objects.filter(
            start_date__lte=timezone.now(),
            end_date__gte=timezone.now(),
            is_active=True
        ).first()
        
        # Get products liked by similar users with seasonal boost
        recommended_products = Product.objects.filter(
            userinteraction__user__in=[u['user'] for u in similar_users]
        ).exclude(
            userinteraction__user_id=user_id
        ).annotate(
            rec_score=Count('userinteraction') * (
                Case(
                    When(seasonal_recommendations=current_season, then=1.5),
                    default=1.0,
                    output_field=FloatField(),
                )
            )
        ).order_by('-rec_score')[:n]
        
        # Cache for 30 minutes
        cache.set(cache_key, recommended_products, 1800)
        
        return recommended_products
        
    def get_personalized_recommendations(self, user_id, n=8):
        """Get hybrid recommendations with explanations"""
        # Get collaborative recommendations
        collab_recs = self.get_collaborative_recommendations(user_id, n=n//2)
        
        # Get content-based recommendations from user's most interacted products
        user_prefs = self.get_user_preferences(user_id)
        content_recs = []
        if user_prefs:
            for pref in user_prefs[:3]:
                content_recs.extend(
                    self.get_similar_products(pref['product'], n=2)
                )
        
        # Get seasonal recommendations
        seasonal_recs = SeasonalRecommendation.objects.filter(
            start_date__lte=timezone.now(),
            end_date__gte=timezone.now(),
            is_active=True
        ).prefetch_related('products').first()
        
        # Combine all recommendations with scoring
        all_recs = []
        seen_ids = set()
        
        def add_recommendation(product, score, explanation_type, explanation):
            if product.id not in seen_ids and len(all_recs) < n:
                all_recs.append({
                    'product': product,
                    'score': score,
                    'explanation_type': explanation_type,
                    'explanation': explanation
                })
                seen_ids.add(product.id)
        
        # Add collaborative recommendations
        for product in collab_recs:
            add_recommendation(
                product,
                0.8,
                'similar_users',
                'Based on products that similar users have enjoyed'
            )
        
        # Add content-based recommendations
        for product in content_recs:
            add_recommendation(
                product,
                0.6,
                'similar_products',
                'Similar to products you have shown interest in'
            )
        
        # Add seasonal recommendations
        if seasonal_recs:
            for product in seasonal_recs.products.all():
                add_recommendation(
                    product,
                    0.7,
                    'seasonal',
                    f'Perfect for the current {seasonal_recs.season_type} season'
                )
        
        # Sort by score and create recommendations
        all_recs.sort(key=lambda x: x['score'], reverse=True)
        final_recs = []
        
        for rec in all_recs[:n]:
            recommendation = Recommendation.objects.create(
                user_id=user_id,
                product=rec['product'],
                recommendation_type='personal',
                score=rec['score']
            )
            
            RecommendationExplanation.objects.create(
                recommendation=recommendation,
                explanation_type=rec['explanation_type'],
                explanation=rec['explanation'],
                confidence_score=rec['score']
            )
            
            final_recs.append(rec['product'])
        
        return final_recs
