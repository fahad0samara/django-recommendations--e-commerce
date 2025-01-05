import os
import requests
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from recommendations.models import Product, Category
from urllib.parse import urljoin
import random

class Command(BaseCommand):
    help = 'Scrapes products from Amazon and adds them to the database'

    def handle(self, *args, **options):
        # Create or get categories
        electronics = Category.objects.get_or_create(
            name='Electronics',
            description='Latest electronic gadgets and devices'
        )[0]
        
        fashion = Category.objects.get_or_create(
            name='Fashion',
            description='Trendy fashion items and accessories'
        )[0]
        
        home = Category.objects.get_or_create(
            name='Home & Living',
            description='Home decor and living essentials'
        )[0]

        # Headers to mimic a browser request
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        # Amazon product URLs
        urls = [
            # Electronics
            'https://www.amazon.com/Apple-Generation-Cancelling-Transparency-Personalized/dp/B0CHWRXH8B/',  # AirPods Pro
            'https://www.amazon.com/Apple-Watch-GPS-41mm-Midnight-Aluminum/dp/B0CHX3QBCH/',  # Apple Watch
            'https://www.amazon.com/Samsung-Factory-Unlocked-Smartphone-Processor/dp/B0CD1GJHW4/',  # Samsung Phone
            
            # Fashion
            'https://www.amazon.com/Ray-Ban-RB3025-Aviator-Sunglasses-Gold/dp/B0014CEVZ4/',  # Sunglasses
            'https://www.amazon.com/Nike-Running-Black-White-Regular/dp/B077ZYH6WZ/',  # Running Shoes
            'https://www.amazon.com/Herschel-Supply-Co-Classic-Backpack/dp/B0077BZ6GI/',  # Backpack
            
            # Home & Living
            'https://www.amazon.com/Philips-Equivalent-White-Dimmable-Assistant/dp/B07G1JH7YN/',  # Smart Bulb
            'https://www.amazon.com/Ninja-CE251-Programmable-Advanced-Technology/dp/B07S98411N/',  # Coffee Maker
            'https://www.amazon.com/Hydro-Flask-Standard-Mouth-Bottle/dp/B01ACAX2CM/'  # Water Bottle
        ]

        for url in urls:
            try:
                response = requests.get(url, headers=headers)
                soup = BeautifulSoup(response.content, 'html.parser')

                # Extract product information
                title = soup.select_one('#productTitle')
                title = title.text.strip() if title else 'Unknown Product'

                price_element = soup.select_one('.a-price-whole')
                price = float(price_element.text.replace(',', '')) if price_element else random.uniform(29.99, 299.99)

                description = soup.select_one('#feature-bullets')
                description = description.text.strip() if description else 'No description available'

                # Determine category based on URL keywords
                if any(keyword in url.lower() for keyword in ['airpods', 'watch', 'phone', 'electronics']):
                    category = electronics
                elif any(keyword in url.lower() for keyword in ['sunglasses', 'shoes', 'backpack', 'fashion']):
                    category = fashion
                else:
                    category = home

                # Create the product
                product = Product.objects.create(
                    name=title[:100],  # Limit title length
                    description=description[:500],  # Limit description length
                    price=price,
                    category=category,
                    discount=random.randint(0, 30) if random.random() > 0.5 else 0
                )

                # Try to get product image
                img_element = soup.select_one('#landingImage')
                if img_element and 'src' in img_element.attrs:
                    img_url = img_element['src']
                    try:
                        img_response = requests.get(img_url, headers=headers)
                        if img_response.status_code == 200:
                            product.image.save(
                                f"{product.name[:30]}.jpg",
                                ContentFile(img_response.content),
                                save=True
                            )
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f'Failed to save image for {title}: {str(e)}'))

                self.stdout.write(self.style.SUCCESS(f'Successfully added product: {title}'))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Failed to scrape {url}: {str(e)}'))

        self.stdout.write(self.style.SUCCESS('Product scraping completed!'))
