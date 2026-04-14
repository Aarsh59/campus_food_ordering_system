# Campus Food Ordering System 🍔

A comprehensive web-based food ordering platform designed for IIT Kanpur campus. This system enables students to order food from campus vendors, vendors to manage their outlets and orders, and a delivery system to ensure timely delivery of meals.

**Course Project:** CS253 (Software Development)

## Table of Contents

- [Features](#features)
- [Project Overview](#project-overview)
- [Tech Stack](#tech-stack)
- [Installation & Setup](#installation--setup)
- [Project Structure](#project-structure)
- [User Roles](#user-roles)
- [Database Models](#database-models)
- [API Endpoints](#api-endpoints)
- [Key Features & Usage](#key-features--usage)
- [Admin Panel](#admin-panel)
- [Development](#development)

## Features

### 🎓 Student Features
- **User Registration & Authentication** - OTP-based email verification for students
- **Vendor Browsing** - Browse available food vendors and their menus
- **Smart Shopping Cart** - Add/remove items from multi-vendor cart
- **Secure Checkout** - Choose delivery location and payment method
- **Payment Integration** - Razorpay integration for online payments, COD support
- **Order Tracking** - Real-time order tracking with delivery partner location
- **Order History** - View past orders and quick reorder functionality
- **Notifications** - Email and SMS alerts for order status updates

### 🏪 Vendor Features
- **Vendor Application** - Vendors apply with outlet details, FSSAI, GST, banking info
- **Admin Approval System** - Admins review and approve vendor applications
- **Outlet Management** - Update outlet name, location on interactive map
- **Menu Management** - Add/update/delete food items with prices and stock
- **Order Management** - Accept/reject incoming orders, track preparation
- **Delivery Broadcasting** - Broadcast orders to available delivery partners
- **Real-time Updates** - Live order status updates

### 🚚 Delivery Partner Features
- **Delivery Application** - Apply with vehicle and license information
- **Available Orders Dashboard** - Browse active delivery broadcasts
- **Assignment Management** - Accept/reject delivery assignments
- **Real-time Tracking** - Send live location updates to students
- **Delivery Workflow** - Mark orders as picked up, out for delivery, delivered

### 👨‍💼 Admin Features
- **Application Review Dashboard** - Beautiful interface to review vendor/delivery applications
- **Application Filtering** - Filter by role, status, and search by name/email/phone
- **Detailed Application Review** - View complete application with all documents
- **Approval/Rejection** - One-click approval/rejection with admin notes
- **User Management** - Manage user accounts and roles
- **System Monitoring** - View orders, payments, and system activity

## Project Overview

### Multi-Tier Architecture
- **Frontend:** Django Templates with Bootstrap 5 for responsive UI
- **Backend:** Django REST Framework for API endpoints
- **Database:** SQLite/PostgreSQL with Django ORM
- **Real-time Features:** JavaScript polling for order tracking

### Key Workflows

**Order Flow:**
1. Student adds items from vendors to cart
2. Groups items by vendor
3. Creates one Order per vendor + one Payment record
4. Payment processed (Razorpay or COD)
5. Vendor receives notification and accepts/rejects
6. If accepted, delivery partner is broadcasted
7. Delivery partner picks up and delivers
8. Student receives delivery notification
9. Payment marked complete at delivery (for COD)

**Vendor Application Flow:**
1. Applicant submits vendor application with required documents
2. Admin reviews application in dedicated dashboard
3. Admin approves/rejects with optional notes
4. Signal handler creates User account + VendorProfile
5. Login credentials sent via email & SMS
6. Vendor can login and set up outlet & menu

## Tech Stack

### Backend
- **Framework:** Django 4.x
- **API:** Django REST Framework
- **Database:** SQLite (development), PostgreSQL (production)
- **Authentication:** Django auth + OTP verification
- **Payment:** Razorpay SDK

### Frontend
- **Template Engine:** Django Templates + Jinja2
- **CSS Framework:** Bootstrap 5
- **JavaScript:** Vanilla JS + jQuery for AJAX
- **Maps:** Google Maps API for location services

### Additional Tools
- **File Storage:** Django FileField + Media handling
- **Email:** Django email backend
- **SMS:** Integrated SMS provider
- **Signals:** Django signals for automated workflows

## Installation & Setup

### Prerequisites
- Python 3.8+
- pip or conda
- Git
- Google Maps API Key (for location features)
- Razorpay account (for payment processing)

### Step 1: Clone Repository
```bash
git clone <repository-url>
cd campus_food_ordering_system
```

### Step 2: Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment
Create a `.env` file in the project root:
```
DEBUG=True
SECRET_KEY=your-secret-key-here
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=sqlite:///db.sqlite3

# Email Configuration
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password

# Google Maps API
GOOGLE_MAPS_API_KEY=your-google-maps-api-key

# Razorpay Configuration
RAZORPAY_KEY_ID=your-razorpay-key-id
RAZORPAY_KEY_SECRET=your-razorpay-secret

# SMS Configuration (if using)
SMS_PROVIDER_API_KEY=your-sms-api-key

# Campus Settings
ALLOWED_EMAIL_DOMAIN=iitk.ac.in
SESSION_INACTIVITY_TIMEOUT=2592000  # 30 days in seconds
```

### Step 5: Run Migrations
```bash
python manage.py migrate
```

### Step 6: Create Superuser (Admin)
```bash
python manage.py createsuperuser
```

### Step 7: Create Sample Data (Optional)
```bash
python manage.py loaddata sample_data  # If available
```

### Step 8: Run Development Server
```bash
python manage.py runserver
```

Visit `http://localhost:8000` to access the application.

## Project Structure

```
campus_food_ordering_system/
├── backend/                      # Django project settings
│   ├── settings.py               # Project configuration
│   ├── urls.py                   # Main URL routing
│   ├── wsgi.py                   # WSGI application
│   └── asgi.py                   # ASGI application
│
├── users/                        # Main app (students, vendors, delivery)
│   ├── models.py                 # Database models
│   ├── views.py                  # View functions
│   ├── urls.py                   # URL routing
│   ├── admin.py                  # Django admin configuration
│   ├── signals.py                # Django signals (auto approvals)
│   ├── email_utils.py            # Email sending utilities
│   ├── sms_utils.py              # SMS sending utilities
│   ├── otp_utils.py              # OTP generation & verification
│   ├── forms.py                  # Django forms
│   ├── tests.py                  # Unit tests
│   ├── middleware.py             # Custom middleware
│   ├── username_validation.py    # Username validation logic
│   └── migrations/               # Database migrations
│
├── templates/                    # HTML templates
│   ├── base.html                 # Base template
│   ├── admin/                    # Admin templates
│   │   ├── applications_list.html
│   │   └── application_detail.html
│   ├── student/                  # Student templates
│   ├── vendor/                   # Vendor templates
│   ├── delivery/                 # Delivery templates
│   ├── users/                    # Auth templates
│   └── registration/             # Password reset templates
│
├── staticfiles/                  # Compiled static files
├── media/                        # User uploaded files
│   ├── documents/                # Aadhaar, FSSAI documents
│   └── menu_photos/              # Menu item photos
│
├── db.sqlite3                    # SQLite database
├── manage.py                     # Django management script
├── requirements.txt              # Python dependencies
├── Procfile                      # Heroku deployment config
├── .env                          # Environment variables (not in git)
├── README.md                     # This file
├── QUICK_START.md                # Quick setup guide
└── STUDENT_DASHBOARD_SETUP.md    # Student setup documentation
```

## User Roles

### 1. **Student**
- Role: `User.Role.STUDENT`
- Capabilities:
  - Browse vendors and menus
  - Add items to cart (multi-vendor)
  - Checkout and pay for orders
  - Track orders in real-time
  - View order history
  - Rate orders

### 2. **Vendor**
- Role: `User.Role.VENDOR`
- Capabilities:
  - Submit vendor application
  - Manage outlet details
  - Manage menu items with stock
  - Accept/reject incoming orders
  - Update order preparation status
  - Broadcast orders to delivery partners

### 3. **Delivery Partner**
- Role: `User.Role.DELIVERY`
- Capabilities:
  - Submit delivery application
  - Browse available delivery broadcasts
  - Accept delivery assignments
  - Track delivery with real-time GPS
  - Update delivery status
  - Mark orders as delivered

### 4. **Admin**
- Role: User with `is_staff=True`
- Capabilities:
  - Review vendor/delivery applications
  - Approve/reject applications with notes
  - Manage all user accounts
  - View all orders and payments
  - Access Django admin panel

## Database Models

### Core Models

**User**
- Username (unique, ASCII only)
- Email (unique)
- Phone (10-digit)
- Role (Student, Vendor, Delivery)
- Is staff (for admins)
- First/Last name
- Account status

**StaffApplication**
- Full name, Email, Phone
- Role applied (Vendor, Delivery)
- Status (Pending, Approved, Rejected)
- Aadhaar number & document
- Applied at, Reviewed at
- Admin notes

**Vendor-Specific Fields:**
- Outlet name, Location
- Cuisine type
- FSSAI license & document
- GST number
- Bank account, IFSC code
- College NOC
- Operating hours

**Delivery-Specific Fields:**
- Vehicle type & number
- Driving license & document
- Emergency contact

**VendorProfile**
- User (OneToOne)
- Outlet name
- Google Maps location (link & address)
- Cuisine type
- Operating hours

**MenuItem**
- Vendor (ForeignKey)
- Name, Description, Price
- Photo (image)
- Stock (quantity available)
- Is active (soft delete)
- Created/Updated timestamps

**Order**
- Student (FK)
- Vendor (FK via VendorProfile)
- Order code (unique)
- Payment status
- Vendor decision (accept/reject)
- Vendor status (preparing/ready/cancelled)
- Delivery status (tracking/out/delivered)
- Delivery address
- Created/Updated timestamps

**OrderItem**
- Order (FK)
- MenuItem (FK)
- Quantity
- Price at order time

**Cart** & **CartItem**
- One cart per student
- Multiple items from multiple vendors
- Unique constraint on (cart, menu_item)

**Payment**
- Order (FK)
- Student (FK)
- Status (Pending, Completed, Failed, Refunded)
- Razorpay order ID & payment ID
- Amount in paise
- Created/Updated timestamps

**DeliveryAssignment**
- Delivery partner (FK)
- Order (FK)
- Status (Accepted, Picked up, Out for delivery, Delivered)
- Timestamps for each status

**OrderTracking**
- Order (FK)
- Delivery partner (FK)
- Latitude, Longitude, Accuracy
- Timestamp

## API Endpoints

### Authentication
- `POST /login/` - User login
- `POST /logout/` - User logout
- `POST /register/` - Student registration
- `POST /otp/send/` - Send OTP for registration/application

### Student APIs
- `GET /student/dashboard/` - Student dashboard
- `GET /student/vendors/` - List all vendors
- `GET /student/vendor/<id>/` - Vendor detail with menu
- `POST /student/add-to-cart/` - Add item to cart
- `GET /student/cart/` - View cart
- `POST /student/checkout/` - Proceed to checkout
- `POST /student/order/create/` - Create order(s)
- `POST /student/order/verify-payment/` - Verify Razorpay payment
- `GET /student/orders/` - Active orders
- `GET /student/order/<id>/tracking/` - Real-time order tracking
- `GET /student/order-history/` - Order history

### Vendor APIs
- `POST /apply/` - Submit vendor application
- `GET /pending/` - Check application status
- `GET /vendor/dashboard/` - Dashboard with incoming orders
- `POST /vendor/menu/add/` - Add menu item
- `POST /vendor/menu/<id>/update/` - Update menu item
- `POST /vendor/tickets/<id>/accept/` - Accept order
- `POST /vendor/tickets/<id>/reject/` - Reject order
- `POST /vendor/orders/<id>/status/` - Update order status

### Delivery APIs
- `GET /delivery/dashboard/` - Delivery dashboard
- `GET /delivery/available-orders/` - Available broadcasts
- `POST /delivery/broadcast/<id>/accept/` - Accept delivery
- `POST /delivery/assignment/<id>/picked-up/` - Mark picked up
- `POST /delivery/assignment/<id>/location/` - Send location update
- `POST /delivery/assignment/<id>/delivered/` - Mark delivered

### Admin APIs
- `GET /admin/applications/` - List all applications
- `GET /admin/applications/<id>/` - Application detail
- `POST /admin/applications/<id>/` - Approve/reject application

## Key Features & Usage

### 1. OTP-Based Registration
- Students verify email with OTP before registration
- Applicants verify email before submitting staff applications
- Prevents fake email registrations

### 2. Multi-Vendor Shopping Cart
- Cart is specific to each student
- Can add items from multiple vendors
- Items grouped by vendor at checkout
- Creates separate Orders for each vendor

### 3. Payment Processing
```
Razorpay Flow:
1. Create Razorpay Order (amount in paise: ₹100 = 10000 paise)
2. Frontend opens Razorpay modal with order_id
3. User completes payment in Razorpay
4. Frontend calls verify endpoint with payment details
5. Backend verifies signature using Razorpay client
6. Mark order payment as complete

COD Flow:
1. Create order with payment_method=COD
2. Payment status = PENDING
3. On delivery completion, payment marked COMPLETED
```

### 4. Real-Time Order Tracking
- Delivery partner sends GPS location every 5 seconds
- Frontend polls `/api/tracking/` endpoint
- Displays delivery partner on Google Map
- Shows real-time location updates to student

### 5. Vendor Application System
- Comprehensive application form with document upload
- Admin dashboard to review applications
- Signal handler auto-creates User & VendorProfile
- Email/SMS notifications sent automatically
- No more cumbersome Django admin usage!

### 6. Delivery Broadcasting
- Vendor broadcasts order to all delivery partners
- Partners can accept within broadcast window
- Auto-expires if not accepted in time
- First to accept gets the assignment

## Admin Panel

### Accessing Admin Features

**Option 1: Admin Application Review Dashboard** (Recommended)
1. Login as staff/admin user
2. Navigate to `http://localhost:8000/admin/applications/`
3. Browse, search, and filter applications
4. Click "Review" on any application
5. View all details and documents
6. Approve or reject with admin notes

**Option 2: Django Admin** (Classic)
1. Login as superuser
2. Navigate to `http://localhost:8000/admin/`
3. Find "Staff Applications"
4. Use admin actions to approve/reject

### Application Review Workflow

**Vendor Application Review:**
1. View applicant's outlet details (name, cuisine, location, hours)
2. Review regulatory documents (FSSAI, GST, NOC)
3. Check banking information (account, IFSC)
4. Approve → User account created, credentials sent via email/SMS
5. Reject → Applicant notified via email

**Delivery Application Review:**
1. View vehicle and license information
2. Verify driving license document
3. Check emergency contact details
4. Approve → User account created
5. Reject → Applicant notified

## Development

### Running Tests
```bash
python manage.py test users.tests
```

### Creating Migrations
```bash
python manage.py makemigrations
python manage.py migrate
```

### Database
- Development: SQLite (db.sqlite3)
- Production: PostgreSQL recommended

### Static Files
```bash
python manage.py collectstatic
```

### Code Quality
- Follow PEP 8
- Use meaningful variable names
- Add docstrings to functions
- Use type hints where applicable

## Deployment

### Heroku Deployment
```bash
heroku create your-app-name
heroku config:set SECRET_KEY=your-secret-key
heroku config:set GOOGLE_MAPS_API_KEY=your-key
git push heroku main
heroku run python manage.py migrate
heroku run python manage.py createsuperuser
```

### Environment Variables Needed
- `SECRET_KEY` - Django secret key
- `DEBUG` - Set to False in production
- `ALLOWED_HOSTS` - Comma-separated domain list
- `DATABASE_URL` - PostgreSQL connection string
- `GOOGLE_MAPS_API_KEY` - For location services
- `RAZORPAY_KEY_ID` - Razorpay public key
- `RAZORPAY_KEY_SECRET` - Razorpay secret key
- Email and SMS provider credentials

## Troubleshooting

**Email not sending?**
- Check `EMAIL_HOST_USER` and `EMAIL_HOST_PASSWORD`
- Ensure "Less secure apps" enabled (if using Gmail)
- Check email logs in admin notifications

**Razorpay payment failing?**
- Verify Key ID and Secret in .env
- Check amount is in paise (multiply by 100)
- Ensure signature verification is correct

**Google Maps not showing?**
- Validate API key is active
- Check API quotas on Google Cloud Console
- Enable Maps APIs and Geocoding APIs

**OTP not sending?**
- Verify email configuration
- Check spam folder
- Ensure email provider isn't blocking

## Contributing

To contribute to this project:
1. Create a feature branch (`git checkout -b feature/amazing-feature`)
2. Commit your changes (`git commit -m 'Add amazing feature'`)
3. Push to branch (`git push origin feature/amazing-feature`)
4. Open a Pull Request

## License

This project is created for CS253 - Software Development course at IIT Kanpur.

## Support

For issues, questions, or suggestions, please open an issue on the repository.

---

**Last Updated:** April 2026
**Version:** 1.0
**Author:** Campus Food Ordering System Team
