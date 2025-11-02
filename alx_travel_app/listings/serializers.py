from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Listing, Booking, Review, Payment


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']


class ReviewSerializer(serializers.ModelSerializer):
    guest = UserSerializer(read_only=True)
    
    class Meta:
        model = Review
        fields = ['id', 'guest', 'rating', 'comment', 'created_at']
        read_only_fields = ['guest', 'created_at']


class ListingSerializer(serializers.ModelSerializer):
    host = UserSerializer(read_only=True)
    average_rating = serializers.ReadOnlyField()
    reviews = ReviewSerializer(many=True, read_only=True)
    
    class Meta:
        model = Listing
        fields = [
            'id', 'title', 'description', 'property_type', 'price_per_night',
            'max_guests', 'bedrooms', 'beds', 'bathrooms', 'address', 'city',
            'country', 'latitude', 'longitude', 'amenities', 'is_available',
            'host', 'average_rating', 'reviews', 'created_at'
        ]
        read_only_fields = ['host', 'created_at']


class BookingSerializer(serializers.ModelSerializer):
    guest = UserSerializer(read_only=True)
    listing = ListingSerializer(read_only=True)
    listing_id = serializers.PrimaryKeyRelatedField(
        queryset=Listing.objects.all(), 
        source='listing',
        write_only=True
    )
    
    class Meta:
        model = Booking
        fields = [
            'id', 'listing', 'listing_id', 'guest', 'check_in', 'check_out',
            'guests_count', 'total_price', 'status', 'special_requests',
            'created_at'
        ]
        read_only_fields = ['guest', 'total_price', 'created_at']
    
    def validate(self, data):
        # Validate check-in/check-out dates
        if data['check_in'] >= data['check_out']:
            raise serializers.ValidationError(
                "Check-out date must be after check-in date"
            )
        
        # Validate guests count
        if data['guests_count'] > data['listing'].max_guests:
            raise serializers.ValidationError(
                f"Maximum guests allowed is {data['listing'].max_guests}"
            )
        
        # Check if listing is available
        if not data['listing'].is_available:
            raise serializers.ValidationError("This listing is not available")
        
        return data


class BookingCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = [
            'listing', 'check_in', 'check_out', 'guests_count', 
            'special_requests'
        ]


class PaymentSerializer(serializers.ModelSerializer):
    booking_details = serializers.SerializerMethodField()
    
    class Meta:
        model = Payment
        fields = [
            'id', 'amount', 'currency', 'status', 'payment_method',
            'chapa_transaction_id', 'chapa_checkout_url', 'created_at',
            'paid_at', 'customer_email', 'customer_first_name',
            'customer_last_name', 'booking_details'
        ]
        read_only_fields = [
            'id', 'chapa_transaction_id', 'chapa_checkout_url', 
            'created_at', 'paid_at', 'status'
        ]
    
    def get_booking_details(self, obj):
        from .serializers import BookingSerializer
        return BookingSerializer(obj.booking).data

class PaymentInitiationSerializer(serializers.Serializer):
    booking_id = serializers.UUIDField()
    payment_method = serializers.ChoiceField(
        choices=Payment.PAYMENT_METHOD_CHOICES,
        default='chapa'
    )
    
    def validate_booking_id(self, value):
        from .models import Booking
        try:
            booking = Booking.objects.get(id=value)
            if hasattr(booking, 'payment'):
                raise serializers.ValidationError("Payment already exists for this booking")
            return value
        except Booking.DoesNotExist:
            raise serializers.ValidationError("Booking not found")

class PaymentVerificationSerializer(serializers.Serializer):
    transaction_id = serializers.CharField(max_length=100)
