from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from recommendations.models import (
    Category, Product, ProductTag, ProductAttribute,
    ProductRating, ProductCollection, ProductCollectionItem,
    UserSegment, UserSegmentMembership, PersonalizedDiscount,
    Recommendation, RecommendationExplanation
)
import random
from datetime import timedelta
from decimal import Decimal

class Command(BaseCommand):
    help = 'Generates test data for the recommendation system'

    def handle(self, *args, **kwargs):
        self.stdout.write('Creating test data...')
        
        # Create test user if not exists
        user, created = User.objects.get_or_create(
            username='testuser',
            email='test@example.com'
        )
        if created:
            user.set_password('testpass123')
            user.save()
            self.stdout.write(self.style.SUCCESS('Created test user: testuser/testpass123'))

        # Create categories
        categories = [
            'Electronics',
            'Books',
            'Clothing',
            'Home & Garden',
            'Sports & Outdoors'
        ]
        category_objects = []
        for cat_name in categories:
            category, created = Category.objects.get_or_create(name=cat_name)
            category_objects.append(category)
            if created:
                self.stdout.write(f'Created category: {cat_name}')

        # Create product tags
        tags = [
            'New', 'Bestseller', 'Sale', 'Limited Edition',
            'Eco-friendly', 'Premium', 'Trending', 'Featured'
        ]
        tag_objects = []
        for tag_name in tags:
            tag, created = ProductTag.objects.get_or_create(name=tag_name)
            tag_objects.append(tag)
            if created:
                self.stdout.write(f'Created tag: {tag_name}')

        # Create products
        products_data = [
            {
                'name': 'Smart Watch Pro',
                'description': 'Advanced smartwatch with health tracking features',
                'category': 'Electronics',
                'price': '199.99',
                'tags': ['New', 'Featured', 'Premium'],
            },
            {
                'name': 'Python Programming Guide',
                'description': 'Comprehensive guide to Python programming',
                'category': 'Books',
                'price': '49.99',
                'tags': ['Bestseller', 'Featured'],
            },
            {
                'name': 'Wireless Earbuds',
                'description': 'High-quality wireless earbuds with noise cancellation',
                'category': 'Electronics',
                'price': '149.99',
                'tags': ['Trending', 'Premium'],
            },
            {
                'name': 'Eco-friendly Water Bottle',
                'description': 'Sustainable water bottle made from recycled materials',
                'category': 'Home & Garden',
                'price': '24.99',
                'tags': ['Eco-friendly', 'Featured'],
            },
            {
                'name': 'Running Shoes',
                'description': 'Professional running shoes with advanced cushioning',
                'category': 'Sports & Outdoors',
                'price': '129.99',
                'tags': ['New', 'Premium'],
            },
        ]

        product_objects = []
        for prod_data in products_data:
            category = Category.objects.get(name=prod_data['category'])
            product, created = Product.objects.get_or_create(
                name=prod_data['name'],
                defaults={
                    'description': prod_data['description'],
                    'category': category,
                    'price': Decimal(prod_data['price']),
                }
            )
            if created:
                # Add tags
                for tag_name in prod_data['tags']:
                    tag = ProductTag.objects.get(name=tag_name)
                    product.tags.add(tag)
                
                # Add attributes
                ProductAttribute.objects.create(
                    product=product,
                    name='Color',
                    value=random.choice(['Black', 'White', 'Blue', 'Red']),
                    attribute_type='text'
                )
                ProductAttribute.objects.create(
                    product=product,
                    name='Weight',
                    value=str(random.randint(100, 1000)),
                    attribute_type='number'
                )

                # Add ratings
                for _ in range(random.randint(3, 8)):
                    try:
                        ProductRating.objects.create(
                            product=product,
                            user=User.objects.order_by('?').first(),  # Get a random user
                            rating=random.randint(3, 5),
                            review=f'Great product! Rating: {random.randint(3, 5)} stars.'
                        )
                    except:
                        continue  # Skip if rating already exists

                product_objects.append(product)
                self.stdout.write(f'Created product: {product.name}')

        # Create collections
        collection_types = ['featured', 'seasonal', 'trending']
        for collection_type in collection_types:
            collection, created = ProductCollection.objects.get_or_create(
                name=f'{collection_type.title()} Collection',
                defaults={
                    'description': f'A collection of {collection_type} products',
                    'collection_type': collection_type,
                    'is_active': True,
                    'start_date': timezone.now(),
                    'end_date': timezone.now() + timedelta(days=30),
                }
            )
            if created:
                # Add random products to collection
                for product in random.sample(product_objects, min(3, len(product_objects))):
                    ProductCollectionItem.objects.create(
                        collection=collection,
                        product=product,
                        position=random.randint(0, 10)
                    )
                self.stdout.write(f'Created collection: {collection.name}')

        # Create user segments
        segment_types = ['premium', 'regular', 'new']
        for segment_type in segment_types:
            segment, created = UserSegment.objects.get_or_create(
                name=f'{segment_type.title()} Users',
                defaults={
                    'description': f'Segment for {segment_type} users',
                    'rules': {'type': segment_type},
                    'is_active': True,
                }
            )
            if created:
                # Add test user to segment
                UserSegmentMembership.objects.create(
                    user=user,
                    segment=segment,
                    score=random.random()
                )
                self.stdout.write(f'Created segment: {segment.name}')

        # Create personalized discounts
        discount_types = ['percentage', 'fixed']
        for i in range(5):
            discount_type = random.choice(discount_types)
            value = random.randint(10, 50) if discount_type == 'percentage' else random.randint(5, 30)
            discount, created = PersonalizedDiscount.objects.get_or_create(
                name=f'Special Offer {i+1}',
                defaults={
                    'description': f'Get {value}{"%" if discount_type == "percentage" else "$"} off!',
                    'discount_type': discount_type,
                    'value': value,
                    'is_active': True,
                    'start_date': timezone.now(),
                    'end_date': timezone.now() + timedelta(days=random.randint(7, 30)),
                    'max_uses': random.randint(50, 200),
                    'current_uses': 0,
                }
            )
            if created:
                # Add random products and segments
                discount.products.set(random.sample(product_objects, min(2, len(product_objects))))
                discount.segments.set(UserSegment.objects.all())
                self.stdout.write(f'Created discount: {discount.name}')

        # Create recommendations
        recommendation_types = ['personalized', 'trending', 'similar']
        for product in product_objects:
            for rec_type in recommendation_types:
                recommendation, created = Recommendation.objects.get_or_create(
                    user=user,
                    product=product,
                    defaults={
                        'recommendation_type': rec_type,
                        'score': random.random(),
                        'explanation': f'Recommended based on your {rec_type} preferences',
                    }
                )
                if created:
                    # Add explanation
                    RecommendationExplanation.objects.create(
                        recommendation=recommendation,
                        explanation_type=rec_type,
                        explanation=f'This product matches your {rec_type} preferences',
                        confidence_score=random.random(),
                        supporting_data={
                            'reason': f'{rec_type.title()} match',
                            'score': random.random()
                        }
                    )
                    self.stdout.write(f'Created recommendation: {recommendation.product.name} ({rec_type})')

        self.stdout.write(self.style.SUCCESS('Successfully created test data'))
