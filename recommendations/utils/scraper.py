import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime, timedelta
import random
import os
from pathlib import Path

class EcommerceScraper:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.categories = [
            {
                'name': 'Electronics',
                'url': 'https://www.amazon.com/s?k=electronics&deals-widget=1',
                'image': 'electronics.jpg'
            },
            {
                'name': 'Fashion',
                'url': 'https://www.amazon.com/s?k=fashion&deals-widget=1',
                'image': 'fashion.jpg'
            },
            {
                'name': 'Home & Living',
                'url': 'https://www.amazon.com/s?k=home+and+living&deals-widget=1',
                'image': 'home.jpg'
            }
        ]

    def generate_sample_products(self):
        electronics_products = [
            {
                'name': 'Premium Wireless Earbuds',
                'description': 'High-quality wireless earbuds with noise cancellation',
                'price': 129.99,
                'image': 'earbuds.jpg',
                'rating': 4.5,
                'stock': 45
            },
            {
                'name': 'Smart Fitness Watch',
                'description': 'Track your health and stay connected',
                'price': 199.99,
                'image': 'smartwatch.jpg',
                'rating': 4.7,
                'stock': 30
            }
        ]
        
        fashion_products = [
            {
                'name': 'Classic Leather Backpack',
                'description': 'Stylish and durable everyday backpack',
                'price': 79.99,
                'image': 'backpack.jpg',
                'rating': 4.3,
                'stock': 25
            },
            {
                'name': 'Premium Sunglasses',
                'description': 'UV protection with modern design',
                'price': 149.99,
                'image': 'sunglasses.jpg',
                'rating': 4.6,
                'stock': 15
            }
        ]
        
        home_products = [
            {
                'name': 'Smart LED Light Bulbs',
                'description': 'Voice-controlled, multi-color LED bulbs',
                'price': 39.99,
                'image': 'bulbs.jpg',
                'rating': 4.4,
                'stock': 60
            },
            {
                'name': 'Premium Coffee Maker',
                'description': 'Programmable coffee maker with thermal carafe',
                'price': 159.99,
                'image': 'coffee-maker.jpg',
                'rating': 4.8,
                'stock': 20
            }
        ]
        
        products = []
        for category, items in [
            ('Electronics', electronics_products),
            ('Fashion', fashion_products),
            ('Home & Living', home_products)
        ]:
            for item in items:
                item['category'] = category
                products.append(item)
        
        return products

    def generate_discounts(self, products):
        discounts = []
        discount_types = ['percentage', 'fixed']
        
        # Generate featured discount
        featured_discount = {
            'name': 'Mega Tech Sale',
            'description': 'Exclusive discounts on premium electronics and gadgets',
            'discount_type': 'percentage',
            'value': random.randint(20, 40),
            'start_date': datetime.now().strftime('%Y-%m-%d'),
            'end_date': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
            'max_uses': 1000,
            'current_uses': random.randint(50, 200),
            'min_purchase': 199.99,
            'is_featured': True,
            'products': [p for p in products if p['category'] == 'Electronics'][:3]
        }
        discounts.append(featured_discount)
        
        # Generate category-specific discounts
        for category in self.categories:
            category_products = [p for p in products if p['category'] == category['name']]
            if category_products:
                discount = {
                    'name': f"Special {category['name']} Deals",
                    'description': f"Save big on {category['name'].lower()} items",
                    'discount_type': random.choice(discount_types),
                    'value': random.randint(10, 30) if random.choice(discount_types) == 'percentage' else random.randint(10, 50),
                    'start_date': datetime.now().strftime('%Y-%m-%d'),
                    'end_date': (datetime.now() + timedelta(days=random.randint(7, 60))).strftime('%Y-%m-%d'),
                    'max_uses': random.randint(100, 500),
                    'current_uses': random.randint(10, 50),
                    'min_purchase': round(random.uniform(50, 150), 2),
                    'is_featured': False,
                    'products': category_products[:2]
                }
                discounts.append(discount)
        
        return discounts

    def save_to_fixtures(self):
        products = self.generate_sample_products()
        discounts = self.generate_discounts(products)
        now = datetime.now().isoformat()
        
        fixture_data = []
        
        # Add categories
        for i, category in enumerate(self.categories, 1):
            fixture_data.append({
                'model': 'recommendations.category',
                'pk': i,
                'fields': {
                    'name': category['name'],
                    'description': f"Explore our {category['name'].lower()} collection",
                    'image': category['image'],
                    'created_at': now,
                    'updated_at': now
                }
            })
        
        # Add products
        for i, product in enumerate(products, 1):
            category_id = next(
                (i for i, cat in enumerate(self.categories, 1) 
                 if cat['name'] == product['category']), 1
            )
            fixture_data.append({
                'model': 'recommendations.product',
                'pk': i,
                'fields': {
                    'name': product['name'],
                    'description': product['description'],
                    'price': str(product['price']),
                    'image': product['image'],
                    'category': category_id,
                    'rating': product['rating'],
                    'stock': product['stock'],
                    'created_at': now,
                    'updated_at': now
                }
            })
        
        # Add discounts
        for i, discount in enumerate(discounts, 1):
            discount_data = {
                'model': 'recommendations.discount',
                'pk': i,
                'fields': {
                    'name': discount['name'],
                    'description': discount['description'],
                    'discount_type': discount['discount_type'],
                    'value': str(discount['value']),
                    'start_date': discount['start_date'],
                    'end_date': discount['end_date'],
                    'max_uses': discount['max_uses'],
                    'current_uses': discount['current_uses'],
                    'min_purchase': str(discount['min_purchase']),
                    'is_featured': discount['is_featured'],
                    'created_at': now,
                    'updated_at': now
                }
            }
            
            # Add product relations after saving
            if i == 1:  # Featured discount
                discount_data['fields']['products'] = [1, 2]  # First two electronics products
            else:
                category_index = i - 2  # Adjust for 0-based index and featured discount
                if category_index < len(self.categories):
                    start_pk = category_index * 2 + 1
                    discount_data['fields']['products'] = [start_pk, start_pk + 1]
            
            fixture_data.append(discount_data)
        
        # Save to fixtures file
        fixtures_dir = Path(__file__).resolve().parent.parent / 'fixtures'
        fixtures_dir.mkdir(exist_ok=True)
        
        with open(fixtures_dir / 'scraped_data.json', 'w', encoding='utf-8') as f:
            json.dump(fixture_data, f, indent=4, ensure_ascii=False)
        
        print(f"Saved {len(fixture_data)} items to fixtures")
        return fixture_data

if __name__ == '__main__':
    scraper = EcommerceScraper()
    scraper.save_to_fixtures()
