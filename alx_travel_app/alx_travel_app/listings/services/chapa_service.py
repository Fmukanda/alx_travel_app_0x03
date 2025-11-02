import requests
import json
import logging
from django.conf import settings
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

class ChapaService:
    def __init__(self):
        self.secret_key = settings.CHAPA_SECRET_KEY
        self.base_url = settings.CHAPA_BASE_URL
        self.headers = {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json',
        }
    
    def initialize_payment(self, payment_data):
        """
        Initialize payment with Chapa
        """
        try:
            url = f"{self.base_url}/transaction/initialize"
            
            payload = {
                'amount': str(payment_data['amount']),
                'currency': payment_data.get('currency', 'ETB'),
                'email': payment_data['customer_email'],
                'first_name': payment_data['customer_first_name'],
                'last_name': payment_data['customer_last_name'],
                'phone_number': payment_data.get('customer_phone', ''),
                'tx_ref': str(payment_data['tx_ref']),
                'callback_url': payment_data.get('callback_url', ''),
                'return_url': payment_data.get('return_url', ''),
                'customization': {
                    'title': 'Travel Booking Payment',
                    'description': f'Payment for booking {payment_data["booking_ref"]}',
                }
            }
            
            response = requests.post(url, json=payload, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if data['status'] == 'success':
                return {
                    'success': True,
                    'checkout_url': data['data']['checkout_url'],
                    'transaction_id': data['data']['tx_ref'],
                }
            else:
                return {
                    'success': False,
                    'message': data.get('message', 'Payment initialization failed'),
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Chapa API request failed: {str(e)}")
            return {
                'success': False,
                'message': f'Payment gateway error: {str(e)}',
            }
        except Exception as e:
            logger.error(f"Unexpected error in initialize_payment: {str(e)}")
            return {
                'success': False,
                'message': 'An unexpected error occurred',
            }
    
    def verify_payment(self, transaction_id):
        """
        Verify payment status with Chapa
        """
        try:
            url = f"{self.base_url}/transaction/verify/{transaction_id}"
            
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if data['status'] == 'success':
                transaction_data = data['data']
                return {
                    'success': True,
                    'status': transaction_data['status'],
                    'amount': float(transaction_data['amount']),
                    'currency': transaction_data['currency'],
                    'charged_amount': float(transaction_data.get('charged_amount', 0)),
                    'fee': float(transaction_data.get('fee', 0)),
                    'raw_response': transaction_data,
                }
            else:
                return {
                    'success': False,
                    'message': data.get('message', 'Verification failed'),
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Chapa verification request failed: {str(e)}")
            return {
                'success': False,
                'message': f'Verification error: {str(e)}',
            }
        except Exception as e:
            logger.error(f"Unexpected error in verify_payment: {str(e)}")
            return {
                'success': False,
                'message': 'An unexpected error occurred during verification',
            }
    
    def validate_webhook_signature(self, payload, signature):
        """
        Validate webhook signature for security
        """
        # Implement webhook signature validation
        # This is a simplified version - implement based on Chapa's webhook docs
        expected_signature = settings.CHAPA_WEBHOOK_SECRET
        return signature == expected_signature
