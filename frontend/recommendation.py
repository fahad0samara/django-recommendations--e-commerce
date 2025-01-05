from .models import Product, ProductView

class RecommendationEngine:
    @staticmethod
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
    
    @staticmethod
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
