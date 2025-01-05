from django.core.management.base import BaseCommand
from django.core.files import File
from recommendations.models import Product
import os
import shutil

class Command(BaseCommand):
    help = 'Setup product images'

    def handle(self, *args, **kwargs):
        # Image mapping
        image_mapping = {
            'earbuds': 'earbuds.jpg',
            'watch': 'smartwatch.jpg',
            'backpack': 'backpack.jpg',
            'sunglasses': 'fashion.jpg',
            'light': 'home.jpg',
            'coffee': 'home.jpg',
            'bottle': 'home.jpg',
            'shoes': 'fashion.jpg',
        }

        # Source directory for images
        src_dir = os.path.join('frontend', 'static', 'images')
        # Destination directory for media
        media_dir = os.path.join('media', 'products')
        os.makedirs(media_dir, exist_ok=True)

        # Copy images and update products
        for keyword, image_name in image_mapping.items():
            # Copy image to media directory
            src_path = os.path.join(src_dir, image_name)
            if os.path.exists(src_path):
                dst_path = os.path.join(media_dir, f'product_{image_name}')
                shutil.copy2(src_path, dst_path)
                
                # Update products containing the keyword
                products = Product.objects.filter(name__icontains=keyword)
                for product in products:
                    product.image = f'products/product_{image_name}'
                    product.save()
                    self.stdout.write(f'Updated image for product: {product.name}')
