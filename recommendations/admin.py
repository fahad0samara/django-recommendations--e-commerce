from django.contrib import admin
from .models import Category, Product, UserInteraction, ProductSimilarity, Recommendation

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent')
    search_fields = ('name',)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'category', 'created_at')
    list_filter = ('category', 'created_at')
    search_fields = ('name', 'description')

@admin.register(UserInteraction)
class UserInteractionAdmin(admin.ModelAdmin):
    list_display = ('user', 'product', 'interaction_type', 'timestamp')
    list_filter = ('interaction_type', 'timestamp')
    search_fields = ('user__username', 'product__name')

@admin.register(ProductSimilarity)
class ProductSimilarityAdmin(admin.ModelAdmin):
    list_display = ('product_a', 'product_b', 'similarity_score', 'last_updated')
    list_filter = ('last_updated',)
    search_fields = ('product_a__name', 'product_b__name')

@admin.register(Recommendation)
class RecommendationAdmin(admin.ModelAdmin):
    list_display = ('user', 'product', 'recommendation_type', 'score', 'created_at')
    list_filter = ('recommendation_type', 'created_at')
    search_fields = ('user__username', 'product__name')
