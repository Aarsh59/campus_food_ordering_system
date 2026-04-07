from django.contrib.auth.models import AbstractUser
from django.contrib.auth.validators import ASCIIUsernameValidator
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    username_validator = ASCIIUsernameValidator()

    username = models.CharField(
        'username',
        max_length=150,
        unique=True,
        help_text='Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.',
        validators=[username_validator],
        error_messages={
            'unique': 'A user with that username already exists.',
        },
    )

    class Role(models.TextChoices):
        STUDENT  = 'STUDENT',  'Student'
        VENDOR   = 'VENDOR',   'Vendor'
        DELIVERY = 'DELIVERY', 'Delivery Personnel'

    role  = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.STUDENT
    )
    phone = models.CharField(max_length=15)

    # these two lines fix the clash
    groups = models.ManyToManyField(
        'auth.Group',
        related_name='custom_user_set',
        blank=True
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='custom_user_set',
        blank=True
    )

    def __str__(self):
        return f"{self.username} ({self.role})"


class StaffApplication(models.Model):
    class Role(models.TextChoices):
        VENDOR   = 'VENDOR',   'Vendor'
        DELIVERY = 'DELIVERY', 'Delivery Personnel'

    class Status(models.TextChoices):
        PENDING  = 'PENDING',  'Pending'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    # personal details
    full_name      = models.CharField(max_length=100)
    email          = models.EmailField(unique=True)
    phone          = models.CharField(max_length=10)
    role_applied   = models.CharField(max_length=20, choices=Role.choices)
    aadhaar_number = models.CharField(max_length=12)
    aadhaar_document = models.FileField(upload_to='documents/aadhaar/')

    # vendor specific
    outlet_name     = models.CharField(max_length=100, blank=True)
    outlet_location = models.CharField(max_length=200, blank=True)
    cuisine_type    = models.CharField(max_length=100, blank=True)
    operating_hours = models.CharField(max_length=100, blank=True)
    fssai_license   = models.CharField(max_length=14, blank=True)
    fssai_document  = models.FileField(upload_to='documents/fssai/', blank=True)
    gst_number      = models.CharField(max_length=15, blank=True)
    college_noc     = models.FileField(upload_to='documents/noc/', blank=True)
    bank_account    = models.CharField(max_length=20, blank=True)
    ifsc_code       = models.CharField(max_length=11, blank=True)

    # delivery specific
    vehicle_type      = models.CharField(max_length=50, blank=True)
    vehicle_number    = models.CharField(max_length=20, blank=True)
    driving_license   = models.CharField(max_length=20, blank=True)
    driving_license_document = models.FileField(upload_to='documents/license/', blank=True)
    emergency_contact = models.CharField(max_length=10, blank=True)

    # admin tracking
    status      = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    applied_at  = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    admin_notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.full_name} - {self.role_applied} ({self.status})"


class VendorProfile(models.Model):
    """
    Vendor-specific profile created after application approval.
    Stores outlet-level info like Google Maps location.
    """

    user = models.OneToOneField('User', on_delete=models.CASCADE, related_name='vendor_profile')
    outlet_name = models.CharField(max_length=100, blank=True)
    google_maps_location = models.CharField(max_length=500, blank=True)
    google_maps_address = models.CharField(max_length=500, blank=True)

    cuisine_type = models.CharField(max_length=100, blank=True)
    operating_hours = models.CharField(max_length=100, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.outlet_name or self.user.username


class MenuItem(models.Model):
    """
    Menu items belong to a vendor.
    Photos are stored using FileField to avoid forcing Pillow as a dependency.
    """

    vendor = models.ForeignKey(VendorProfile, on_delete=models.CASCADE, related_name='menu_items')

    name = models.CharField(max_length=120)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True)

    # Using FileField instead of ImageField to keep dependencies minimal.
    photo = models.FileField(upload_to='menu_photos/', blank=True, null=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.vendor} - {self.name}"


class Order(models.Model):
    """
    Minimal order model to support vendor workflows:
    - incoming tickets: vendor accepts/rejects
    - status tab: vendor updates order preparation status
    """

    class VendorDecision(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        ACCEPTED = 'ACCEPTED', 'Accepted'
        REJECTED = 'REJECTED', 'Rejected'

    class VendorStatus(models.TextChoices):
        NOT_STARTED = 'NOT_STARTED', 'Not started'
        PREPARING = 'PREPARING', 'Preparing'
        READY = 'READY', 'Ready'
        CANCELLED = 'CANCELLED', 'Cancelled'

    class DeliveryStatus(models.TextChoices):
        NOT_STARTED = 'NOT_STARTED', 'Not started'
        OUT_FOR_DELIVERY = 'OUT_FOR_DELIVERY', 'Out for delivery'
        DELIVERED = 'DELIVERED', 'Delivered'

    class PaymentStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'

    student = models.ForeignKey('User', on_delete=models.CASCADE, related_name='orders_as_student')
    vendor = models.ForeignKey(VendorProfile, on_delete=models.CASCADE, related_name='orders')

    vendor_decision = models.CharField(max_length=20, choices=VendorDecision.choices, default=VendorDecision.PENDING)
    vendor_status = models.CharField(max_length=30, choices=VendorStatus.choices, default=VendorStatus.NOT_STARTED)
    delivery_status = models.CharField(max_length=30, choices=DeliveryStatus.choices, default=DeliveryStatus.NOT_STARTED)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)

    # Order amount
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Delivery location
    delivery_address = models.CharField(max_length=500, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # optional: a human-friendly order code (useful in UIs)
    order_code = models.CharField(max_length=30, unique=True, blank=True, default='')

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        # Ensure an order_code exists for ticket UX.
        if not self.order_code:
            # Example: ORD-20260326153000123456 (timestamp + microseconds)
            self.order_code = f"ORD-{timezone.now().strftime('%Y%m%d%H%M%S%f')}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order_code} ({self.student.username} -> {self.vendor})"


class OrderItem(models.Model):
    """
    Snapshot of an order line item.
    Snapshots prevent menu price changes from breaking historical orders.
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')

    vendor_item = models.ForeignKey(MenuItem, on_delete=models.SET_NULL, null=True, blank=True, related_name='order_items')

    item_name = models.CharField(max_length=120)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)

    def line_total(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.item_name} x{self.quantity}"


class Notification(models.Model):
    class NotificationType(models.TextChoices):
        ORDER_UPDATE = 'ORDER_UPDATE', 'Order update'

    recipient = models.ForeignKey('User', on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=30, choices=NotificationType.choices, default=NotificationType.ORDER_UPDATE)

    message = models.TextField()
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name='notifications')

    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"To {self.recipient.username}: {self.message[:30]}"


class Cart(models.Model):
    """
    Shopping cart for students.
    Allows items from multiple vendors to be added.
    """
    student = models.OneToOneField('User', on_delete=models.CASCADE, related_name='cart')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_total(self):
        return sum(item.get_subtotal() for item in self.items.all())

    def get_vendor_groups(self):
        """Group items by vendor for checkout display"""
        vendors = {}
        for item in self.items.all():
            vendor_id = item.menu_item.vendor.id
            if vendor_id not in vendors:
                vendors[vendor_id] = {
                    'vendor': item.menu_item.vendor,
                    'items': [],
                    'total': 0
                }
            vendors[vendor_id]['items'].append(item)
            vendors[vendor_id]['total'] += item.get_subtotal()
        return vendors

    def __str__(self):
        return f"Cart for {self.student.username}"


class CartItem(models.Model):
    """
    Individual item in the shopping cart.
    """
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name='cart_items')
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_subtotal(self):
        return self.menu_item.price * self.quantity

    class Meta:
        unique_together = ('cart', 'menu_item')

    def __str__(self):
        return f"{self.menu_item.name} x{self.quantity} in {self.cart.student.username}'s cart"


class Payment(models.Model):
    """
    Payment transaction tracking using Razorpay.
    """
    class PaymentStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        SUCCESS = 'SUCCESS', 'Success'
        FAILED = 'FAILED', 'Failed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='payment')
    student = models.ForeignKey('User', on_delete=models.CASCADE, related_name='payments')
    
    # Razorpay details
    razorpay_order_id = models.CharField(max_length=100, blank=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True)
    razorpay_signature = models.CharField(max_length=200, blank=True)
    
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='INR')
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment {self.razorpay_order_id or 'N/A'} - {self.status}"


class DeliveryAssignment(models.Model):
    """
    Tracks which delivery partner is assigned to an order.
    """
    class AssignmentStatus(models.TextChoices):
        ACCEPTED = 'ACCEPTED', 'Accepted'
        PICKED_UP = 'PICKED_UP', 'Picked Up'
        OUT_FOR_DELIVERY = 'OUT_FOR_DELIVERY', 'Out for Delivery'
        DELIVERED = 'DELIVERED', 'Delivered'
        CANCELLED = 'CANCELLED', 'Cancelled'

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='delivery_assignment')
    delivery_partner = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_orders')
    
    status = models.CharField(max_length=30, choices=AssignmentStatus.choices, default=AssignmentStatus.ACCEPTED)
    
    assigned_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    out_for_delivery_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    
    # Delivery partner contact info (cached from StaffApplication for quick access)
    partner_name = models.CharField(max_length=100, blank=True)
    partner_phone = models.CharField(max_length=15, blank=True)
    partner_vehicle = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return f"Delivery for {self.order.order_code}"


class OrderTracking(models.Model):
    """
    Real-time location updates for order delivery.
    Stores latitude, longitude, and timestamp for tracking.
    """
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='tracking_updates')
    delivery_partner = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True)
    
    latitude = models.FloatField()
    longitude = models.FloatField()
    accuracy = models.FloatField(null=True, blank=True)  # GPS accuracy in meters
    
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"Location update for {self.order.order_code} at {self.timestamp}"


class DeliveryBroadcast(models.Model):
    """
    Broadcast an order to all registered delivery personnel.
    Delivery personnel can accept or reject the delivery.
    """
    class BroadcastStatus(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'          # Waiting for acceptance
        ACCEPTED = 'ACCEPTED', 'Accepted'    # Someone accepted
        REJECTED = 'REJECTED', 'Rejected'    # All rejected
        EXPIRED = 'EXPIRED', 'Expired'       # Timed out

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='delivery_broadcast')
    
    # Broadcast details
    status = models.CharField(max_length=20, choices=BroadcastStatus.choices, default=BroadcastStatus.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='accepted_deliveries')
    accepted_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)  # Auto-expire after 10 minutes
    
    # Pickup location (vendor)
    pickup_latitude = models.FloatField(null=True, blank=True)
    pickup_longitude = models.FloatField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Broadcast for {self.order.order_code} - {self.status}"


class DeliveryBroadcastResponse(models.Model):
    """
    Track each delivery partner's response to a broadcast.
    """
    class ResponseStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        ACCEPTED = 'ACCEPTED', 'Accepted'
        REJECTED = 'REJECTED', 'Rejected'
        CANCELLED = 'CANCELLED', 'Cancelled'

    broadcast = models.ForeignKey(DeliveryBroadcast, on_delete=models.CASCADE, related_name='responses')
    delivery_partner = models.ForeignKey('User', on_delete=models.CASCADE, related_name='broadcast_responses')
    
    status = models.CharField(max_length=20, choices=ResponseStatus.choices, default=ResponseStatus.PENDING)
    responded_at = models.DateTimeField(null=True, blank=True)
    response_reason = models.TextField(blank=True)  # Why rejected
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('broadcast', 'delivery_partner')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.delivery_partner.username} - {self.status} on {self.broadcast.order.order_code}"
