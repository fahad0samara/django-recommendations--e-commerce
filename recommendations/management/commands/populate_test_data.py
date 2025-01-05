from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from recommendations.models import Category, Product, UserInteraction
from django.utils import timezone
import random

class Command(BaseCommand):
    help = 'Populate database with test data'

    def handle(self, *args, **kwargs):
        # Create test user if not exists
        test_user, created = User.objects.get_or_create(
            username='testuser',
            email='test@example.com'
        )
        if created:
            test_user.set_password('testpass123')
            test_user.save()
            self.stdout.write(self.style.SUCCESS('Created test user'))

        # Create categories
        categories = [
            {'name': 'Electronics', 'parent': None},
            {'name': 'Books', 'parent': None},
            {'name': 'Clothing', 'parent': None},
        ]

        for cat_data in categories:
            category, created = Category.objects.get_or_create(
                name=cat_data['name'],
                parent=cat_data['parent']
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created category {category.name}'))

        # Create subcategories
        electronics = Category.objects.get(name='Electronics')
        subcategories = [
            {'name': 'Smartphones', 'parent': electronics},
            {'name': 'Laptops', 'parent': electronics},
            {'name': 'Accessories', 'parent': electronics},
        ]

        for subcat_data in subcategories:
            category, created = Category.objects.get_or_create(
                name=subcat_data['name'],
                parent=subcat_data['parent']
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created subcategory {category.name}'))

        # Create products
        smartphones = Category.objects.get(name='Smartphones')
        products = [
            {
                'name': 'iPhone 15 Pro',
                'description': 'Latest iPhone with advanced features',
                'price': 999.99,
                'category': smartphones
            },
            {
                'name': 'Samsung Galaxy S24',
                'description': 'Premium Android smartphone',
                'price': 899.99,
                'category': smartphones
            },
            {
                'name': 'Google Pixel 8',
                'description': 'Pure Android experience',
                'price': 799.99,
                'category': smartphones
            },
        ]

        for prod_data in products:
            product, created = Product.objects.get_or_create(
                name=prod_data['name'],
                defaults={
                    'description': prod_data['description'],
                    'price': prod_data['price'],
                    'category': prod_data['category']
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created product {product.name}'))

        # Create user interactions
        products = Product.objects.all()
        interaction_types = ['view', 'cart', 'wishlist', 'purchase']

        for product in products:
            for _ in range(random.randint(1, 5)):  # Random number of interactions per product
                interaction_type = random.choice(interaction_types)
                UserInteraction.objects.create(
                    user=test_user,
                    product=product,
                    interaction_type=interaction_type
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Created {interaction_type} interaction for {product.name}'
                    )
                )
