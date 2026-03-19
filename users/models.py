from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
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