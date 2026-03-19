from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.conf import settings
from .models import User, StaffApplication


# ─── Register (Students Only) ─────────────────────────────────────────────────
def register_view(request):
    if request.method == 'POST':
        username   = request.POST.get('username')
        email      = request.POST.get('email')
        phone      = request.POST.get('phone')
        password1  = request.POST.get('password1')
        password2  = request.POST.get('password2')

        # validations
        if password1 != password2:
            messages.error(request, 'Passwords do not match')
            return render(request, 'users/register.html')

        if not email.endswith(settings.ALLOWED_EMAIL_DOMAIN):
            messages.error(request, f'Only {settings.ALLOWED_EMAIL_DOMAIN} emails are allowed')
            return render(request, 'users/register.html')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already taken')
            return render(request, 'users/register.html')

        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already registered')
            return render(request, 'users/register.html')

        # create user
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password1,
            phone=phone,
            role=User.Role.STUDENT
        )
        messages.success(request, 'Account created! Please log in.')
        return redirect('login')

    return render(request, 'users/register.html')


# ─── Login ────────────────────────────────────────────────────────────────────
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            if user.role == User.Role.STUDENT:
                return redirect('student_dashboard')
            elif user.role == User.Role.VENDOR:
                return redirect('vendor_dashboard')
            elif user.role == User.Role.DELIVERY:
                return redirect('delivery_dashboard')
        else:
            messages.error(request, 'Invalid username or password')

    return render(request, 'users/login.html')


# ─── Logout ───────────────────────────────────────────────────────────────────
def logout_view(request):
    logout(request)
    return redirect('login')


# ─── Vendor/Delivery Application ─────────────────────────────────────────────
def apply_view(request):
    if request.method == 'POST':
        role_applied = request.POST.get('role_applied')

        if StaffApplication.objects.filter(email=request.POST.get('email')).exists():
            messages.error(request, 'An application with this email already exists')
            return render(request, 'users/apply.html')

        application = StaffApplication(
            full_name        = request.POST.get('full_name'),
            email            = request.POST.get('email'),
            phone            = request.POST.get('phone'),
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


# ─── Placeholder Dashboards (built later) ────────────────────────────────────
def student_dashboard(request):
    return render(request, 'student/dashboard.html')

def vendor_dashboard(request):
    return render(request, 'vendor/dashboard.html')

def delivery_dashboard(request):
    return render(request, 'delivery/dashboard.html')