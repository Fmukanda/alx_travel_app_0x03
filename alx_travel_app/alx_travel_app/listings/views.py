from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import Listing, Booking, Review, Payment
from .serializers import (
    ListingSerializer, 
    BookingSerializer, 
    BookingCreateSerializer,
    ReviewSerializer,
    PaymentSerializer, 
    PaymentInitiationSerializer,
    PaymentVerificationSerializer
)
from django.contrib.auth.models import User
from .services.chapa_service import ChapaService
from .tasks import send_payment_confirmation_email
from .tasks import send_booking_confirmation_email, send_booking_status_update

class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it.
    """
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to the owner
        return obj.host == request.user


class IsGuestOrHost(permissions.BasePermission):
    """
    Custom permission to only allow guests or listing hosts to view bookings.
    """
    def has_object_permission(self, request, view, obj):
        # Guests can view their own bookings
        if obj.guest == request.user:
            return True
        
        # Hosts can view bookings for their listings
        if obj.listing.host == request.user:
            return True
        
        return False


class ListingViewSet(viewsets.ModelViewSet):
    """
    ViewSet for viewing and editing property listings.
    """
    queryset = Listing.objects.all()
    serializer_class = ListingSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsOwnerOrReadOnly]

    def get_queryset(self):
        """
        Optionally restricts the returned listings by filtering against
        query parameters in the URL.
        """
        queryset = Listing.objects.all()
        
        # Filter by city
        city = self.request.query_params.get('city', None)
        if city:
            queryset = queryset.filter(city__icontains=city)
        
        # Filter by country
        country = self.request.query_params.get('country', None)
        if country:
            queryset = queryset.filter(country__icontains=country)
        
        # Filter by property type
        property_type = self.request.query_params.get('property_type', None)
        if property_type:
            queryset = queryset.filter(property_type=property_type)
        
        # Filter by price range
        min_price = self.request.query_params.get('min_price', None)
        max_price = self.request.query_params.get('max_price', None)
        if min_price:
            queryset = queryset.filter(price_per_night__gte=min_price)
        if max_price:
            queryset = queryset.filter(price_per_night__lte=max_price)
        
        # Filter by guests
        guests = self.request.query_params.get('guests', None)
        if guests:
            queryset = queryset.filter(max_guests__gte=guests)
        
        # Filter by availability
        available = self.request.query_params.get('available', None)
        if available and available.lower() == 'true':
            queryset = queryset.filter(is_available=True)
        
        return queryset.select_related('host').prefetch_related('reviews')

    def perform_create(self, serializer):
        """
        Set the current user as the host when creating a listing.
        """
        serializer.save(host=self.request.user)

    @action(detail=True, methods=['get'])
    def bookings(self, request, pk=None):
        """
        Get all bookings for a specific listing.
        Only accessible by the listing host.
        """
        listing = self.get_object()
        
        if listing.host != request.user:
            return Response(
                {"detail": "You can only view bookings for your own listings."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        bookings = listing.bookings.all()
        serializer = BookingSerializer(bookings, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def reviews(self, request, pk=None):
        """
        Get all reviews for a specific listing.
        """
        listing = self.get_object()
        reviews = listing.reviews.all()
        serializer = ReviewSerializer(reviews, many=True)
        return Response(serializer.data)


class BookingViewSet(viewsets.ModelViewSet):
    """
    ViewSet for viewing and editing bookings.
    """
    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAuthenticated, IsGuestOrHost]

    def get_queryset(self):
        """
        Users can only see their own bookings or bookings for their listings.
        """
        user = self.request.user
        
        # Get bookings where user is guest OR user is host of the listing
        queryset = Booking.objects.filter(
            Q(guest=user) | Q(listing__host=user)
        ).select_related('listing', 'guest', 'listing__host')
        
        # Filter by status if provided
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by upcoming bookings
        upcoming = self.request.query_params.get('upcoming', None)
        if upcoming and upcoming.lower() == 'true':
            queryset = queryset.filter(check_in__gte=timezone.now().date())
        
        return queryset

    def get_serializer_class(self):
        """
        Use different serializers for creation and retrieval.
        """
        if self.action in ['create', 'update', 'partial_update']:
            return BookingCreateSerializer
        return BookingSerializer

    def perform_create(self, serializer):
        """
        Set the current user as the guest when creating a booking.
        """
        serializer.save(guest=self.request.user)

        # Send initial booking confirmation (pending status)
        send_booking_confirmation_email.delay(booking.id)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """
        Cancel a booking.
        """
        booking = self.get_object()
        
        if booking.guest != request.user:
            return Response(
                {"detail": "You can only cancel your own bookings."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if booking.status == 'cancelled':
            return Response(
                {"detail": "Booking is already cancelled."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        booking.status = 'cancelled'
        booking.save()
        
        serializer = self.get_serializer(booking)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """
        Confirm a booking (host only).
        """
        booking = self.get_object()
        
        if booking.listing.host != request.user:
            return Response(
                {"detail": "Only the host can confirm bookings."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if booking.status != 'pending':
            return Response(
                {"detail": "Only pending bookings can be confirmed."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        old_status = booking.status
        booking.status = 'confirmed'
        booking.save()
        
        # Send confirmation email asynchronously
        send_booking_confirmation_email.delay(booking.id)
        
        # Send status update email
        send_booking_status_update.delay(booking.id, old_status, 'confirmed')
        
        serializer = self.get_serializer(booking)
        return Response(serializer.data)


class ReviewViewSet(viewsets.ModelViewSet):
    """
    ViewSet for viewing and creating reviews.
    """
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Users can see all reviews, but we'll filter by listing if provided.
        """
        queryset = Review.objects.all()
        
        listing_id = self.request.query_params.get('listing', None)
        if listing_id:
            queryset = queryset.filter(listing_id=listing_id)
        
        return queryset.select_related('guest', 'listing')

    def perform_create(self, serializer):
        """
        Set the current user as the guest when creating a review.
        """
        serializer.save(guest=self.request.user)

class PaymentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for handling payment operations.
    """
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """
        Users can only see payments for their own bookings
        or payments for bookings on their listings
        """
        user = self.request.user
        return Payment.objects.filter(
            models.Q(booking__guest=user) | 
            models.Q(booking__listing__host=user)
        ).select_related('booking', 'booking__listing', 'booking__guest')
    
    @action(detail=False, methods=['post'])
    def initialize(self, request):
        """
        Initialize a payment for a booking
        """
        serializer = PaymentInitiationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        booking = get_object_or_404(Booking, id=serializer.validated_data['booking_id'])
        
        # Check permissions
        if booking.guest != request.user:
            return Response(
                {"detail": "You can only create payments for your own bookings."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if booking can be paid
        if booking.status != 'pending':
            return Response(
                {"detail": "This booking cannot be paid."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create payment record
        payment = Payment.objects.create(
            booking=booking,
            amount=booking.total_price,
            currency='ETB',
            payment_method=serializer.validated_data['payment_method'],
            customer_email=request.user.email,
            customer_first_name=request.user.first_name or 'Customer',
            customer_last_name=request.user.last_name or 'User',
        )
        
        # Initialize payment with Chapa
        chapa_service = ChapaService()
        
        payment_data = {
            'amount': float(payment.amount),
            'currency': payment.currency,
            'customer_email': payment.customer_email,
            'customer_first_name': payment.customer_first_name,
            'customer_last_name': payment.customer_last_name,
            'tx_ref': str(payment.id),
            'booking_ref': str(booking.id),
            'callback_url': request.build_absolute_uri('/api/payments/webhook/'),
            'return_url': request.build_absolute_uri(f'/bookings/{booking.id}/payment-complete/'),
        }
        
        result = chapa_service.initialize_payment(payment_data)
        
        if result['success']:
            payment.chapa_transaction_id = result['transaction_id']
            payment.chapa_checkout_url = result['checkout_url']
            payment.status = 'processing'
            payment.save()
            
            return Response({
                'payment_id': str(payment.id),
                'checkout_url': result['checkout_url'],
                'message': 'Payment initialized successfully'
            })
        else:
            payment.status = 'failed'
            payment.error_message = result['message']
            payment.save()
            
            return Response({
                'error': result['message']
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def verify(self, request):
        """
        Verify payment status
        """
        serializer = PaymentVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        transaction_id = serializer.validated_data['transaction_id']
        
        try:
            payment = Payment.objects.get(
                chapa_transaction_id=transaction_id,
                booking__guest=request.user
            )
        except Payment.DoesNotExist:
            return Response(
                {"detail": "Payment not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        chapa_service = ChapaService()
        verification_result = chapa_service.verify_payment(transaction_id)
        
        if verification_result['success']:
            if verification_result['status'] == 'success':
                payment.mark_as_paid()
                
                # Send confirmation email asynchronously
                send_payment_confirmation_email.delay(
                    payment.id,
                    request.user.email
                )
                
                return Response({
                    'status': 'completed',
                    'message': 'Payment verified successfully',
                    'payment': PaymentSerializer(payment).data
                })
            else:
                payment.status = 'failed'
                payment.error_message = f"Payment failed: {verification_result.get('message', 'Unknown error')}"
                payment.save()
                
                return Response({
                    'status': 'failed',
                    'message': 'Payment verification failed'
                }, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({
                'error': verification_result['message']
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        """
        Retry a failed payment
        """
        payment = self.get_object()
        
        if not payment.can_retry:
            return Response(
                {"detail": "This payment cannot be retried."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Reset payment for retry
        payment.status = 'pending'
        payment.retry_count += 1
        payment.save()
        
        # Re-initialize payment
        return self.initialize(request)
    
    @action(detail=False, methods=['post'], permission_classes=[permissions.AllowAny])
    def webhook(self, request):
        """
        Handle Chapa webhook notifications
        """
        chapa_service = ChapaService()
        
        # Verify webhook signature (implement based on Chapa documentation)
        signature = request.headers.get('Chapa-Signature')
        if not chapa_service.validate_webhook_signature(request.data, signature):
            return Response({'error': 'Invalid signature'}, status=status.HTTP_401_UNAUTHORIZED)
        
        event_type = request.data.get('event')
        transaction_id = request.data.get('tx_ref')
        
        try:
            payment = Payment.objects.get(chapa_transaction_id=transaction_id)
            
            if event_type == 'charge.completed':
                payment.mark_as_paid()
                send_payment_confirmation_email.delay(payment.id, payment.customer_email)
            
            elif event_type == 'charge.failed':
                payment.status = 'failed'
                payment.error_message = request.data.get('failure_message', 'Payment failed')
                payment.save()
            
            return Response({'status': 'webhook processed'})
            
        except Payment.DoesNotExist:
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)
