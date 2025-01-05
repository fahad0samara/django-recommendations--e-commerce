from django.core.management.base import BaseCommand
from recommendations.utils.scraper import EcommerceScraper
from django.core.management import call_command

class Command(BaseCommand):
    help = 'Scrapes product data and creates fixtures'

    def handle(self, *args, **kwargs):
        self.stdout.write('Starting data scraping...')
        
        # Run the scraper
        scraper = EcommerceScraper()
        fixture_data = scraper.save_to_fixtures()
        
        # Load the fixtures
        self.stdout.write('Loading fixtures...')
        call_command('loaddata', 'scraped_data.json')
        
        self.stdout.write(self.style.SUCCESS(f'Successfully scraped and loaded {len(fixture_data)} items'))
