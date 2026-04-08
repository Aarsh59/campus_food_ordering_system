from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache
from django.utils import timezone
from django.db import IntegrityError, transaction
from .models import (
    User,
    StaffApplication,
    VendorProfile,
    MenuItem,
    Order,
    OrderItem,
    Notification,
    Cart,
    CartItem,
    Payment,
    DeliveryAssignment,
    DeliveryBroadcast,
    DeliveryBroadcastResponse,
    OrderTracking,
    ContactOTP,
)
from .username_validation import USERNAME_ALLOWED_DESCRIPTION, is_valid_username
from .email_utils import send_app_email
from .otp_utils import (
    OTPResendCooldownError,
    is_allowed_email_domain,
    is_valid_phone,
    normalize_email,
    normalize_phone,
    send_otp,
    verify_otp,
)

import json
import urllib.parse
import urllib.request
import razorpay
from datetime import timedelta
from django.db.models import Q


IITK_CAMPUS_BOUNDS = {
    'north': 26.5278,
    'south': 26.4942,
    'east': 80.2585,
    'west': 80.2240,
}
IITK_CAMPUS_CENTER = {
    'lat': 26.5124,
    'lng': 80.2329,
}
def _format_retry_after_message(retry_after_seconds: int) -> str:
    if retry_after_seconds <= 1:
        return 'Please wait 1 second before requesting another OTP.'
    if retry_after_seconds < 60:
        return f'Please wait {retry_after_seconds} seconds before requesting another OTP.'

    minutes, seconds = divmod(retry_after_seconds, 60)
    minute_label = 'minute' if minutes == 1 else 'minutes'
    if seconds == 0:
        return f'Please wait {minutes} {minute_label} before requesting another OTP.'

    second_label = 'second' if seconds == 1 else 'seconds'
    return (
        f'Please wait {minutes} {minute_label} and {seconds} {second_label} '
        'before requesting another OTP.'
    )


def _dashboard_route_name_for_user(user):
    if user.role == User.Role.STUDENT:
        return 'student_dashboard'
    if user.role == User.Role.VENDOR:
        return 'vendor_dashboard'
    if user.role == User.Role.DELIVERY:
        return 'delivery_dashboard'
    return 'login'


def _delete_file_field(field_file):
    if field_file and getattr(field_file, 'name', ''):
        field_file.delete(save=False)


def _collect_staff_application_files(applications):
    file_fields = []
    for application in applications:
        for field_name in [
            'aadhaar_document',
            'fssai_document',
            'college_noc',
            'driving_license_document',
        ]:
            field_file = getattr(application, field_name, None)
            if field_file and getattr(field_file, 'name', ''):
                file_fields.append(field_file)
    return file_fields


def _collect_vendor_menu_files(user):
    vendor_profile = VendorProfile.objects.filter(user=user).first()
    if not vendor_profile:
        return []
    return [
        item.photo
        for item in vendor_profile.menu_items.all()
        if item.photo and getattr(item.photo, 'name', '')
    ]


def _get_account_deletion_blocker(user):
    if user.role == User.Role.STUDENT:
        has_active_orders = Order.objects.filter(student=user).exclude(
            Q(payment_status=Order.PaymentStatus.FAILED)
            | Q(vendor_decision=Order.VendorDecision.REJECTED)
            | Q(vendor_status=Order.VendorStatus.CANCELLED)
            | Q(delivery_status=Order.DeliveryStatus.DELIVERED)
        ).exists()
        if has_active_orders:
            return (
                'You still have active orders. Please wait for them to finish '
                'or be cancelled before deleting your account.'
            )

    if user.role == User.Role.VENDOR:
        vendor_profile = VendorProfile.objects.filter(user=user).first()
        if vendor_profile:
            has_active_orders = Order.objects.filter(vendor=vendor_profile).exclude(
                Q(vendor_decision=Order.VendorDecision.REJECTED)
                | Q(vendor_status=Order.VendorStatus.CANCELLED)
                | Q(delivery_status=Order.DeliveryStatus.DELIVERED)
            ).exists()
            if has_active_orders:
                return (
                    'You still have active vendor orders. Complete or cancel them '
                    'before deleting your account.'
                )

    if user.role == User.Role.DELIVERY:
        has_active_assignments = DeliveryAssignment.objects.filter(
            delivery_partner=user,
            status__in=[
                DeliveryAssignment.AssignmentStatus.ACCEPTED,
                DeliveryAssignment.AssignmentStatus.PICKED_UP,
                DeliveryAssignment.AssignmentStatus.OUT_FOR_DELIVERY,
            ],
        ).exists()
        if has_active_assignments:
            return (
                'You still have an active delivery assignment. Complete it before '
                'deleting your account.'
            )

    return ''


def _delete_user_account_data(user):
    staff_applications = list(StaffApplication.objects.filter(email=user.email))
    uploaded_files = _collect_staff_application_files(staff_applications)
    uploaded_files.extend(_collect_vendor_menu_files(user))

    ContactOTP.objects.filter(
        Q(target=normalize_email(user.email)) | Q(target=normalize_phone(user.phone))
    ).delete()

    StaffApplication.objects.filter(id__in=[application.id for application in staff_applications]).delete()
    user.delete()

    # Remove uploaded files after database rows are gone.
    for field_file in uploaded_files:
        _delete_file_field(field_file)


def _parse_cart_quantity(raw_quantity, *, allow_zero=False):
    """Parse and validate a cart quantity sent by the client."""
    try:
        quantity = int(raw_quantity)
    except (TypeError, ValueError):
        raise ValueError('Invalid quantity')

    minimum_quantity = 0 if allow_zero else 1
    if quantity < minimum_quantity:
        minimum_message = '0 or more' if allow_zero else 'at least 1'
        raise ValueError(f'Quantity must be {minimum_message}')
    return quantity


def _parse_menu_item_stock(raw_stock):
    """Parse and validate a vendor-supplied stock value."""
    try:
        stock = int(raw_stock)
    except (TypeError, ValueError):
        raise ValueError('Invalid stock value.')

    if stock < 0:
        raise ValueError('Stock cannot be negative.')
    return stock


def _validate_menu_item_quantity(menu_item, quantity):
    """Ensure a requested quantity fits within the current stock."""
    if quantity > menu_item.stock:
        if menu_item.stock == 0:
            raise ValueError(f'{menu_item.name} is currently out of stock.')
        raise ValueError(
            f'Only {menu_item.stock} of {menu_item.name} available right now.'
        )


def _restore_order_item_stock(order):
    """Return reserved stock for an order back to its menu items."""
    for order_item in order.items.select_related('vendor_item'):
        if order_item.vendor_item_id:
            menu_item = order_item.vendor_item
            menu_item.stock += order_item.quantity
            menu_item.save(update_fields=['stock'])


def _cancel_pending_checkout_orders(student, cancellation_reason, order_ids=None, razorpay_order_id=None):
    """
    Cancel pending checkout orders left behind by an abandoned payment flow.
    """
    pending_orders_qs = Order.objects.filter(
        student=student,
        payment_status=Order.PaymentStatus.PENDING,
    )
    if order_ids is not None:
        pending_orders_qs = pending_orders_qs.filter(id__in=order_ids)

    pending_orders = list(pending_orders_qs)
    if not pending_orders:
        return 0

    order_ids = [order.id for order in pending_orders]
    pending_payment_qs = Payment.objects.filter(
        student=student,
        order_id__in=order_ids,
    )
    if razorpay_order_id:
        pending_payment_qs = pending_payment_qs.filter(razorpay_order_id=razorpay_order_id)
    else:
        pending_payment_qs = pending_payment_qs.filter(status=Payment.PaymentStatus.PENDING)

    pending_payment = pending_payment_qs.order_by('-created_at').first()

    if pending_payment and pending_payment.status == Payment.PaymentStatus.SUCCESS:
        return 0

    for order in pending_orders:
        _restore_order_item_stock(order)
        order.payment_status = Order.PaymentStatus.FAILED
        order.vendor_status = Order.VendorStatus.CANCELLED
        order.save(update_fields=['payment_status', 'vendor_status', 'updated_at'])

        _notify_user(
            student,
            order,
            f"{cancellation_reason}. Order {order.order_code} was cancelled.",
            email_subject='Order Cancelled',
        )

    if pending_payment and pending_payment.status == Payment.PaymentStatus.PENDING:
        pending_payment.status = Payment.PaymentStatus.CANCELLED
        pending_payment.save(update_fields=['status', 'updated_at'])

    return len(pending_orders)


def redirect_authenticated_user(user):
    return redirect(_dashboard_route_name_for_user(user))


def home_view(request):
    if request.user.is_authenticated:
        return redirect_authenticated_user(request.user)
    return redirect('login')


def _generate_google_maps_link_from_address(address: str) -> tuple[str, str]:
    """
    Convert a free-form address into a Google Maps link using Geocoding API.
    """
    address = (address or "").strip()
    if not address:
        raise ValueError("Address is required")

    api_key = getattr(settings, "GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        raise ValueError("Google Maps API key is not configured")

    query = urllib.parse.urlencode({"address": _build_iitk_geocode_query(address), "key": api_key})
    url = f"https://maps.googleapis.com/maps/api/geocode/json?{query}"

    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    if payload.get("status") != "OK":
        # Examples: OVER_QUERY_LIMIT, REQUEST_DENIED, ZERO_RESULTS
        detail = payload.get("error_message") or payload.get("results") or ""
        if detail:
            raise ValueError(f"Geocoding failed: {payload.get('status')} ({detail})")
        raise ValueError(f"Geocoding failed: {payload.get('status')}")

    results = payload.get("results") or []
    if not results:
        raise ValueError("No matching location found for the given address")

    loc = (results[0].get("geometry") or {}).get("location") or {}
    lat = loc.get("lat")
    lng = loc.get("lng")
    if lat is None or lng is None:
        raise ValueError("Geocoding returned no coordinates")

    # Using a "search link" style similar to what map-based apps generate.
    maps_link = f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
    formatted_address = results[0].get("formatted_address") or address
    return maps_link, formatted_address


def _reverse_geocode_lat_lng(lat: float, lng: float) -> tuple[str, str]:
    """
    Convert coordinates into a Google Maps search link + formatted address using Geocoding API.
    """
    api_key = getattr(settings, "GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        raise ValueError("Google Maps API key is not configured")

    if not _is_within_iitk_campus(lat, lng):
        raise ValueError("Selected location must be inside the IIT Kanpur campus")

    query = urllib.parse.urlencode({"latlng": f"{lat},{lng}", "key": api_key})
    url = f"https://maps.googleapis.com/maps/api/geocode/json?{query}"

    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    if payload.get("status") != "OK":
        detail = payload.get("error_message") or payload.get("results") or ""
        if detail:
            raise ValueError(f"Geocoding failed: {payload.get('status')} ({detail})")
        raise ValueError(f"Geocoding failed: {payload.get('status')}")

    results = payload.get("results") or []
    if not results:
        raise ValueError("No matching location found for the given coordinates")

    formatted_address = results[0].get("formatted_address") or ""
    maps_link = f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
    return maps_link, formatted_address


def _is_within_iitk_campus(lat: float, lng: float) -> bool:
    return (
        IITK_CAMPUS_BOUNDS['south'] <= lat <= IITK_CAMPUS_BOUNDS['north']
        and IITK_CAMPUS_BOUNDS['west'] <= lng <= IITK_CAMPUS_BOUNDS['east']
    )


def _build_iitk_geocode_query(address: str) -> str:
    normalized = (address or '').strip()
    lowered = normalized.lower()
    if not normalized:
        return normalized
    if 'iit kanpur' in lowered or 'indian institute of technology kanpur' in lowered:
        return normalized
    return f'{normalized}, IIT Kanpur'


def _validate_iitk_location_from_address(address: str) -> tuple[str, str, tuple]:
    maps_link, formatted_address = _generate_google_maps_link_from_address(address)
    coords = _parse_google_maps_coordinates(maps_link)
    if not coords:
        raise ValueError('Could not determine map coordinates for this location')
    if not _is_within_iitk_campus(coords[0], coords[1]):
        raise ValueError('Location must be inside the IIT Kanpur campus')
    return maps_link, formatted_address, coords


def _campus_map_context() -> dict:
    return {
        'campus_map_config_json': json.dumps({
            'bounds': IITK_CAMPUS_BOUNDS,
            'center': IITK_CAMPUS_CENTER,
        }),
    }


# ─── Register (Students Only) ─────────────────────────────────────────────────
@require_http_methods(["POST"])
def send_registration_otp(request):
    """Send OTP for student registration or staff application contact verification."""
    purpose = request.POST.get('purpose')
    channel = request.POST.get('channel')
    email = normalize_email(request.POST.get('email'))
    phone = normalize_phone(request.POST.get('phone'))

    if purpose not in ContactOTP.Purpose.values:
        return JsonResponse({'success': False, 'error': 'Invalid OTP purpose'}, status=400)

    if channel not in ContactOTP.Channel.values:
        return JsonResponse({'success': False, 'error': 'Invalid OTP channel'}, status=400)

    if channel != ContactOTP.Channel.EMAIL:
        return JsonResponse({'success': False, 'error': 'Only email OTP is supported right now'}, status=400)

    if purpose == ContactOTP.Purpose.STUDENT_REGISTER and not is_allowed_email_domain(email):
        return JsonResponse({
            'success': False,
            'error': f'Only {settings.ALLOWED_EMAIL_DOMAIN} emails are allowed',
        }, status=400)
    if purpose == ContactOTP.Purpose.STUDENT_REGISTER and User.objects.filter(email=email).exists():
        return JsonResponse({'success': False, 'error': 'Email already registered'}, status=400)
    if purpose == ContactOTP.Purpose.STAFF_APPLICATION and StaffApplication.objects.filter(email=email).exists():
        return JsonResponse({'success': False, 'error': 'An application with this email already exists'}, status=400)
    try:
        sent = send_otp(purpose, channel, email)
    except OTPResendCooldownError as exc:
        return JsonResponse({
            'success': False,
            'error': _format_retry_after_message(exc.retry_after_seconds),
            'retry_after_seconds': exc.retry_after_seconds,
        }, status=429)

    return JsonResponse({
        'success': sent,
        'message': 'Email OTP sent. Please check your inbox.',
        'error': '' if sent else 'Could not send email OTP. Please try again.',
    }, status=200 if sent else 500)


def _contact_otps_are_valid(request, purpose: str, email: str, phone: str) -> bool:
    email_otp = request.POST.get('email_otp')

    email_verified = verify_otp(purpose, ContactOTP.Channel.EMAIL, email, email_otp, consume=False)

    if not email_verified:
        messages.error(request, 'Please enter the correct email OTP before submitting.')
        return False

    verify_otp(purpose, ContactOTP.Channel.EMAIL, email, email_otp)
    return True


def register_view(request):
    if request.method == 'POST':
        username   = (request.POST.get('username') or '').strip()
        email      = normalize_email(request.POST.get('email'))
        phone      = normalize_phone(request.POST.get('phone'))
        password1  = request.POST.get('password1')
        password2  = request.POST.get('password2')

        # validations
        if password1 != password2:
            messages.error(request, 'Passwords do not match')
            return render(request, 'users/register.html')

        if not is_valid_username(username):
            messages.error(request, f'Username can contain {USERNAME_ALLOWED_DESCRIPTION}')
            return render(request, 'users/register.html')

        if not is_allowed_email_domain(email):
            messages.error(request, f'Only {settings.ALLOWED_EMAIL_DOMAIN} emails are allowed')
            return render(request, 'users/register.html')

        if not is_valid_phone(phone):
            messages.error(request, 'Enter a valid 10 digit mobile number')
            return render(request, 'users/register.html')

        if User.objects.filter(username__iexact=username).exists():
            messages.error(request, 'Username already taken')
            return render(request, 'users/register.html')

        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already registered')
            return render(request, 'users/register.html')

        if not _contact_otps_are_valid(request, ContactOTP.Purpose.STUDENT_REGISTER, email, phone):
            return render(request, 'users/register.html')

        # create user
        try:
            User.objects.create_user(
                username=username,
                email=email,
                password=password1,
                phone=phone,
                role=User.Role.STUDENT
            )
        except IntegrityError:
            messages.error(request, 'Username already taken')
            return render(request, 'users/register.html')

        messages.success(request, 'Account created! Please log in.')
        return redirect('login')

    return render(request, 'users/register.html')


# ─── Login ────────────────────────────────────────────────────────────────────
def login_view(request):
    if request.user.is_authenticated:
        return redirect_authenticated_user(request.user)

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            request.session.set_expiry(getattr(settings, 'SESSION_INACTIVITY_TIMEOUT', settings.SESSION_COOKIE_AGE))
            return redirect_authenticated_user(user)
        else:
            messages.error(request, 'Invalid username or password')

    return render(request, 'users/login.html')


# ─── Logout ───────────────────────────────────────────────────────────────────
def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def account_settings(request):
    deletion_blocker = _get_account_deletion_blocker(request.user)
    return render(
        request,
        'users/account_settings.html',
        {
            'deletion_blocker': deletion_blocker,
            'dashboard_route_name': _dashboard_route_name_for_user(request.user),
        },
    )


@login_required
@require_http_methods(["POST"])
def delete_account(request):
    confirmation = (request.POST.get('confirmation') or '').strip()
    if confirmation != 'DELETE':
        messages.error(request, 'Type DELETE to confirm account deletion.')
        return redirect('account_settings')

    deletion_blocker = _get_account_deletion_blocker(request.user)
    if deletion_blocker:
        messages.error(request, deletion_blocker)
        return redirect('account_settings')

    with transaction.atomic():
        _delete_user_account_data(request.user)

    logout(request)
    messages.success(
        request,
        'Your account has been deleted. You can now register or apply again with the same email address.',
    )
    return redirect('login')


# ─── Vendor/Delivery Application ─────────────────────────────────────────────
def apply_view(request):
    if request.method == 'POST':
        role_applied = request.POST.get('role_applied')
        email = normalize_email(request.POST.get('email'))
        phone = normalize_phone(request.POST.get('phone'))

        if role_applied not in StaffApplication.Role.values:
            messages.error(request, 'Please select a valid role')
            return render(request, 'users/apply.html')

        if not is_valid_phone(phone):
            messages.error(request, 'Enter a valid 10 digit mobile number')
            return render(request, 'users/apply.html')

        if StaffApplication.objects.filter(email=email).exists():
            messages.error(request, 'An application with this email already exists')
            return render(request, 'users/apply.html')

        if User.objects.filter(email=email).exists():
            messages.error(request, 'A user with this email already exists')
            return render(request, 'users/apply.html')

        if not _contact_otps_are_valid(request, ContactOTP.Purpose.STAFF_APPLICATION, email, phone):
            return render(request, 'users/apply.html')

        application = StaffApplication(
            full_name        = request.POST.get('full_name'),
            email            = email,
            phone            = phone,
            role_applied     = role_applied,
            aadhaar_number   = request.POST.get('aadhaar_number'),
            aadhaar_document = request.FILES.get('aadhaar_document'),
        )

        if role_applied == 'VENDOR':
            application.outlet_name     = request.POST.get('outlet_name', '')
            application.outlet_location = request.POST.get('outlet_location', '')
            application.cuisine_type    = request.POST.get('cuisine_type', '')
            application.operating_hours = request.POST.get('operating_hours', '')
            application.fssai_license   = request.POST.get('fssai_license', '')
            application.fssai_document  = request.FILES.get('fssai_document')
            application.gst_number      = request.POST.get('gst_number', '')
            application.college_noc     = request.FILES.get('college_noc')
            application.bank_account    = request.POST.get('bank_account', '')
            application.ifsc_code       = request.POST.get('ifsc_code', '')

        elif role_applied == 'DELIVERY':
            application.vehicle_type             = request.POST.get('vehicle_type', '')
            application.vehicle_number           = request.POST.get('vehicle_number', '')
            application.driving_license          = request.POST.get('driving_license', '')
            application.driving_license_document = request.FILES.get('driving_license_document')
            application.emergency_contact        = request.POST.get('emergency_contact', '')

        application.save()
        return redirect('pending')

    return render(request, 'users/apply.html')


# ─── Pending Page ─────────────────────────────────────────────────────────────
def pending_view(request):
    return render(request, 'users/pending.html')


# ─── Dashboards ──────────────────────────────────────────────────────────────
@login_required
def student_dashboard(request):
    if request.user.role != User.Role.STUDENT:
        messages.error(request, 'Unauthorized access')
        return redirect('login')
    
    notifications = Notification.objects.filter(recipient=request.user).order_by('-created_at')[:50]
    recent_orders = (
        Order.objects.filter(student=request.user)
        .select_related('vendor')
        .order_by('-created_at')[:5]
    )
    orders_placed_count = Order.objects.filter(
        student=request.user,
        payment_status=Order.PaymentStatus.COMPLETED,
    ).exclude(
        vendor_decision=Order.VendorDecision.REJECTED,
    ).exclude(
        vendor_status=Order.VendorStatus.CANCELLED,
    ).count()
    return render(request, 'student/dashboard.html', {
        'notifications': notifications,
        'recent_orders': recent_orders,
        'orders_placed_count': orders_placed_count,
    })


@login_required
def vendor_dashboard(request):
    if request.user.role != User.Role.VENDOR:
        messages.error(request, 'Unauthorized access')
        return redirect('login')

    vendor_profile, _ = VendorProfile.objects.get_or_create(user=request.user)
    now = timezone.now()
    DeliveryBroadcast.objects.filter(
        order__vendor=vendor_profile,
        status=DeliveryBroadcast.BroadcastStatus.ACTIVE,
        expires_at__lt=now,
    ).update(status=DeliveryBroadcast.BroadcastStatus.EXPIRED)

    incoming_tickets = (
        Order.objects.filter(
            vendor=vendor_profile,
            vendor_decision=Order.VendorDecision.PENDING,
        )
        .select_related('student', 'vendor')
        .prefetch_related('items')
        .order_by('-created_at')[:50]
    )

    accepted_orders = (
        Order.objects.filter(
            vendor=vendor_profile,
            vendor_decision=Order.VendorDecision.ACCEPTED,
        )
        .exclude(
            Q(delivery_status=Order.DeliveryStatus.DELIVERED) |
            Q(vendor_status=Order.VendorStatus.CANCELLED) |
            Q(delivery_broadcast__status=DeliveryBroadcast.BroadcastStatus.EXPIRED)
        )
        .select_related('student', 'vendor')
        .prefetch_related('items')
        .order_by('-created_at')[:50]
    )

    menu_items = MenuItem.objects.filter(vendor=vendor_profile, is_active=True).order_by('-updated_at')[:50]

    return render(
        request,
        'vendor/dashboard.html',
        {
            'vendor_profile': vendor_profile,
            'incoming_tickets': incoming_tickets,
            'accepted_orders': accepted_orders,
            'menu_items': menu_items,
            'google_maps_api_key': settings.GOOGLE_MAPS_API_KEY,
            **_campus_map_context(),
        },
    )


@login_required
def delivery_dashboard(request):
    """
    Display delivery partner dashboard with available broadcasts and active assignments.
    """
    if request.user.role != User.Role.DELIVERY:
        messages.error(request, 'Unauthorized access')
        return redirect('login')
    
    now = timezone.now()
    DeliveryBroadcast.objects.filter(
        status=DeliveryBroadcast.BroadcastStatus.ACTIVE,
        expires_at__lt=now,
    ).update(status=DeliveryBroadcast.BroadcastStatus.EXPIRED)

    # Get accepted deliveries
    my_accepted = DeliveryAssignment.objects.filter(
        delivery_partner=request.user,
        status__in=[
            DeliveryAssignment.AssignmentStatus.ACCEPTED,
            DeliveryAssignment.AssignmentStatus.PICKED_UP,
            DeliveryAssignment.AssignmentStatus.OUT_FOR_DELIVERY,
        ]
    ).select_related('order', 'order__vendor', 'order__student')

    has_active_delivery = my_accepted.exists()

    available = []
    if not has_active_delivery:
        active_broadcasts = DeliveryBroadcast.objects.filter(
            status=DeliveryBroadcast.BroadcastStatus.ACTIVE
        ).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        ).select_related('order', 'order__vendor', 'order__student')

        my_responses = DeliveryBroadcastResponse.objects.filter(
            delivery_partner=request.user
        ).values('broadcast_id', 'status')
        response_dict = {r['broadcast_id']: r['status'] for r in my_responses}

        for broadcast in active_broadcasts:
            if broadcast.id not in response_dict or response_dict[broadcast.id] == DeliveryBroadcastResponse.ResponseStatus.PENDING:
                available.append(broadcast)
    
    return render(request, 'delivery/dashboard.html', {
        'broadcasts': available,
        'my_deliveries': my_accepted,
        'has_active_delivery': has_active_delivery,
    })


# ─── Vendor Actions ─────────────────────────────────────────────────────────
@login_required
def vendor_update_location(request):
    if request.user.role != User.Role.VENDOR:
        messages.error(request, 'Unauthorized access')
        return redirect('login')
    if request.method != 'POST':
        return redirect('vendor_dashboard')

    vendor_profile, _ = VendorProfile.objects.get_or_create(user=request.user)
    outlet_name = request.POST.get('outlet_name', vendor_profile.outlet_name).strip()
    google_maps_location = request.POST.get(
        'google_maps_location', vendor_profile.google_maps_location
    ).strip()
    google_maps_address = request.POST.get(
        'google_maps_address', vendor_profile.google_maps_address
    ).strip()

    if not outlet_name:
        messages.error(request, 'Outlet name is required.')
        return redirect('vendor_dashboard')

    if not google_maps_address or not google_maps_location:
        messages.error(request, 'Please select and save your outlet address on the map before continuing.')
        return redirect('vendor_dashboard')

    coords = _parse_google_maps_coordinates(google_maps_location)
    if not coords:
        messages.error(request, 'Your saved outlet map location is invalid. Please select it again on the map.')
        return redirect('vendor_dashboard')

    if not _is_within_iitk_campus(coords[0], coords[1]):
        messages.error(request, 'Vendor location must be inside the IIT Kanpur campus.')
        return redirect('vendor_dashboard')

    try:
        _, normalized_address = _reverse_geocode_lat_lng(coords[0], coords[1])
    except Exception as exc:
        messages.error(request, f'Could not validate the selected outlet location: {exc}')
        return redirect('vendor_dashboard')

    vendor_profile.outlet_name = outlet_name
    vendor_profile.google_maps_location = google_maps_location
    vendor_profile.google_maps_address = normalized_address or google_maps_address
    vendor_profile.save()

    messages.success(request, 'Location saved successfully.')
    return redirect('vendor_dashboard')


@login_required
def vendor_menu_add(request):
    if request.user.role != User.Role.VENDOR:
        messages.error(request, 'Unauthorized access')
        return redirect('login')
    if request.method != 'POST':
        return redirect('vendor_dashboard')

    vendor_profile, _ = VendorProfile.objects.get_or_create(user=request.user)

    name = request.POST.get('name', '').strip()
    description = request.POST.get('description', '').strip()
    price_raw = request.POST.get('price', '').strip()
    stock_raw = request.POST.get('stock', '').strip()
    photo = request.FILES.get('photo')

    if not name or not price_raw or not stock_raw:
        messages.error(request, 'Menu item name, price, and stock are required.')
        return redirect('vendor_dashboard')

    try:
        price = Decimal(price_raw)
    except (InvalidOperation, ValueError):
        messages.error(request, 'Invalid price value.')
        return redirect('vendor_dashboard')

    try:
        stock = _parse_menu_item_stock(stock_raw)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('vendor_dashboard')

    MenuItem.objects.create(
        vendor=vendor_profile,
        name=name,
        description=description,
        price=price,
        stock=stock,
        photo=photo,
    )

    messages.success(request, 'Menu item added.')
    return redirect('vendor_dashboard')


@login_required
def vendor_menu_update(request, item_id: int):
    if request.user.role != User.Role.VENDOR:
        messages.error(request, 'Unauthorized access')
        return redirect('login')
    if request.method != 'POST':
        return redirect('vendor_dashboard')

    vendor_profile, _ = VendorProfile.objects.get_or_create(user=request.user)
    item = get_object_or_404(MenuItem, pk=item_id, vendor=vendor_profile)

    name = request.POST.get('name', item.name).strip()
    description = request.POST.get('description', item.description).strip()
    price_raw = request.POST.get('price', '').strip()
    stock_raw = request.POST.get('stock', '').strip()

    if price_raw:
        try:
            item.price = Decimal(price_raw)
        except (InvalidOperation, ValueError):
            messages.error(request, 'Invalid price value.')
            return redirect('vendor_dashboard')

    if stock_raw:
        try:
            item.stock = _parse_menu_item_stock(stock_raw)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('vendor_dashboard')

    item.name = name
    item.description = description

    photo = request.FILES.get('photo')
    if photo:
        item.photo = photo

    is_active_raw = request.POST.get('is_active')
    if is_active_raw is not None:
        item.is_active = is_active_raw == 'true'

    item.save()
    messages.success(request, 'Menu item updated.')
    return redirect('vendor_dashboard')


def _safe_send_email(subject: str, message: str, recipient_email: str):
    """
    Best-effort email sender. Failures shouldn't break vendor workflows.
    """
    return send_app_email(subject=subject, message=message, recipient_email=recipient_email)


def _notify_user(recipient: User, order: Order, message: str, email_subject: str = ''):
    notification = Notification.objects.create(
        recipient=recipient,
        order=order,
        message=message,
    )
    if email_subject:
        _safe_send_email(
            subject=email_subject,
            message=message,
            recipient_email=recipient.email,
        )
    return notification


@login_required
def vendor_ticket_accept(request, order_id: int):
    if request.user.role != User.Role.VENDOR:
        messages.error(request, 'Unauthorized access')
        return redirect('login')

    vendor_profile, _ = VendorProfile.objects.get_or_create(user=request.user)
    order = get_object_or_404(Order, pk=order_id, vendor=vendor_profile)

    if order.vendor_decision != Order.VendorDecision.PENDING:
        messages.error(request, 'This ticket has already been decided.')
        return redirect('vendor_dashboard')

    order.vendor_decision = Order.VendorDecision.ACCEPTED
    order.vendor_status = Order.VendorStatus.NOT_STARTED
    order.save()

    message = f"Your order {order.order_code or order.id} has been accepted by the vendor."
    _notify_user(order.student, order, message, email_subject='Order Accepted')

    messages.success(request, 'Ticket accepted. Student has been notified.')
    return redirect('vendor_dashboard')


@login_required
def vendor_ticket_reject(request, order_id: int):
    if request.user.role != User.Role.VENDOR:
        messages.error(request, 'Unauthorized access')
        return redirect('login')

    vendor_profile, _ = VendorProfile.objects.get_or_create(user=request.user)
    order = get_object_or_404(Order, pk=order_id, vendor=vendor_profile)

    if order.vendor_decision != Order.VendorDecision.PENDING:
        messages.error(request, 'This ticket has already been decided.')
        return redirect('vendor_dashboard')

    order.vendor_decision = Order.VendorDecision.REJECTED
    order.vendor_status = Order.VendorStatus.CANCELLED
    order.save()
    _restore_order_item_stock(order)

    message = f"Your order {order.order_code or order.id} has been rejected by the vendor."
    _notify_user(order.student, order, message, email_subject='Order Rejected')

    messages.success(request, 'Ticket rejected. Student has been notified.')
    return redirect('vendor_dashboard')


@login_required
def vendor_order_status_update(request, order_id: int):
    if request.user.role != User.Role.VENDOR:
        messages.error(request, 'Unauthorized access')
        return redirect('login')
    if request.method != 'POST':
        return redirect('vendor_dashboard')

    vendor_profile, _ = VendorProfile.objects.get_or_create(user=request.user)
    order = get_object_or_404(Order, pk=order_id, vendor=vendor_profile)

    if order.vendor_decision != Order.VendorDecision.ACCEPTED:
        messages.error(request, 'You can only update status for accepted tickets.')
        return redirect('vendor_dashboard')

    new_status = request.POST.get('vendor_status', '').strip()
    valid = {c[0] for c in Order.VendorStatus.choices}
    if new_status not in valid:
        messages.error(request, 'Invalid status update.')
        return redirect('vendor_dashboard')

    order.vendor_status = new_status
    order.save()

    message = (
        f"Your order {order.order_code or order.id} status updated to: "
        f"{order.get_vendor_status_display()}."
    )
    _notify_user(order.student, order, message, email_subject='Order Status Updated')

    messages.success(request, 'Order status updated. Student has been notified.')
    return redirect('vendor_dashboard')


@login_required
def vendor_generate_google_maps_link(request):
    if request.user.role != User.Role.VENDOR:
        messages.error(request, 'Unauthorized access')
        return redirect('login')
    if request.method != 'POST':
        return redirect('vendor_dashboard')

    vendor_profile, _ = VendorProfile.objects.get_or_create(user=request.user)
    address = request.POST.get('geocode_address', '')

    try:
        maps_link, formatted_address, _ = _validate_iitk_location_from_address(address)
    except Exception as e:
        messages.error(request, f'Could not generate maps link: {e}')
        return redirect('vendor_dashboard')

    vendor_profile.google_maps_location = maps_link
    vendor_profile.google_maps_address = formatted_address
    vendor_profile.save()
    messages.success(request, 'Google Maps link generated successfully.')
    return redirect('vendor_dashboard')


@login_required
def vendor_reverse_geocode_location(request):
    if request.user.role != User.Role.VENDOR:
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    # Support both form-encoded POST and JSON body POST.
    lat = None
    lng = None
    try:
        if request.body:
            body = json.loads(request.body.decode('utf-8'))
            lat = body.get('lat')
            lng = body.get('lng')
    except Exception:
        pass

    if lat is None or lng is None:
        lat = request.POST.get('lat')
        lng = request.POST.get('lng')

    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Invalid lat/lng'}, status=400)

    try:
        maps_link, formatted_address = _reverse_geocode_lat_lng(lat, lng)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse(
        {
            'lat': lat,
            'lng': lng,
            'address': formatted_address,
            'maps_link': maps_link,
        }
    )


@login_required
@require_http_methods(["POST"])
def student_reverse_geocode_location(request):
    if request.user.role != User.Role.STUDENT:
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    lat = None
    lng = None
    try:
        if request.body:
            body = json.loads(request.body.decode('utf-8'))
            lat = body.get('lat')
            lng = body.get('lng')
    except Exception:
        pass

    if lat is None or lng is None:
        lat = request.POST.get('lat')
        lng = request.POST.get('lng')

    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Invalid lat/lng'}, status=400)

    try:
        maps_link, formatted_address = _reverse_geocode_lat_lng(lat, lng)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse(
        {
            'lat': lat,
            'lng': lng,
            'address': formatted_address,
            'maps_link': maps_link,
        }
    )


# ─── Student Views - Vendor Discovery & Ordering ──────────────────────────────

@login_required
def student_vendors_list(request):
    """Display all active vendors for student discovery."""
    if request.user.role != User.Role.STUDENT:
        messages.error(request, 'Unauthorized access')
        return redirect('login')
    
    vendors = VendorProfile.objects.filter(user__role=User.Role.VENDOR).order_by('outlet_name')
    cart = Cart.objects.filter(student=request.user).first()
    cart_count = cart.items.count() if cart else 0
    
    return render(request, 'student/vendors_list.html', {
        'vendors': vendors,
        'cart_count': cart_count,
    })


@login_required
def student_vendor_detail(request, vendor_id: int):
    """Display vendor profile with menu items."""
    if request.user.role != User.Role.STUDENT:
        messages.error(request, 'Unauthorized access')
        return redirect('login')
    
    vendor = get_object_or_404(VendorProfile, id=vendor_id)
    menu_items = MenuItem.objects.filter(vendor=vendor, is_active=True).order_by('-created_at')
    
    cart = Cart.objects.filter(student=request.user).first()
    cart_count = cart.items.count() if cart else 0
    
    # Get cart items for this vendor to show quantities in menu
    cart_items_dict = {}
    if cart:
        cart_items_dict = {
            ci.menu_item_id: ci.quantity for ci in cart.items.filter(menu_item__vendor=vendor)
        }
    menu_item_rows = [
        {
            'item': item,
            'cart_quantity': cart_items_dict.get(item.id, 0),
        }
        for item in menu_items
    ]
    
    return render(request, 'student/vendor_detail.html', {
        'vendor': vendor,
        'menu_item_rows': menu_item_rows,
        'cart_count': cart_count,
        'google_maps_api_key': settings.GOOGLE_MAPS_API_KEY,
    })


@login_required
@require_http_methods(["POST"])
def student_add_to_cart(request, item_id: int):
    """Add menu item to cart."""
    if request.user.role != User.Role.STUDENT:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    menu_item = get_object_or_404(MenuItem, id=item_id, is_active=True)
    quantity = request.POST.get('quantity', '1')
    
    try:
        quantity = _parse_cart_quantity(quantity)
        _validate_menu_item_quantity(menu_item, quantity)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    
    cart, _ = Cart.objects.get_or_create(student=request.user)
    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,
        menu_item=menu_item,
        defaults={'quantity': quantity}
    )
    
    if not created:
        cart_item.quantity = quantity
        cart_item.save()
    
    return JsonResponse({
        'success': True,
        'message': f'Added {menu_item.name} to cart',
        'cart_count': cart.items.count(),
    })


@login_required
def student_view_cart(request):
    """Display shopping cart with items from multiple vendors."""
    if request.user.role != User.Role.STUDENT:
        messages.error(request, 'Unauthorized access')
        return redirect('login')
    
    cart, _ = Cart.objects.get_or_create(student=request.user)
    vendor_groups = cart.get_vendor_groups()
    total = cart.get_total()
    
    return render(request, 'student/cart.html', {
        'cart': cart,
        'vendor_groups': vendor_groups,
        'total': total,
    })


@login_required
@require_http_methods(["POST"])
def student_remove_from_cart(request, item_id: int):
    """Remove item from cart."""
    if request.user.role != User.Role.STUDENT:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    cart = get_object_or_404(Cart, student=request.user)
    cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)
    cart_item.delete()
    
    return JsonResponse({
        'success': True,
        'message': 'Item removed from cart',
        'cart_count': cart.items.count(),
    })


@login_required
@require_http_methods(["POST"])
def student_update_cart_item(request, item_id: int):
    """Update quantity of cart item."""
    if request.user.role != User.Role.STUDENT:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    cart = get_object_or_404(Cart, student=request.user)
    cart_item = get_object_or_404(CartItem, id=item_id, cart=cart)
    
    quantity = request.POST.get('quantity', '1')
    try:
        quantity = _parse_cart_quantity(quantity, allow_zero=True)
        if quantity < 1:
            cart_item.delete()
        else:
            _validate_menu_item_quantity(cart_item.menu_item, quantity)
            cart_item.quantity = quantity
            cart_item.save()
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    
    return JsonResponse({
        'success': True,
        'message': 'Cart updated',
        'total': float(cart.get_total()),
    })


@login_required
@require_http_methods(["POST"])
def student_update_menu_cart_item(request, item_id: int):
    """Update a cart item from the menu page using a menu item id."""
    if request.user.role != User.Role.STUDENT:
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    menu_item = get_object_or_404(MenuItem, id=item_id, is_active=True)
    cart, _ = Cart.objects.get_or_create(student=request.user)

    quantity = request.POST.get('quantity', '1')
    try:
        quantity = _parse_cart_quantity(quantity, allow_zero=True)
        if quantity > 0:
            _validate_menu_item_quantity(menu_item, quantity)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=400)

    cart_item = CartItem.objects.filter(cart=cart, menu_item=menu_item).first()
    if quantity < 1:
        if cart_item:
            cart_item.delete()
        return JsonResponse({
            'success': True,
            'message': f'Removed {menu_item.name} from cart',
            'cart_count': cart.items.count(),
        })

    if cart_item:
        cart_item.quantity = quantity
        cart_item.save()
    else:
        CartItem.objects.create(cart=cart, menu_item=menu_item, quantity=quantity)

    return JsonResponse({
        'success': True,
        'message': f'Updated {menu_item.name} in cart',
        'cart_count': cart.items.count(),
    })


@login_required
@never_cache
def student_checkout(request):
    """Checkout page - prepare orders for each vendor and initiate payment."""
    if request.user.role != User.Role.STUDENT:
        messages.error(request, 'Unauthorized access')
        return redirect('login')

    cancelled_orders = _cancel_pending_checkout_orders(
        request.user,
        'Your previous checkout session expired after the page was reloaded',
    )
    if cancelled_orders:
        messages.warning(
            request,
            'Your previous payment session was cancelled after the checkout page was reloaded. '
            'Please review your cart and start payment again.',
        )
        return redirect('student_view_cart')
    
    cart = get_object_or_404(Cart, student=request.user)
    
    if not cart.items.exists():
        messages.error(request, 'Your cart is empty')
        return redirect('student_view_cart')
    
    vendor_groups = cart.get_vendor_groups()
    total_amount = cart.get_total()
    delivery_address = request.GET.get('address', '')
    
    return render(request, 'student/checkout.html', {
        'vendor_groups': vendor_groups,
        'total_amount': total_amount,
        'delivery_address': delivery_address,
        'razorpay_key': settings.RAZORPAY_KEY_ID,
        'google_maps_api_key': settings.GOOGLE_MAPS_API_KEY,
        **_campus_map_context(),
    })


@login_required
@require_http_methods(["POST"])
def student_create_order(request):
    """Create orders for each vendor and initiate Razorpay payment."""
    if request.user.role != User.Role.STUDENT:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    cart = get_object_or_404(Cart, student=request.user)
    
    if not cart.items.exists():
        return JsonResponse({'error': 'Cart is empty'}, status=400)
    
    delivery_address = request.POST.get('delivery_address', '').strip()
    if not delivery_address:
        return JsonResponse({'error': 'Delivery address is required'}, status=400)

    try:
        _, delivery_address, _ = _validate_iitk_location_from_address(delivery_address)
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    
    cart_items = list(
        CartItem.objects.filter(cart=cart)
        .select_related('menu_item', 'menu_item__vendor')
        .order_by('id')
    )
    for cart_item in cart_items:
        try:
            _validate_menu_item_quantity(cart_item.menu_item, cart_item.quantity)
        except ValueError as exc:
            return JsonResponse({'error': str(exc)}, status=400)

    total_amount = cart.get_total()
    
    # Initialize Razorpay client
    try:
        razorpay_client = razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        )
    except Exception as e:
        return JsonResponse({'error': 'Payment gateway not configured'}, status=500)
    
    # Create Razorpay order
    try:
        razorpay_order = razorpay_client.order.create({
            'amount': int(total_amount * 100),  # Razorpay expects amount in paise
            'currency': 'INR',
            'payment_capture': '1',
        })
    except Exception as e:
        return JsonResponse({'error': f'Failed to create payment order: {str(e)}'}, status=500)
    
    # Create master order record with payment info and reserve stock
    with transaction.atomic():
        locked_cart_items = list(
            CartItem.objects.select_for_update()
            .filter(cart=cart)
            .select_related('menu_item', 'menu_item__vendor')
            .order_by('id')
        )
        if not locked_cart_items:
            return JsonResponse({'error': 'Cart is empty'}, status=400)

        menu_items = {
            menu_item.id: menu_item
            for menu_item in MenuItem.objects.select_for_update().filter(
                id__in=[cart_item.menu_item_id for cart_item in locked_cart_items]
            ).select_related('vendor')
        }

        grouped_items = {}
        for cart_item in locked_cart_items:
            menu_item = menu_items[cart_item.menu_item_id]
            if not menu_item.is_active:
                return JsonResponse({'error': f'{menu_item.name} is no longer available.'}, status=400)
            try:
                _validate_menu_item_quantity(menu_item, cart_item.quantity)
            except ValueError as exc:
                return JsonResponse({'error': str(exc)}, status=400)

            menu_item.stock -= cart_item.quantity
            menu_item.save(update_fields=['stock'])
            vendor_group = grouped_items.setdefault(menu_item.vendor_id, {
                'vendor': menu_item.vendor,
                'items': [],
                'total': Decimal('0.00'),
            })
            vendor_group['items'].append((cart_item, menu_item))
            vendor_group['total'] += menu_item.price * cart_item.quantity

        orders = []
        for vendor_data in grouped_items.values():
            order = Order.objects.create(
                student=request.user,
                vendor=vendor_data['vendor'],
                total_amount=vendor_data['total'],
                delivery_address=delivery_address,
                payment_status=Order.PaymentStatus.PENDING,
            )

            for cart_item, menu_item in vendor_data['items']:
                OrderItem.objects.create(
                    order=order,
                    vendor_item=menu_item,
                    item_name=menu_item.name,
                    unit_price=menu_item.price,
                    quantity=cart_item.quantity,
                )

            orders.append(order)

        Payment.objects.create(
            order=orders[0],  # Associate with first order for tracking
            student=request.user,
            razorpay_order_id=razorpay_order['id'],
            amount=total_amount,
            currency='INR',
            status=Payment.PaymentStatus.PENDING,
        )
    
    return JsonResponse({
        'success': True,
        'razorpay_order_id': razorpay_order['id'],
        'amount': int(total_amount * 100),
        'orders': [o.id for o in orders],
    })


@login_required
@require_http_methods(["POST"])
def student_verify_payment(request):
    """Verify Razorpay payment and update order status."""
    if request.user.role != User.Role.STUDENT:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    try:
        data = json.loads(request.body)
    except:
        return JsonResponse({'error': 'Invalid request'}, status=400)
    
    razorpay_order_id = data.get('razorpay_order_id')
    razorpay_payment_id = data.get('razorpay_payment_id')
    razorpay_signature = data.get('razorpay_signature')
    
    if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
        return JsonResponse({'error': 'Missing payment details'}, status=400)
    
    # Verify payment signature
    try:
        razorpay_client = razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        )
        razorpay_client.utility.verify_payment_signature({
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature,
        })
    except Exception as e:
        return JsonResponse({'error': f'Payment verification failed: {str(e)}'}, status=400)
    
    # Update payment record
    try:
        payment = Payment.objects.get(razorpay_order_id=razorpay_order_id)
        payment.razorpay_payment_id = razorpay_payment_id
        payment.razorpay_signature = razorpay_signature
        payment.status = Payment.PaymentStatus.SUCCESS
        payment.save()
        
        # Update all orders for this payment
        related_orders = Order.objects.filter(
            student=request.user,
            id__in=data.get('order_ids') or [],
            payment_status=Order.PaymentStatus.PENDING,
        )
        
        for order in related_orders:
            order.payment_status = Order.PaymentStatus.COMPLETED
            order.save()
            
            _notify_user(
                request.user,
                order,
                f"Payment successful! Your order {order.order_code} has been placed.",
                email_subject='Payment Successful',
            )

        cart = Cart.objects.filter(student=request.user).first()
        if cart:
            cart.items.all().delete()
    except Payment.DoesNotExist:
        return JsonResponse({'error': 'Payment record not found'}, status=404)
    
    return JsonResponse({
        'success': True,
        'message': 'Payment verified successfully',
    })


@login_required
@require_http_methods(["POST"])
def student_cancel_payment(request):
    """Mark newly created orders as cancelled when payment is abandoned."""
    if request.user.role != User.Role.STUDENT:
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid request'}, status=400)

    razorpay_order_id = (data.get('razorpay_order_id') or '').strip()
    raw_order_ids = data.get('order_ids') or []
    cancellation_reason = (data.get('reason') or 'Payment cancelled').strip()

    if not razorpay_order_id or not isinstance(raw_order_ids, list):
        return JsonResponse({'error': 'Missing cancellation details'}, status=400)

    orders = list(
        Order.objects.filter(
            student=request.user,
            id__in=raw_order_ids,
            payment_status=Order.PaymentStatus.PENDING,
        )
    )

    if not orders:
        return JsonResponse({
            'success': True,
            'message': 'No pending orders needed cancellation.',
        })

    payment = Payment.objects.filter(
        student=request.user,
        razorpay_order_id=razorpay_order_id,
    ).first()

    if payment and payment.status == Payment.PaymentStatus.SUCCESS:
        return JsonResponse({
            'success': False,
            'error': 'Payment already completed for this order.',
        }, status=400)

    _cancel_pending_checkout_orders(
        request.user,
        cancellation_reason,
        order_ids=raw_order_ids,
        razorpay_order_id=razorpay_order_id,
    )

    return JsonResponse({
        'success': True,
        'message': 'Pending orders cancelled successfully.',
    })


@login_required
def student_orders(request):
    """Display all orders for the student."""
    if request.user.role != User.Role.STUDENT:
        messages.error(request, 'Unauthorized access')
        return redirect('login')
    
    orders = Order.objects.filter(student=request.user).select_related(
        'vendor', 'payment'
    ).prefetch_related('items', 'notifications', 'delivery_assignment').order_by('-created_at')
    
    return render(request, 'student/orders.html', {
        'orders': orders,
    })


@login_required
def student_order_detail(request, order_id: int):
    """Display order details with delivery tracking."""
    if request.user.role != User.Role.STUDENT:
        messages.error(request, 'Unauthorized access')
        return redirect('login')
    
    order = get_object_or_404(Order, id=order_id, student=request.user)
    items = order.items.all()
    delivery_assignment = order.delivery_assignment if hasattr(order, 'delivery_assignment') else None
    tracking_updates = list(order.tracking_updates.all()[:100])
    order_is_cancelled = (
        order.payment_status == Order.PaymentStatus.FAILED
        or order.vendor_decision == Order.VendorDecision.REJECTED
        or order.vendor_status == Order.VendorStatus.CANCELLED
    )

    student_location = None
    if order.delivery_address:
        try:
            maps_link, _ = _generate_google_maps_link_from_address(order.delivery_address)
            coords = _parse_google_maps_coordinates(maps_link)
            if coords:
                student_location = {'lat': coords[0], 'lng': coords[1]}
        except Exception:
            student_location = None
    
    return render(request, 'student/order_detail.html', {
        'order': order,
        'items': items,
        'delivery_assignment': delivery_assignment,
        'tracking_updates': tracking_updates,
        'order_is_cancelled': order_is_cancelled,
        'google_maps_api_key': settings.GOOGLE_MAPS_API_KEY,
        'student_location_json': json.dumps(student_location),
    })


@login_required
def student_order_history(request):
    """Display order history for the student - completed orders for reordering."""
    if request.user.role != User.Role.STUDENT:
        messages.error(request, 'Unauthorized access')
        return redirect('login')
    
    # Get all completed/delivered orders
    history_orders = Order.objects.filter(
        student=request.user,
        delivery_status=Order.DeliveryStatus.DELIVERED
    ).select_related('vendor').prefetch_related('items').order_by('-updated_at')
    
    # Group by vendor for quick reordering
    vendors_with_orders = {}
    for order in history_orders:
        vendor_id = order.vendor.id
        if vendor_id not in vendors_with_orders:
            vendors_with_orders[vendor_id] = {
                'vendor': order.vendor,
                'orders': []
            }
        vendors_with_orders[vendor_id]['orders'].append(order)
    
    return render(request, 'student/order_history.html', {
        'history_orders': history_orders,
        'vendors_with_orders': list(vendors_with_orders.values()),
    })


@login_required
@require_http_methods(["POST"])
def student_quick_reorder_from_order(request, order_id: int):
    """Add all items from a previous order to the cart for quick reordering."""
    if request.user.role != User.Role.STUDENT:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    order = get_object_or_404(Order, id=order_id, student=request.user, delivery_status=Order.DeliveryStatus.DELIVERED)
    
    # Get or create cart
    cart, _ = Cart.objects.get_or_create(student=request.user)
    
    items_count = 0
    for item in order.items.all():
        # Get the current menu item (in case it exists and is still active)
        if item.vendor_item and item.vendor_item.is_active:
            reorder_quantity = min(item.quantity, item.vendor_item.stock)
            if reorder_quantity < 1:
                continue
            cart_item, created = CartItem.objects.get_or_create(
                cart=cart,
                menu_item=item.vendor_item,
                defaults={'quantity': reorder_quantity}
            )
            
            if not created:
                cart_item.quantity = min(
                    cart_item.quantity + item.quantity,
                    item.vendor_item.stock,
                )
                cart_item.save()
            
            items_count += 1
    
    if items_count == 0:
        return JsonResponse({
            'success': False,
            'error': 'Items from this order are no longer available'
        }, status=400)
    
    return JsonResponse({
        'success': True,
        'message': f'Added {items_count} item{"s" if items_count > 1 else ""} to your cart!',
        'items_count': items_count,
        'redirect': '/users/student/cart/',
    })


@login_required
@require_http_methods(["POST"])
def delivery_partner_update_location(request, order_id: int):
    """Delivery partner sends real-time location update."""
    if request.user.role != User.Role.DELIVERY:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    try:
        data = json.loads(request.body)
        latitude = float(data.get('latitude'))
        longitude = float(data.get('longitude'))
        accuracy = float(data.get('accuracy', 0))
    except (json.JSONDecodeError, TypeError, ValueError):
        return JsonResponse({'error': 'Invalid location data'}, status=400)
    
    order = get_object_or_404(Order, id=order_id)
    
    # Verify this delivery partner is assigned to this order
    if not hasattr(order, 'delivery_assignment') or order.delivery_assignment.delivery_partner != request.user:
        return JsonResponse({'error': 'Not assigned to this order'}, status=403)
    
    # Create tracking update
    tracking = OrderTracking.objects.create(
        order=order,
        delivery_partner=request.user,
        latitude=latitude,
        longitude=longitude,
        accuracy=accuracy,
    )
    
    return JsonResponse({
        'success': True,
        'message': 'Location updated',
        'tracking_id': tracking.id,
    })


@login_required
def get_order_tracking_updates(request, order_id: int):
    """Get real-time tracking updates for an order (JSON API)."""
    if request.user.role != User.Role.STUDENT:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    order = get_object_or_404(Order, id=order_id, student=request.user)
    tracking_updates = list(order.tracking_updates.values(
        'id', 'latitude', 'longitude', 'accuracy', 'timestamp'
    )[:50])
    
    delivery_info = None
    if hasattr(order, 'delivery_assignment') and order.delivery_assignment:
        da = order.delivery_assignment
        delivery_info = {
            'name': da.partner_name,
            'phone': da.partner_phone,
            'vehicle': da.partner_vehicle,
        }
    
    # Parse vendor location from google_maps_location
    vendor_location = {'latitude': 26.5124, 'longitude': 80.2394}  # Default: IIT Kanpur
    if order.vendor and order.vendor.google_maps_location:
        coords = _parse_google_maps_coordinates(order.vendor.google_maps_location)
        if coords:
            vendor_location = {'latitude': coords[0], 'longitude': coords[1]}
    
    return JsonResponse({
        'order_id': order.id,
        'order_code': order.order_code,
        'status': order.delivery_status,
        'delivery_info': delivery_info,
        'tracking_updates': tracking_updates,
        'vendor_location': vendor_location
    })


# ─── Delivery Module Views ────────────────────────────────────────────────────

@login_required
@require_http_methods(["POST"])
def vendor_broadcast_delivery(request, order_id: int):
    """
    Vendor marks order as READY and broadcasts to all delivery personnel.
    """
    if request.user.role != User.Role.VENDOR:
        messages.error(request, 'Unauthorized access')
        return redirect('login')
    
    vendor_profile = get_object_or_404(VendorProfile, user=request.user)
    order = get_object_or_404(Order, id=order_id, vendor=vendor_profile)
    
    if order.vendor_status != Order.VendorStatus.READY:
        messages.error(request, 'Order must be marked as ready first.')
        return redirect('vendor_dashboard')
    
    # Check if broadcast already exists
    if hasattr(order, 'delivery_broadcast') and order.delivery_broadcast.status == DeliveryBroadcast.BroadcastStatus.ACTIVE:
        messages.info(request, 'This order has already been broadcast to delivery personnel.')
        return redirect('vendor_dashboard')

    if not vendor_profile.google_maps_address or not vendor_profile.google_maps_location:
        messages.error(request, 'Add and save your outlet address on the map before broadcasting to delivery personnel.')
        return redirect('vendor_dashboard')
    
    # Get vendor location from profile
    pickup_lat, pickup_lng = None, None
    if vendor_profile.google_maps_location:
        coords = _parse_google_maps_coordinates(vendor_profile.google_maps_location)
        if coords:
            pickup_lat, pickup_lng = coords

    if pickup_lat is None or pickup_lng is None:
        messages.error(request, 'Your saved outlet map location is invalid. Please reselect it on the map and save again.')
        return redirect('vendor_dashboard')
    
    # Create broadcast
    expires_at = timezone.now() + timedelta(minutes=10)
    broadcast = DeliveryBroadcast.objects.create(
        order=order,
        status=DeliveryBroadcast.BroadcastStatus.ACTIVE,
        expires_at=expires_at,
        pickup_latitude=pickup_lat,
        pickup_longitude=pickup_lng,
    )
    
    # Create response entries for all active delivery personnel
    delivery_personnel = User.objects.filter(role=User.Role.DELIVERY)
    for personnel in delivery_personnel:
        DeliveryBroadcastResponse.objects.create(
            broadcast=broadcast,
            delivery_partner=personnel,
            status=DeliveryBroadcastResponse.ResponseStatus.PENDING,
        )
    
    # Notify all delivery personnel
    for personnel in delivery_personnel:
        _notify_user(
            personnel,
            order,
            f"New delivery request: {order.order_code} from {vendor_profile.outlet_name}. Order ready for pickup.",
            email_subject='New Delivery Request',
        )
    
    messages.success(request, 'Order broadcasted to delivery personnel successfully.')
    return redirect('vendor_dashboard')


@login_required
def delivery_available_orders(request):
    """
    Display all available delivery broadcasts for the logged-in delivery partner.
    """
    if request.user.role != User.Role.DELIVERY:
        messages.error(request, 'Unauthorized access')
        return redirect('login')
    
    now = timezone.now()
    DeliveryBroadcast.objects.filter(
        status=DeliveryBroadcast.BroadcastStatus.ACTIVE,
        expires_at__lt=now,
    ).update(status=DeliveryBroadcast.BroadcastStatus.EXPIRED)

    # Get accepted deliveries
    my_accepted = DeliveryAssignment.objects.filter(
        delivery_partner=request.user,
        status__in=[
            DeliveryAssignment.AssignmentStatus.ACCEPTED,
            DeliveryAssignment.AssignmentStatus.PICKED_UP,
            DeliveryAssignment.AssignmentStatus.OUT_FOR_DELIVERY,
        ]
    ).select_related('order', 'order__vendor', 'order__student')

    has_active_delivery = my_accepted.exists()

    available = []
    if not has_active_delivery:
        active_broadcasts = DeliveryBroadcast.objects.filter(
            status=DeliveryBroadcast.BroadcastStatus.ACTIVE
        ).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        ).select_related('order', 'order__vendor', 'order__student')

        my_responses = DeliveryBroadcastResponse.objects.filter(
            delivery_partner=request.user
        ).values('broadcast_id', 'status')
        response_dict = {r['broadcast_id']: r['status'] for r in my_responses}

        for broadcast in active_broadcasts:
            if broadcast.id not in response_dict or response_dict[broadcast.id] == DeliveryBroadcastResponse.ResponseStatus.PENDING:
                available.append(broadcast)
    
    return render(request, 'delivery/available_orders.html', {
        'broadcasts': available,
        'my_deliveries': my_accepted,
        'has_active_delivery': has_active_delivery,
    })


@login_required
@require_http_methods(["POST"])
def delivery_accept_broadcast(request, broadcast_id: int):
    """
    Delivery partner accepts a delivery broadcast.
    """
    if request.user.role != User.Role.DELIVERY:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    try:
        with transaction.atomic():
            broadcast = DeliveryBroadcast.objects.select_for_update().select_related(
                'order', 'order__student'
            ).get(id=broadcast_id)

            existing_assignment = DeliveryAssignment.objects.filter(order=broadcast.order).first()
            if existing_assignment:
                if existing_assignment.delivery_partner_id == request.user.id:
                    return JsonResponse({
                        'success': True,
                        'message': 'Delivery already accepted successfully',
                        'assignment_id': existing_assignment.id,
                    })
                return JsonResponse({'error': 'Already accepted by another partner'}, status=400)

            current_assignment = DeliveryAssignment.objects.filter(
                delivery_partner=request.user,
                status__in=[
                    DeliveryAssignment.AssignmentStatus.ACCEPTED,
                    DeliveryAssignment.AssignmentStatus.PICKED_UP,
                    DeliveryAssignment.AssignmentStatus.OUT_FOR_DELIVERY,
                ]
            ).first()
            if current_assignment:
                return JsonResponse({
                    'error': f'Complete your current delivery {current_assignment.order.order_code} before accepting another order.'
                }, status=400)

            if broadcast.status != DeliveryBroadcast.BroadcastStatus.ACTIVE:
                return JsonResponse({'error': 'Broadcast is no longer active'}, status=400)

            if broadcast.expires_at and timezone.now() > broadcast.expires_at:
                broadcast.status = DeliveryBroadcast.BroadcastStatus.EXPIRED
                broadcast.save(update_fields=['status'])
                return JsonResponse({'error': 'Broadcast has expired'}, status=400)

            if broadcast.accepted_by and broadcast.accepted_by_id != request.user.id:
                return JsonResponse({'error': 'Already accepted by another partner'}, status=400)

            broadcast.status = DeliveryBroadcast.BroadcastStatus.ACCEPTED
            broadcast.accepted_by = request.user
            broadcast.accepted_at = timezone.now()
            broadcast.save(update_fields=['status', 'accepted_by', 'accepted_at'])

            app = StaffApplication.objects.filter(
                email=request.user.email,
                role_applied='DELIVERY'
            ).first()

            assignment = DeliveryAssignment.objects.create(
                order=broadcast.order,
                delivery_partner=request.user,
                status=DeliveryAssignment.AssignmentStatus.ACCEPTED,
                accepted_at=timezone.now(),
                partner_name=request.user.get_full_name() or request.user.username,
                partner_phone=request.user.phone,
                partner_vehicle=app.vehicle_number if app else '',
            )

            DeliveryBroadcastResponse.objects.filter(
                broadcast=broadcast
            ).exclude(delivery_partner=request.user).update(
                status=DeliveryBroadcastResponse.ResponseStatus.CANCELLED,
                responded_at=timezone.now()
            )

            my_response, _ = DeliveryBroadcastResponse.objects.get_or_create(
                broadcast=broadcast,
                delivery_partner=request.user,
                defaults={'status': DeliveryBroadcastResponse.ResponseStatus.PENDING}
            )
            my_response.status = DeliveryBroadcastResponse.ResponseStatus.ACCEPTED
            my_response.responded_at = timezone.now()
            my_response.save()

            _notify_user(
                broadcast.order.student,
                broadcast.order,
                f'Your order {broadcast.order.order_code} has been accepted by a delivery partner and pickup is on the way.',
                email_subject='Delivery Partner Assigned',
            )

            return JsonResponse({
                'success': True,
                'message': 'Delivery accepted successfully',
                'assignment_id': assignment.id,
            })
    except DeliveryBroadcast.DoesNotExist:
        return JsonResponse({'error': 'Broadcast not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': f'Could not accept delivery: {str(e)}'}, status=500)


@login_required
@require_http_methods(["POST"])
def delivery_reject_broadcast(request, broadcast_id: int):
    """
    Delivery partner rejects a delivery broadcast.
    """
    if request.user.role != User.Role.DELIVERY:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    try:
        broadcast = get_object_or_404(DeliveryBroadcast, id=broadcast_id)
        reason = request.POST.get('reason', 'No reason provided')

        response, _ = DeliveryBroadcastResponse.objects.get_or_create(
            broadcast=broadcast,
            delivery_partner=request.user
        )
        response.status = DeliveryBroadcastResponse.ResponseStatus.REJECTED
        response.responded_at = timezone.now()
        response.response_reason = reason
        response.save()

        return JsonResponse({
            'success': True,
            'message': 'Broadcast rejected',
        })
    except Exception as e:
        return JsonResponse({'error': f'Could not reject delivery: {str(e)}'}, status=500)


@login_required
def delivery_navigation(request, assignment_id: int):
    """
    Show navigation for the current delivery leg.
    """
    if request.user.role != User.Role.DELIVERY:
        messages.error(request, 'Unauthorized access')
        return redirect('login')
    
    assignment = get_object_or_404(DeliveryAssignment, id=assignment_id, delivery_partner=request.user)
    broadcast = assignment.order.delivery_broadcast

    vendor_location = None
    if broadcast.pickup_latitude is not None and broadcast.pickup_longitude is not None:
        vendor_location = {
            'lat': float(broadcast.pickup_latitude),
            'lng': float(broadcast.pickup_longitude),
        }
    elif assignment.order.vendor.google_maps_location:
        coords = _parse_google_maps_coordinates(assignment.order.vendor.google_maps_location)
        if coords:
            vendor_location = {
                'lat': coords[0],
                'lng': coords[1],
            }

    student_location = None
    try:
        maps_link, _ = _generate_google_maps_link_from_address(assignment.order.delivery_address)
        coords = _parse_google_maps_coordinates(maps_link)
        if coords:
            student_location = {
                'lat': coords[0],
                'lng': coords[1],
            }
    except Exception:
        student_location = None

    active_leg = 'pickup'
    if assignment.status in [
        DeliveryAssignment.AssignmentStatus.PICKED_UP,
        DeliveryAssignment.AssignmentStatus.OUT_FOR_DELIVERY,
    ]:
        active_leg = 'delivery'
    
    return render(request, 'delivery/navigation.html', {
        'assignment': assignment,
        'order': assignment.order,
        'vendor': assignment.order.vendor,
        'broadcast': broadcast,
        'google_maps_api_key': settings.GOOGLE_MAPS_API_KEY,
        'vendor_location_json': json.dumps(vendor_location),
        'student_location_json': json.dumps(student_location),
        'active_leg': active_leg,
    })


@login_required
@require_http_methods(["POST"])
def delivery_mark_picked_up(request, assignment_id: int):
    """
    Mark order as picked up from vendor.
    """
    if request.user.role != User.Role.DELIVERY:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    assignment = get_object_or_404(DeliveryAssignment, id=assignment_id, delivery_partner=request.user)
    
    if assignment.status != DeliveryAssignment.AssignmentStatus.ACCEPTED:
        return JsonResponse({'error': 'Invalid status for pickup'}, status=400)
    
    assignment.status = DeliveryAssignment.AssignmentStatus.PICKED_UP
    assignment.picked_up_at = timezone.now()
    assignment.save()
    
    # Update order status
    order = assignment.order
    order.delivery_status = Order.DeliveryStatus.OUT_FOR_DELIVERY
    order.save()
    
    # Notify student
    _notify_user(
        order.student,
        order,
        f'Your order {order.order_code} has been picked up! View live tracking of your delivery.',
        email_subject='Order Picked Up',
    )
    
    return JsonResponse({
        'success': True,
        'message': 'Marked as picked up',
    })


@login_required
@require_http_methods(["POST"])
def delivery_start_delivery(request, assignment_id: int):
    """
    Mark order as out for delivery (vendor triggers when ready).
    """
    if request.user.role != User.Role.VENDOR:
        # Also allow delivery partner if they want to explicitly mark
        if request.user.role != User.Role.DELIVERY:
            return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    assignment = get_object_or_404(DeliveryAssignment, id=assignment_id)
    
    if assignment.status not in [
        DeliveryAssignment.AssignmentStatus.ACCEPTED,
        DeliveryAssignment.AssignmentStatus.PICKED_UP
    ]:
        return JsonResponse({'error': 'Invalid status'}, status=400)
    
    assignment.status = DeliveryAssignment.AssignmentStatus.OUT_FOR_DELIVERY
    assignment.out_for_delivery_at = timezone.now()
    assignment.save()
    
    # Update order status
    order = assignment.order
    order.delivery_status = Order.DeliveryStatus.OUT_FOR_DELIVERY
    order.save()
    
    # Notify student with tracking link
    _notify_user(
        order.student,
        order,
        f'🚗 Your order {order.order_code} is out for delivery! View live tracking now.',
        email_subject='Order Out For Delivery',
    )
    
    return JsonResponse({
        'success': True,
        'message': 'Order marked as out for delivery',
    })


@login_required
@require_http_methods(["POST"])
def delivery_mark_delivered(request, assignment_id: int):
    """
    Mark order as delivered by delivery partner.
    """
    if request.user.role != User.Role.DELIVERY:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    assignment = get_object_or_404(DeliveryAssignment, id=assignment_id, delivery_partner=request.user)
    
    if assignment.status != DeliveryAssignment.AssignmentStatus.OUT_FOR_DELIVERY:
        return JsonResponse({'error': 'Order must be out for delivery first'}, status=400)
    
    assignment.status = DeliveryAssignment.AssignmentStatus.DELIVERED
    assignment.delivered_at = timezone.now()
    assignment.save()
    
    # Update order status
    order = assignment.order
    order.delivery_status = Order.DeliveryStatus.DELIVERED
    order.save()
    
    # Notify student
    _notify_user(
        order.student,
        order,
        f'✅ Your order {order.order_code} has been delivered! Please rate your experience.',
        email_subject='Order Delivered',
    )
    
    return JsonResponse({
        'success': True,
        'message': 'Order marked as delivered',
    })


def _parse_google_maps_coordinates(maps_url: str) -> tuple:
    """
    Extract lat, lng from Google Maps URL.
    Format: https://www.google.com/maps/search/?api=1&query=28.123,-45.456
    """
    try:
        if 'query=' in maps_url:
            query_part = maps_url.split('query=')[1].split('&')[0]
            parts = query_part.split(',')
            if len(parts) == 2:
                lat = float(parts[0].strip())
                lng = float(parts[1].strip())
                return (lat, lng)
    except:
        pass
    return None


@login_required
@require_http_methods(["POST"])
def delivery_send_location(request, assignment_id: int):
    """
    Delivery partner sends real-time location updates.
    """
    if request.user.role != User.Role.DELIVERY:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    try:
        data = json.loads(request.body)
        latitude = float(data.get('latitude'))
        longitude = float(data.get('longitude'))
        accuracy = float(data.get('accuracy', 0))
    except (json.JSONDecodeError, TypeError, ValueError):
        return JsonResponse({'error': 'Invalid location data'}, status=400)
    
    assignment = get_object_or_404(DeliveryAssignment, id=assignment_id, delivery_partner=request.user)
    order = assignment.order
    
    # Create tracking update
    tracking = OrderTracking.objects.create(
        order=order,
        delivery_partner=request.user,
        latitude=latitude,
        longitude=longitude,
        accuracy=accuracy,
    )
    
    return JsonResponse({
        'success': True,
        'message': 'Location updated',
        'tracking_id': tracking.id,
    })
