from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
import uuid


class Listing(models.Model):
    PROPERTY_TYPES = [
        ('apartment', 'Apartment'),
        ('house', 'House'),
        ('villa', 'Villa'),
        ('condo', 'Condo'),
        ('cabin', 'Cabin'),
        ('hotel', 'Hotel'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField()
    property_type = models.CharField(max_length=20, choices=PROPERTY_TYPES)
    price_per_night = models.DecimalField(max_digits=10, decimal_places=2)
    max_guests = models.PositiveIntegerField()
    bedrooms = models.PositiveIntegerField()
    beds = models.PositiveIntegerField()
    bathrooms = models.PositiveIntegerField()
    address = models.TextField()
    city = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    amenities = models.JSONField(default=list)  # Store as list of strings
    is_available = models.BooleanField(default=True)
    host = models.ForeignKey(User, on_delete=models.CASCADE, related_name='listings')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.title} - {self.city}"
    
    @property
    def average_rating(self):
        reviews = self.reviews.all()
        if reviews:
            return sum(review.rating for review in reviews) / len(reviews)
        return 0
    
    class Meta:
        ordering = ['-created_at']


class Booking(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ]
    
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='bookings')
    guest = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings')
    check_in = models.DateField()
    check_out = models.DateField()
    guests_count = models.PositiveIntegerField()
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    special_requests = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.guest.username} - {self.listing.title}"
    
    def save(self, *args, **kwargs):
        # Calculate total price based on nights and listing price
        if self.check_in and self.check_out and self.listing:
            nights = (self.check_out - self.check_in).days
            if nights > 0:
                self.total_price = self.listing.price_per_night * nights
        super().save(*args, **kwargs)
    
    class Meta:
        ordering = ['-created_at']


class Review(models.Model):
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='reviews')
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='review')
    guest = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews')
    rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Review by {self.guest.username} - {self.rating} stars"
    
    class Meta:
        ordering = ['-created_at']
        unique_together = ['booking', 'guest']  # One review per booking per guest


class Payment(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('chapa', 'Chapa'),
        ('bank_transfer', 'Bank Transfer'),
        ('card', 'Credit Card'),
    ]

    # Primary fields
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.OneToOneField(
        'Booking', 
        on_delete=models.CASCADE, 
        related_name='payment'
    )
    
    # Payment details
    amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0.01)]
    )
    currency = models.CharField(max_length=3, default='ETB')
    status = models.CharField(
        max_length=20, 
        choices=PAYMENT_STATUS_CHOICES, 
        default='pending'
    )
    payment_method = models.CharField(
        max_length=20, 
        choices=PAYMENT_METHOD_CHOICES, 
        default='chapa'
    )
    
    # Chapa specific fields
    chapa_transaction_id = models.CharField(max_length=100, blank=True, null=True)
    chapa_checkout_url = models.URLField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    
    # Additional info
    customer_email = models.EmailField()
    customer_first_name = models.CharField(max_length=100)
    customer_last_name = models.CharField(max_length=100)
    
    # Error handling
    error_message = models.TextField(blank=True, null=True)
    retry_count = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['chapa_transaction_id']),
            models.Index(fields=['booking']),
        ]
    
    def __str__(self):
        return f"Payment {self.id} - {self.booking} - {self.status}"
    
    @property
    def is_successful(self):
        return self.status == 'completed'
    
    @property
    def can_retry(self):
        return self.status in ['failed', 'cancelled'] and self.retry_count < 3
    
    def mark_as_paid(self):
        from django.utils import timezone
        self.status = 'completed'
        self.paid_at = timezone.now()
        self.save()
        
        # Update booking status
        self.booking.status = 'confirmed'
        self.booking.save()



