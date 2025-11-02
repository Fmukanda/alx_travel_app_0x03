from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from .models import Listing, Booking, Review
from datetime import date, timedelta
import json
from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from .models import Payment
import logging

logger = logging.getLogger(__name__)

class ListingAPITestCase(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testhost', 
            email='host@example.com', 
            password='testpass123'
        )
        self.user2 = User.objects.create_user(
            username='testguest', 
            email='guest@example.com', 
            password='testpass123'
        )
        
        self.listing = Listing.objects.create(
            title="Beautiful Apartment in Paris",
            description="Stunning apartment with Eiffel Tower view",
            property_type="apartment",
            price_per_night=150.00,
            max_guests=4,
            bedrooms=2,
            beds=3,
            bathrooms=1,
            address="123 Paris Street",
            city="Paris",
            country="France",
            host=self.user
        )
        
        self.valid_listing_data = {
            "title": "Luxury Villa in Bali",
            "description": "Private villa with pool and ocean view",
            "property_type": "villa",
            "price_per_night": "300.00",
            "max_guests": 6,
            "bedrooms": 3,
            "beds": 4,
            "bathrooms": 2,
            "address": "456 Bali Road",
            "city": "Bali",
            "country": "Indonesia",
            "amenities": ["WiFi", "Pool", "Air Conditioning"]
        }

    def test_get_listings_unauthorized(self):
        """Test that anyone can view listings"""
        response = self.client.get('/api/listings/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_listing_authenticated(self):
        """Test creating listing as authenticated user"""
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            '/api/listings/',
            data=json.dumps(self.valid_listing_data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['host']['username'], 'testhost')

    def test_create_listing_unauthenticated(self):
        """Test that unauthenticated users cannot create listings"""
        response = self.client.post(
            '/api/listings/',
            data=json.dumps(self.valid_listing_data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_own_listing(self):
        """Test that host can update their own listing"""
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(
            f'/api/listings/{self.listing.id}/',
            data=json.dumps({"title": "Updated Title"}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Updated Title')

    def test_update_others_listing(self):
        """Test that users cannot update others' listings"""
        self.client.force_authenticate(user=self.user2)
        response = self.client.patch(
            f'/api/listings/{self.listing.id}/',
            data=json.dumps({"title": "Hacked Title"}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_filter_listings_by_city(self):
        """Test filtering listings by city"""
        response = self.client.get('/api/listings/?city=paris')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['city'], 'Paris')

    def test_filter_listings_by_price(self):
        """Test filtering listings by price range"""
        response = self.client.get('/api/listings/?min_price=100&max_price=200')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Our test listing is 150, so it should be included
        self.assertEqual(len(response.data['results']), 1)


class BookingAPITestCase(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.host = User.objects.create_user(
            username='testhost', 
            password='testpass123'
        )
        self.guest = User.objects.create_user(
            username='testguest', 
            password='testpass123'
        )
        self.other_user = User.objects.create_user(
            username='otheruser', 
            password='testpass123'
        )
        
        self.listing = Listing.objects.create(
            title="Test Listing",
            description="Test description",
            property_type="apartment",
            price_per_night=100.00,
            max_guests=4,
            bedrooms=1,
            beds=2,
            bathrooms=1,
            address="Test Address",
            city="Test City",
            country="Test Country",
            host=self.host
        )
        
        self.booking = Booking.objects.create(
            listing=self.listing,
            guest=self.guest,
            check_in=date.today() + timedelta(days=10),
            check_out=date.today() + timedelta(days=15),
            guests_count=2,
            status='confirmed'
        )
        
        self.valid_booking_data = {
            "listing": self.listing.id,
            "check_in": str(date.today() + timedelta(days=20)),
            "check_out": str(date.today() + timedelta(days=25)),
            "guests_count": 2,
            "special_requests": "Early check-in please"
        }

    def test_create_booking_authenticated(self):
        """Test creating booking as authenticated guest"""
        self.client.force_authenticate(user=self.guest)
        response = self.client.post(
            '/api/bookings/',
            data=json.dumps(self.valid_booking_data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['guest']['username'], 'testguest')

    def test_create_booking_unauthenticated(self):
        """Test that unauthenticated users cannot create bookings"""
        response = self.client.post(
            '/api/bookings/',
            data=json.dumps(self.valid_booking_data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_guest_can_view_own_bookings(self):
        """Test that guests can view their own bookings"""
        self.client.force_authenticate(user=self.guest)
        response = self.client.get('/api/bookings/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

    def test_host_can_view_listing_bookings(self):
        """Test that hosts can view bookings for their listings"""
        self.client.force_authenticate(user=self.host)
        response = self.client.get('/api/bookings/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

    def test_other_user_cannot_view_bookings(self):
        """Test that other users cannot view bookings"""
        self.client.force_authenticate(user=self.other_user)
        response = self.client.get('/api/bookings/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should see 0 bookings since they're not related
        self.assertEqual(len(response.data['results']), 0)

    def test_cancel_booking(self):
        """Test that guests can cancel their bookings"""
        self.client.force_authenticate(user=self.guest)
        response = self.client.post(f'/api/bookings/{self.booking.id}/cancel/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Refresh booking from database
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'cancelled')

    def test_booking_validation(self):
        """Test booking validation for invalid dates"""
        self.client.force_authenticate(user=self.guest)
        invalid_data = self.valid_booking_data.copy()
        invalid_data['check_in'] = str(date.today() + timedelta(days=25))
        invalid_data['check_out'] = str(date.today() + timedelta(days=20))  # Invalid
        
        response = self.client.post(
            '/api/bookings/',
            data=json.dumps(invalid_data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ErrorScenarioTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser', 
            password='testpass123'
        )
        
        self.listing = Listing.objects.create(
            title="Test Listing",
            description="Test description",
            property_type="apartment",
            price_per_night=100.00,
            max_guests=2,  # Small capacity
            bedrooms=1,
            beds=1,
            bathrooms=1,
            address="Test Address",
            city="Test City",
            country="Test Country",
            host=self.user
        )

    def test_booking_exceeds_guest_limit(self):
        """Test booking fails when guests exceed listing capacity"""
        self.client.force_authenticate(user=self.user)
        booking_data = {
            "listing": self.listing.id,
            "check_in": str(date.today() + timedelta(days=10)),
            "check_out": str(date.today() + timedelta(days=15)),
            "guests_count": 5,  # Exceeds max_guests=2
        }
        
        response = self.client.post(
            '/api/bookings/',
            data=json.dumps(booking_data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Maximum guests allowed', str(response.data))

    def test_booking_unavailable_listing(self):
        """Test booking fails for unavailable listings"""
        self.listing.is_available = False
        self.listing.save()
        
        self.client.force_authenticate(user=self.user)
        booking_data = {
            "listing": self.listing.id,
            "check_in": str(date.today() + timedelta(days=10)),
            "check_out": str(date.today() + timedelta(days=15)),
            "guests_count": 2,
        }
        
        response = self.client.post(
            '/api/bookings/',
            data=json.dumps(booking_data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('not available', str(response.data))

@shared_task
def send_payment_confirmation_email(payment_id, customer_email):
    """
    Send payment confirmation email asynchronously
    """
    try:
        payment = Payment.objects.get(id=payment_id)
        booking = payment.booking
        
        subject = f'Payment Confirmation - Booking #{booking.id}'
        
        html_message = render_to_string('emails/payment_confirmation.html', {
            'customer_name': f"{payment.customer_first_name} {payment.customer_last_name}",
            'booking': booking,
            'payment': payment,
            'listing': booking.listing,
        })
        
        plain_message = strip_tags(html_message)
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[customer_email],
            html_message=html_message,
            fail_silently=False,
        )
        
        logger.info(f"Payment confirmation email sent for payment {payment_id}")
        
    except Payment.DoesNotExist:
        logger.error(f"Payment {payment_id} not found for email sending")
    except Exception as e:
        logger.error(f"Failed to send payment confirmation email: {str(e)}")

@shared_task
def verify_pending_payments():
    """
    Periodic task to verify pending payments
    """
    from .services.chapa_service import ChapaService
    
    pending_payments = Payment.objects.filter(
        status__in=['pending', 'processing'],
        created_at__gte=timezone.now() - timezone.timedelta(hours=24)
    )
    
    chapa_service = ChapaService()
    
    for payment in pending_payments:
        if payment.chapa_transaction_id:
            result = chapa_service.verify_payment(payment.chapa_transaction_id)
            
            if result['success'] and result['status'] == 'success':
                payment.mark_as_paid()
                send_payment_confirmation_email.delay(payment.id, payment.customer_email)
