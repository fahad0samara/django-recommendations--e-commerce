import numpy as np
from scipy.sparse import csr_matrix
from sklearn.metrics.pairwise import cosine_similarity
from django.db.models import Count
from django.utils import timezone
from datetime import timedelta
from .models import Product, UserInteraction, ProductSimilarity, Recommendation

class RecommendationEngine:
    def __init__(self):
        self.similarity_matrix = None
        self.product_index = {}
        self.reverse_product_index = {}
    
    def build_interaction_matrix(self):
        """Build user-item interaction matrix"""
        interactions = UserInteraction.objects.values('user_id', 'product_id', 'interaction_type')
        
        # Create product index mapping
        products = Product.objects.all()
        self.product_index = {p.id: idx for idx, p in enumerate(products)}
        self.reverse_product_index = {idx: p_id for p_id, idx in self.product_index.items()}
        
        # Initialize matrices
        n_users = UserInteraction.objects.values('user_id').distinct().count()
        n_items = len(self.product_index)
        
        # Create sparse matrix
        rows, cols, data = [], [], []
        
        for interaction in interactions:
            user_idx = interaction['user_id']
            item_idx = self.product_index[interaction['product_id']]
            
            # Weight different interaction types
            weight = {
                'view': 1,
                'cart': 2,
                'wishlist': 3,
                'purchase': 4
            }.get(interaction['interaction_type'], 1)
            
            rows.append(user_idx)
            cols.append(item_idx)
            data.append(weight)
        
        return csr_matrix((data, (rows, cols)), shape=(n_users, n_items))
    
    def update_similarity_matrix(self):
        """Update item-item similarity matrix"""
        interaction_matrix = self.build_interaction_matrix()
        
        # Calculate item-item similarity
        self.similarity_matrix = cosine_similarity(interaction_matrix.T)
        
        # Update database
        batch_size = 1000
        similarities = []
        
        for i in range(len(self.similarity_matrix)):
            for j in range(i + 1, len(self.similarity_matrix)):
                if self.similarity_matrix[i, j] > 0:
                    similarities.append(
                        ProductSimilarity(
                            product_a_id=self.reverse_product_index[i],
                            product_b_id=self.reverse_product_index[j],
                            similarity_score=float(self.similarity_matrix[i, j])
                        )
                    )
                
                if len(similarities) >= batch_size:
                    ProductSimilarity.objects.bulk_create(
                        similarities, 
                        ignore_conflicts=True,
                        batch_size=batch_size
                    )
                    similarities = []
        
        if similarities:
            ProductSimilarity.objects.bulk_create(
                similarities,
                ignore_conflicts=True,
                batch_size=batch_size
            )
    
    def get_similar_products(self, product_id, n=5):
        """Get similar products for a given product"""
        return ProductSimilarity.objects.filter(
            product_a_id=product_id
        ).order_by('-similarity_score')[:n]
    
    def get_frequently_bought_together(self, product_id, n=5):
        """Get products frequently bought together"""
        # Find users who bought this product
        users = UserInteraction.objects.filter(
            product_id=product_id,
            interaction_type='purchase'
        ).values_list('user_id', flat=True)
        
        # Find other products these users bought
        return Product.objects.filter(
            userinteraction__user_id__in=users,
            userinteraction__interaction_type='purchase'
        ).exclude(
            id=product_id
        ).annotate(
            purchase_count=Count('id')
        ).order_by('-purchase_count')[:n]
    
    def get_personalized_recommendations(self, user_id, n=10):
        """Get personalized recommendations for a user"""
        # Get user's recent interactions
        recent_interactions = UserInteraction.objects.filter(
            user_id=user_id,
            timestamp__gte=timezone.now() - timedelta(days=30)
        ).select_related('product')
        
        # Calculate recommendation scores
        product_scores = {}
        
        for interaction in recent_interactions:
            similar_products = self.get_similar_products(interaction.product_id)
            
            for similar in similar_products:
                weight = {
                    'view': 1,
                    'cart': 2,
                    'wishlist': 3,
                    'purchase': 4
                }.get(interaction.interaction_type, 1)
                
                score = similar.similarity_score * weight
                product_scores[similar.product_b_id] = product_scores.get(similar.product_b_id, 0) + score
        
        # Sort and return top N recommendations
        sorted_products = sorted(
            product_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        recommendations = []
        for product_id, score in sorted_products[:n]:
            product = Product.objects.get(id=product_id)
            explanation = f"Based on your interest in similar products"
            
            recommendations.append(
                Recommendation(
                    user_id=user_id,
                    product=product,
                    recommendation_type='personal',
                    score=score,
                    explanation=explanation
                )
            )
        
        Recommendation.objects.bulk_create(recommendations)
        return recommendations
    
    def get_trending_products(self, n=10, days=7):
        """Get trending products based on recent interactions"""
        recent_date = timezone.now() - timedelta(days=days)
        
        return Product.objects.filter(
            userinteraction__timestamp__gte=recent_date
        ).annotate(
            interaction_count=Count('userinteraction')
        ).order_by('-interaction_count')[:n]
    
    def handle_cold_start(self, user_id=None, n=10):
        """Handle cold start problem for new users or products"""
        if user_id:
            # For new users, recommend popular products
            return Product.objects.filter(
                userinteraction__interaction_type='purchase'
            ).annotate(
                purchase_count=Count('id')
            ).order_by('-purchase_count')[:n]
        else:
            # For new products, recommend based on category
            return Product.objects.values('category').annotate(
                category_count=Count('id')
            ).order_by('-category_count')[:n]
