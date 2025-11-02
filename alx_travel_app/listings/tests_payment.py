from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from .models import Listing, Booking, Payment
from datetime import date, timedelta
import json
from unittest.mock import patch, MagicMock

class PaymentAPITestCase(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser', 
            email='test@example.com', 
            password='testpass123'
        )
        
        self.host = User.objects.create_user(
            username='testhost', 
            email='host@example.com', 
            password='testpass123'
        )
        
        self.listing = Listing.objects.create(
            title="Test Listing",
            description="Test description",
            property_type="apartment",
            price_per_night=100.00,
            max_guests=4,
            bedrooms=2,
            beds=3,
            bathrooms=1,
            address="Test Address",
            city="Test City",
            country="Test Country",
            host=self.host
        )
        
        self.booking = Booking.objects.create(
            listing=self.listing,
            guest=self.user,
            check_in=date.today() + timedelta(days=10),
            check_out=date.today() + timedelta(days=15),
            guests_count=2,
            status='pending',
            total_price=500.00
        )

    @patch('listings.services.chapa_service.ChapaService.initialize_payment')
    def test_initialize_payment_success(self, mock_initialize):
        """Test successful payment initialization"""
        mock_initialize.return_value = {
            'success': True,
            'checkout_url': 'https://checkout.chapa.co/test',
            'transaction_id': 'test_tx_123'
        }
        
        self.client.force_authenticate(user=self.user)
        
        response = self.client.post(
            '/api/payments/initialize/',
            data=json.dumps({'booking_id': str(self.booking.id)}),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('checkout_url', response.data)
        
        # Verify payment record was created
        payment = Payment.objects.get(booking=self.booking)
        self.assertEqual(payment.status, 'processing')
        self.assertEqual(payment.chapa_transaction_id, 'test_tx_123')

    @patch('listings.services.chapa_service.ChapaService.initialize_payment')
    def test_initialize_payment_failure(self, mock_initialize):
        """Test payment initialization failure"""
        mock_initialize.return_value = {
            'success': False,
            'message': 'Insufficient funds'
        }
        
        self.client.force_authenticate(user=self.user)
        
        response = self.client.post(
            '/api/payments/initialize/',
            data=json.dumps({'booking_id': str(self.booking.id)}),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        
        # Verify payment record was marked as failed
        payment = Payment.objects.get(booking=self.booking)
        self.assertEqual(payment.status, 'failed')

    @patch('listings.services.chapa_service.ChapaService.verify_payment')
    def test_verify_payment_success(self, mock_verify):
        """Test successful payment verification"""
        # Create a payment first
        payment = Payment.objects.create(
            booking=self.booking,
            amount=500.00,
            currency='ETB',
            customer_email=self.user.email,
            customer_first_name='Test',
            customer_last_name='User',
            chapa_transaction_id='test_tx_123',
            status='processing'
        )
        
        mock_verify.return_value = {
            'success': True,
            'status': 'success',
            'amount': 500.00,
            'currency': 'ETB'
        }
        
        self.client.force_authenticate(user=self.user)
        
        response = self.client.post(
            '/api/payments/verify/',
            data=json.dumps({'transaction_id': 'test_tx_123'}),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'completed')
        
        # Refresh payment from database
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'completed')
        self.assertIsNotNone(payment.paid_at)

    def test_webhook_processing(self):
        """Test webhook payment processing"""
        payment = Payment.objects.create(
            booking=self.booking,
            amount=500.00,
            currency='ETB',
            customer_email=self.user.email,
            customer_first_name='Test',
            customer_last_name='User',
            chapa_transaction_id='test_tx_123',
            status='processing'
        )
        
        webhook_data = {
            'event': 'charge.completed',
            'tx_ref': 'test_tx_123',
            'amount': '500.00',
            'currency': 'ETB'
        }
        
        response = self.client.post(
            '/api/payments/webhook/',
            data=json.dumps(webhook_data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Refresh payment from database
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'completed')

class PaymentWorkflowTest(APITestCase):
    def test_complete_payment_workflow(self):
        """Test complete payment workflow from booking to confirmation"""
        # This would be an integration test covering the entire flow
        pass
