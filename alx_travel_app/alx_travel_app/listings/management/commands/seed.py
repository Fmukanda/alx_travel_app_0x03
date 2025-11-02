from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from listings.models import Listing, Booking, Review
from django.utils import timezone
from datetime import timedelta
import random


class Command(BaseCommand):
    help = 'Seed the database with sample travel booking data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing data before seeding',
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.clear_data()
        
        self.create_users()
        self.create_listings()
        self.create_bookings()
        self.create_reviews()
        
        self.stdout.write(
            self.style.SUCCESS('Successfully seeded the database!')
        )

    def clear_data(self):
        self.stdout.write('Clearing existing data...')
        Review.objects.all().delete()
        Booking.objects.all().delete()
        Listing.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()

    def create_users(self):
        self.stdout.write('Creating users...')
        
        users_data = [
            {'username': 'john_doe', 'email': 'john@example.com', 'first_name': 'John', 'last_name': 'Doe'},
            {'username': 'jane_smith', 'email': 'jane@example.com', 'first_name': 'Jane', 'last_name': 'Smith'},
            {'username': 'mike_wilson', 'email': 'mike@example.com', 'first_name': 'Mike', 'last_name': 'Wilson'},
            {'username': 'sarah_jones', 'email': 'sarah@example.com', 'first_name': 'Sarah', 'last_name': 'Jones'},
            {'username': 'david_brown', 'email': 'david@example.com', 'first_name': 'David', 'last_name': 'Brown'},
        ]
        
        for user_data in users_data:
            user, created = User.objects.get_or_create(
                username=user_data['username'],
                defaults=user_data
            )
            if created:
                user.set_password('password123')
                user.save()

    def create_listings(self):
        self.stdout.write('Creating listings...')
        
        hosts = User.objects.all()[:3]  # First 3 users will be hosts
        cities = [
            {'city': 'Paris', 'country': 'France'},
            {'city': 'Tokyo', 'country': 'Japan'},
            {'city': 'New York', 'country': 'USA'},
            {'city': 'Bali', 'country': 'Indonesia'},
            {'city': 'Rome', 'country': 'Italy'},
            {'city': 'Sydney', 'country': 'Australia'},
        ]
        
        property_types = ['apartment', 'house', 'villa', 'condo', 'hotel']
        amenities_options = [
            ['WiFi', 'Kitchen', 'Pool', 'Parking'],
            ['WiFi', 'Air Conditioning', 'TV', 'Heating'],
            ['WiFi', 'Gym', 'Hot Tub', 'Breakfast'],
            ['WiFi', 'Ocean View', 'Balcony', 'Fireplace'],
        ]
        
        listings_data = []
        
        for i, city_data in enumerate(cities):
            host = hosts[i % len(hosts)]
            listing = Listing.objects.create(
                title=f"Beautiful {property_types[i % len(property_types)]} in {city_data['city']}",
                description=f"Stunning {property_types[i % len(property_types)]} located in the heart of {city_data['city']}. Perfect for travelers looking for comfort and convenience.",
                property_type=property_types[i % len(property_types)],
                price_per_night=random.randint(80, 300),
                max_guests=random.randint(2, 8),
                bedrooms=random.randint(1, 4),
                beds=random.randint(1, 6),
                bathrooms=random.randint(1, 3),
                address=f"{random.randint(1, 999)} Main Street",
                city=city_data['city'],
                country=city_data['country'],
                latitude=random.uniform(-90, 90),
                longitude=random.uniform(-180, 180),
                amenities=random.choice(amenities_options),
                is_available=random.choice([True, True, True, False]),  # 75% available
                host=host,
            )
            listings_data.append(listing)

    def create_bookings(self):
        self.stdout.write('Creating bookings...')
        
        listings = Listing.objects.filter(is_available=True)
        guests = User.objects.all()[3:]  # Last 2 users will be guests
        
        if not listings.exists() or not guests.exists():
            self.stdout.write('No available listings or guests found')
            return
        
        status_choices = ['confirmed', 'completed', 'pending', 'cancelled']
        
        for i in range(15):  # Create 15 bookings
            listing = random.choice(listings)
            guest = random.choice(guests)
            
            # Generate random dates
            days_from_now = random.randint(1, 180)
            check_in = timezone.now().date() + timedelta(days=days_from_now)
            stay_duration = random.randint(2, 14)
            check_out = check_in + timedelta(days=stay_duration)
            
            # Ensure guest count doesn't exceed listing capacity
            guests_count = random.randint(1, min(6, listing.max_guests))
            
            Booking.objects.create(
                listing=listing,
                guest=guest,
                check_in=check_in,
                check_out=check_out,
                guests_count=guests_count,
                status=random.choice(status_choices),
                special_requests=random.choice([
                    "Early check-in if possible",
                    "Please provide extra towels",
                    "Traveling with a pet",
                    "Special occasion - anniversary",
                    "Need baby crib",
                    ""
                ])
            )

    def create_reviews(self):
        self.stdout.write('Creating reviews...')
        
        completed_bookings = Booking.objects.filter(status='completed')
        
        for booking in completed_bookings[:8]:  # Create reviews for 8 completed bookings
            Review.objects.create(
                listing=booking.listing,
                booking=booking,
                guest=booking.guest,
                rating=random.randint(3, 5),  # Mostly positive reviews
                comment=random.choice([
                    "Amazing stay! Would definitely recommend.",
                    "Great location and very comfortable.",
                    "Host was very responsive and helpful.",
                    "Beautiful property, exactly as described.",
                    "Perfect for our family vacation.",
                    "Loved the amenities and the neighborhood.",
                ])
            )
