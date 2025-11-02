from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.contrib.auth.models import User
from .models import Booking, Listing
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_booking_confirmation_email(self, booking_id, recipient_email=None):
    """
    Send a booking confirmation email to the guest.
    
    Args:
        booking_id (int): The ID of the booking
        recipient_email (str, optional): Email address to send to. 
                                       If not provided, uses booking guest's email.
    """
    try:
        # Get the booking object with related data
        booking = Booking.objects.select_related(
            'guest', 
            'listing', 
            'listing__host'
        ).get(id=booking_id)
        
        # Use provided email or fall back to guest's email
        if not recipient_email:
            recipient_email = booking.guest.email
        
        # Prepare email context
        context = {
            'booking': booking,
            'guest_name': f"{booking.guest.first_name} {booking.guest.last_name}".strip() or booking.guest.username,
            'host_name': f"{booking.listing.host.first_name} {booking.listing.host.last_name}".strip() or booking.listing.host.username,
            'listing_title': booking.listing.title,
            'check_in': booking.check_in.strftime('%B %d, %Y'),
            'check_out': booking.check_out.strftime('%B %d, %Y'),
            'total_nights': (booking.check_out - booking.check_in).days,
            'total_price': booking.total_price,
            'booking_id': booking.id,
            'property_address': f"{booking.listing.city}, {booking.listing.country}",
            'support_email': getattr(settings, 'DEFAULT_SUPPORT_EMAIL', 'support@yourapp.com'),
            'site_name': getattr(settings, 'SITE_NAME', 'Booking App'),
        }
        
        # Render email templates
        subject = f"Booking Confirmation - {booking.listing.title}"
        
        # HTML content
        html_message = render_to_string('emails/booking_confirmation.html', context)
        
        # Plain text content (fallback)
        plain_message = strip_tags(html_message)
        
        # Send email using Django's email backend
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            html_message=html_message,
            fail_silently=False,
        )
        
        logger.info(f"Booking confirmation email sent to {recipient_email} for booking {booking_id}")
        
        # Also send notification to host (chain the tasks)
        send_booking_notification_to_host.delay(booking_id)
        
        return {
            'status': 'success',
            'message': f"Booking confirmation email sent successfully to {recipient_email}",
            'booking_id': booking_id
        }
        
    except Booking.DoesNotExist:
        error_msg = f"Error: Booking with ID {booking_id} does not exist"
        logger.error(error_msg)
        return {'status': 'error', 'message': error_msg}
    except Exception as e:
        error_msg = f"Error sending booking confirmation email: {str(e)}"
        logger.error(error_msg)
        
        # Retry the task
        try:
            raise self.retry(exc=e, countdown=60)
        except self.MaxRetriesExceededError:
            return {'status': 'error', 'message': error_msg, 'max_retries_exceeded': True}

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_booking_notification_to_host(self, booking_id):
    """
    Send a notification email to the host about the new booking.
    """
    try:
        booking = Booking.objects.select_related(
            'guest', 
            'listing', 
            'listing__host'
        ).get(id=booking_id)
        
        host_email = booking.listing.host.email
        
        context = {
            'booking': booking,
            'guest_name': f"{booking.guest.first_name} {booking.guest.last_name}".strip() or booking.guest.username,
            'host_name': f"{booking.listing.host.first_name} {booking.listing.host.last_name}".strip() or booking.listing.host.username,
            'listing_title': booking.listing.title,
            'check_in': booking.check_in.strftime('%B %d, %Y'),
            'check_out': booking.check_out.strftime('%B %d, %Y'),
            'total_nights': (booking.check_out - booking.check_in).days,
            'total_price': booking.total_price,
            'booking_id': booking.id,
            'guest_email': booking.guest.email,
            'site_name': getattr(settings, 'SITE_NAME', 'Booking App'),
        }
        
        subject = f"New Booking - {booking.listing.title}"
        
        html_message = render_to_string('emails/booking_notification_host.html', context)
        plain_message = strip_tags(html_message)
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[host_email],
            html_message=html_message,
            fail_silently=False,
        )
        
        logger.info(f"Booking notification sent to host {host_email} for booking {booking_id}")
        
        return {
            'status': 'success',
            'message': f"Booking notification sent to host {host_email}",
            'booking_id': booking_id
        }
        
    except Exception as e:
        error_msg = f"Error sending booking notification to host: {str(e)}"
        logger.error(error_msg)
        
        try:
            raise self.retry(exc=e, countdown=60)
        except self.MaxRetriesExceededError:
            return {'status': 'error', 'message': error_msg, 'max_retries_exceeded': True}

@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def send_booking_status_update(self, booking_id, old_status, new_status):
    """
    Send email when booking status changes (confirmed, cancelled, etc.)
    """
    try:
        booking = Booking.objects.select_related('guest', 'listing').get(id=booking_id)
        
        context = {
            'booking': booking,
            'guest_name': f"{booking.guest.first_name} {booking.guest.last_name}".strip() or booking.guest.username,
            'listing_title': booking.listing.title,
            'old_status': old_status,
            'new_status': new_status,
            'check_in': booking.check_in.strftime('%B %d, %Y'),
            'check_out': booking.check_out.strftime('%B %d, %Y'),
            'booking_id': booking.id,
            'site_name': getattr(settings, 'SITE_NAME', 'Booking App'),
        }
        
        if new_status == 'confirmed':
            subject = f"Booking Confirmed - {booking.listing.title}"
            template = 'emails/booking_confirmed.html'
        elif new_status == 'cancelled':
            subject = f"Booking Cancelled - {booking.listing.title}"
            template = 'emails/booking_cancelled.html'
        else:
            subject = f"Booking Status Update - {booking.listing.title}"
            template = 'emails/booking_status_update.html'
        
        html_message = render_to_string(template, context)
        plain_message = strip_tags(html_message)
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[booking.guest.email],
            html_message=html_message,
            fail_silently=False,
        )
        
        logger.info(f"Booking status update email sent for booking {booking_id}")
        
        return {
            'status': 'success',
            'message': f"Booking status update email sent for booking {booking_id}",
            'booking_id': booking_id,
            'status_change': f"{old_status} -> {new_status}"
        }
        
    except Exception as e:
        error_msg = f"Error sending booking status update: {str(e)}"
        logger.error(error_msg)
        
        try:
            raise self.retry(exc=e, countdown=30)
        except self.MaxRetriesExceededError:
            return {'status': 'error', 'message': error_msg, 'max_retries_exceeded': True}

# Add the payment confirmation email task mentioned in your views
@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_payment_confirmation_email(self, payment_id, customer_email):
    """
    Send payment confirmation email (mentioned in your PaymentViewSet)
    """
    try:
        from .models import Payment
        
        payment = Payment.objects.select_related('booking', 'booking__listing').get(id=payment_id)
        
        context = {
            'payment': payment,
            'booking': payment.booking,
            'customer_name': f"{payment.customer_first_name} {payment.customer_last_name}",
            'amount': payment.amount,
            'currency': payment.currency,
            'transaction_id': payment.chapa_transaction_id,
            'site_name': getattr(settings, 'SITE_NAME', 'Booking App'),
        }
        
        subject = f"Payment Confirmation - {payment.booking.listing.title}"
        
        html_message = render_to_string('emails/payment_confirmation.html', context)
        plain_message = strip_tags(html_message)
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[customer_email],
            html_message=html_message,
            fail_silently=False,
        )
        
        logger.info(f"Payment confirmation email sent to {customer_email} for payment {payment_id}")
        
        return {
            'status': 'success',
            'message': f"Payment confirmation email sent to {customer_email}",
            'payment_id': payment_id
        }
        
    except Exception as e:
        error_msg = f"Error sending payment confirmation email: {str(e)}"
        logger.error(error_msg)
        
        try:
            raise self.retry(exc=e, countdown=60)
        except self.MaxRetriesExceededError:
            return {'status': 'error', 'message': error_msg, 'max_retries_exceeded': True}