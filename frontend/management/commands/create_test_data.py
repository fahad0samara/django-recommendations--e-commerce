from django.core.management.base import BaseCommand
from frontend.models import Category, Product
from django.core.files import File
import os
import requests
import tempfile

class Command(BaseCommand):
    help = 'Creates test data for the store'

    def download_image(self, url):
        """Download image from URL and return as Django File object"""
        try:
            response = requests.get(url)
            if response.status_code == 200:
                # Create a temporary file
                temp_file = tempfile.NamedTemporaryFile()
                # Write the content
                temp_file.write(response.content)
                temp_file.seek(0)
                return temp_file
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Failed to download image: {str(e)}'))
        return None

    def handle(self, *args, **kwargs):
        # Create categories
        categories = {
            'Electronics': 'Latest gadgets and electronic devices',
            'Clothing': 'Fashion items and accessories',
            'Books': 'Books of all genres',
            'Home & Garden': 'Items for your home and garden',
            'Sports': 'Sports equipment and accessories'
        }

        for name, desc in categories.items():
            Category.objects.get_or_create(name=name, description=desc)

        # Get categories
        electronics = Category.objects.get(name='Electronics')
        clothing = Category.objects.get(name='Clothing')
        books = Category.objects.get(name='Books')
        home = Category.objects.get(name='Home & Garden')
        sports = Category.objects.get(name='Sports')

        # Products data with Unsplash images
        products_data = [
            {
                'name': 'Sony WH-1000XM4 Wireless Headphones',
                'description': 'Industry-leading noise canceling with Dual Noise Sensor technology',
                'price': 349.99,
                'original_price': 399.99,
                'category': electronics,
                'stock': 50,
                'featured': True,
                'image_url': 'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=800'
            },
            {
                'name': 'Apple Watch Series 7',
                'description': 'Always-On Retina display, GPS, Heart Rate Monitoring',
                'price': 399.99,
                'original_price': 429.99,
                'category': electronics,
                'stock': 30,
                'featured': True,
                'image_url': 'https://images.unsplash.com/photo-1579586337278-3befd40fd17a?w=800'
            },
            {
                'name': 'Levi\'s Men\'s Trucker Jacket',
                'description': 'Classic denim jacket with modern styling',
                'price': 69.99,
                'original_price': 89.99,
                'category': clothing,
                'stock': 100,
                'featured': True,
                'image_url': 'https://images.unsplash.com/photo-1495105787522-5334e3ffa0ef?w=800'
            },
            {
                'name': 'Python Crash Course, 2nd Edition',
                'description': 'A hands-on, project-based introduction to programming',
                'price': 29.99,
                'original_price': 39.99,
                'category': books,
                'stock': 75,
                'featured': False,
                'image_url': 'https://images.unsplash.com/photo-1532012197267-da84d127e765?w=800'
            },
            {
                'name': 'WORKPRO Garden Tools Set',
                'description': '12-Piece Garden Tool Set with Carrying Case',
                'price': 49.99,
                'original_price': 69.99,
                'category': home,
                'stock': 40,
                'featured': True,
                'image_url': 'https://images.unsplash.com/photo-1617576683096-00fc8eecb3af?w=800'
            },
            {
                'name': 'Gaiam Essentials Premium Yoga Mat',
                'description': '72"L x 24"W x 1/4 Inch Thick Premium Exercise & Fitness Mat',
                'price': 24.99,
                'original_price': 34.99,
                'category': sports,
                'stock': 60,
                'featured': False,
                'image_url': 'https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=800'
            }
        ]

        # Create products
        for data in products_data:
            product, created = Product.objects.get_or_create(
                name=data['name'],
                defaults={
                    'description': data['description'],
                    'price': data['price'],
                    'original_price': data['original_price'],
                    'category': data['category'],
                    'stock': data['stock'],
                    'featured': data['featured']
                }
            )
            
            if created:
                # Download and save the image
                temp_file = self.download_image(data['image_url'])
                if temp_file:
                    try:
                        # Generate a unique filename
                        image_name = f"{product.id}_{data['name'].lower().replace(' ', '_')}.jpg"
                        # Save the image to the product
                        product.image.save(image_name, File(temp_file), save=True)
                        self.stdout.write(self.style.SUCCESS(f'Created product: {product.name} with image'))
                    finally:
                        temp_file.close()
                else:
                    self.stdout.write(self.style.WARNING(f'Created product: {product.name} without image'))

        self.stdout.write(self.style.SUCCESS('Successfully created test data'))
