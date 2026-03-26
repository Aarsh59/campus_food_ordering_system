# Campus Food Ordering System - Student Dashboard Setup Guide

## Overview
The student dashboard is a comprehensive food ordering system with multi-vendor support, shopping cart functionality, Razorpay payment integration, and real-time delivery tracking with Google Maps.

## Features Implemented

### 1. **Vendor Discovery** 🏪
- Browse all available vendors on campus
- View vendor profiles (outlet name, cuisine type, operating hours, location)
- Quick access to Google Maps for directions
- See number of menu items per vendor

**Routes:**
- `/users/student/vendors/` - List all vendors
- `/users/student/vendor/<vendor_id>/` - View vendor menu

### 2. **Shopping Cart** 🛒
- Add items from multiple vendors to one cart
- Quantity adjustment
- Remove items
- Automatic cart total calculation
- Grouped view by vendor

**Routes:**
- `/users/student/cart/add/` - Add item to cart
- `/users/student/cart/` - View cart
- `/users/student/cart/remove/<item_id>/` - Remove from cart
- `/users/student/cart/update/<item_id>/` - Update quantity

### 3. **Checkout & Payment** 💳
- Enter delivery address
- Review order summary grouped by vendor
- Razorpay payment gateway integration
- Real-time payment processing
- Stock snapshot preservation (prices at order time)

**Routes:**
- `/users/student/checkout/` - Checkout page
- `/users/student/order/create/` - Create order and initiate payment
- `/users/student/order/verify-payment/` - Verify Razorpay signature

### 4. **Order Management** 📦
- View all past orders
- Detailed order information
- Track order status (Payment → Acceptance → Preparation → Delivery)
- See all order items and amounts

**Routes:**
- `/users/student/orders/` - List all orders
- `/users/student/order/<order_id>/` - Order details

### 5. **Real-Time Delivery Tracking** 📍
- Google Maps integration for live tracking
- Delivery partner location updates
- Vendor, student, and delivery partner markers
- Order timeline with status updates
- Delivery partner contact information (name, phone, vehicle)

**Routes:**
- `/users/student/order/<order_id>/tracking/` - Get tracking data (JSON API)
- `/users/delivery/order/<order_id>/location/` - Delivery partner sends location

## Environment Variables Required

Add these to your `.env` file:

```env
# Razorpay Payment Gateway
RAZORPAY_KEY_ID=your_razorpay_key_id
RAZORPAY_KEY_SECRET=your_razorpay_key_secret

# Google Maps API (for vendor locations and delivery tracking)
GOOGLE_MAPS_API_KEY=your_google_maps_api_key
```

### How to Get These Keys:

**Razorpay Keys:**
1. Go to https://dashboard.razorpay.com
2. Sign up/login with your account
3. Go to Settings → API Keys
4. Copy "Key ID" and "Key Secret"
5. Add them to your `.env` file

**Google Maps API Key:**
1. Go to https://cloud.google.com/maps-platform
2. Create a new project
3. Enable Maps JavaScript API and Geocoding API
4. Create an API key (Application restrictions: HTTP referrers)
5. Add it to your `.env` file

## Database Models Created

### Cart Model
- Stores student's shopping cart
- One-to-one relationship with User
- Methods: `get_total()`, `get_vendor_groups()`

### CartItem Model
- Individual items in cart
- Foreign key to Cart and MenuItem
- Unique constraint on (cart, menu_item)

### Payment Model
- Tracks Razorpay payment transactions
- Stores order_id, payment_id, signature
- Payment status tracking (PENDING, SUCCESS, FAILED)

### DeliveryAssignment Model
- Tracks which delivery partner is assigned
- Stores partner details (name, phone, vehicle)
- Timestamps for pickup and delivery

### OrderTracking Model
- Real-time GPS location updates
- Foreign key to Order and User (delivery_partner)
- Stores latitude, longitude, accuracy, timestamp

### Updated Order Model
- Added fields: `total_amount`, `delivery_address`, `payment_status`
- Supports payment status tracking

## API Endpoints

### Student Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/users/student/vendors/` | List all vendors |
| GET | `/users/student/vendor/<id>/` | View vendor menu |
| POST | `/users/student/cart/add/` | Add item to cart |
| GET | `/users/student/cart/` | View shopping cart |
| POST | `/users/student/cart/remove/<id>/` | Remove from cart |
| POST | `/users/student/cart/update/<id>/` | Update quantity |
| GET | `/users/student/checkout/` | Checkout page |
| POST | `/users/student/order/create/` | Create order & payment |
| POST | `/users/student/order/verify-payment/` | Verify payment |
| GET | `/users/student/orders/` | List all orders |
| GET | `/users/student/order/<id>/` | Order details |
| GET | `/users/student/order/<id>/tracking/` | Tracking data (JSON) |

### Delivery Partner Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/users/delivery/order/<id>/location/` | Send GPS location |

## Frontend Features

### Student Dashboard
- **Notifications Tab**: Recent order updates
- **Recent Orders Tab**: 5 latest orders with statuses
- **Quick Links Tab**: Navigation to key features
- **Order Statistics**: Total orders and notifications count

### Vendor Discovery Page
- Grid layout of all vendors
- Vendor cards with info and quick actions
- Filter by cuisine (can be extended)
- View menu button and map directions

### Shopping Cart
- Multi-vendor organization
- Grouped by vendor with subtotals
- Quantity adjustment with +/- buttons
- Item removal functionality
- Cart total and checkout button

### Checkout Page
- Delivery address input
- Order summary by vendor
- Price breakdown
- Razorpay payment gateway
- Order terms and conditions

### Order Tracking
- Timeline showing order progress
- 4 main stages: Payment → Acceptance → Preparation → Delivery
- Real-time Google Maps with markers:
  - 🟠 Vendor location (orange)
  - 🔵 Student location (blue)
  - 🔴 Delivery partner (red)
- Delivery partner contact details

## Bootstrap Components Used

- Navigation bars and tabs
- Cards and modals
- Alert messages
- Badges and tooltips
- Grid system (12-column)
- Form controls
- Tables
- Buttons and button groups
- Timeline/step indicators

## How Payment Flow Works

1. **Student adds items to cart** → Multiple vendors supported
2. **Student enters delivery address in checkout** → Validates address
3. **Student clicks "Proceed to Razorpay Payment"** → Creates orders
4. **System creates Order records** → One per vendor
5. **System creates Payment record** → Razorpay order ID stored
6. **Razorpay modal opens** → Student completes payment
7. **Payment successful** → Signature verification
8. **Payment verified** → Order status updated to COMPLETED
9. **Notification sent to student** → Order placed successfully
10. **Vendors see incoming tickets** → Can accept/reject orders
11. **Delivery assigned** → Partner tracks order
12. **Real-time updates** → Via location updates

## Real-Time Delivery Tracking

The tracking system works as follows:

1. **Delivery partner receives order assignment**
2. **Partner's app sends GPS location every 5 seconds**
3. **Locations stored in OrderTracking table**
4. **Student's map refreshes every 5 seconds**
5. **Latest location displayed on Google Maps**
6. **Status changes trigger notifications**

## Testing the Features

### Create Test Data:

```python
# In Django shell:
from users.models import *

# Create a vendor
app = StaffApplication.objects.create(
    full_name="Test Vendor",
    email="vendor@test.com",
    phone="9999999999",
    role_applied="VENDOR",
    aadhaar_number="123456789012",
    status="APPROVED",
    outlet_name="Test Restaurant",
    bank_account="1234567890",
    ifsc_code="SBIN0000001"
)

# Create vendor user
vendor_user = User.objects.create_user(
    username="testvendor",
    email="vendor@test.com",
    password="test123",
    phone="9999999999",
    role="VENDOR"
)

# Create vendor profile
vendor_profile = VendorProfile.objects.create(
    user=vendor_user,
    outlet_name="Test Restaurant",
    cuisine_type="Indian",
    operating_hours="11 AM - 11 PM"
)

# Create menu items
MenuItem.objects.create(
    vendor=vendor_profile,
    name="Biryani",
    price=250.00,
    description="Delicious chicken biryani"
)
```

## Common Issues & Solutions

### Razorpay Payment Not Working
- Check `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` in `.env`
- Verify Razorpay account is active
- Test with Razorpay test mode keys first

### Google Maps Not Showing
- Verify `GOOGLE_MAPS_API_KEY` in `.env`
- Check that Maps JavaScript API is enabled
- Verify API key restrictions (if any)

### Cart Not Working
- Check user is authenticated (must be STUDENT role)
- Ensure Cart is created for user
- Check CartItem unique constraint

### Delivery Tracking Not Updating
- Verify delivery partner is  assigned
- Check that location data is being posted
- Check browser console for JavaScript errors
- Verify Google Maps API key is valid

## Future Enhancements

1. **SMS/Email Notifications** - Real-time updates via SMS
2. **Rating & Reviews** - Post-delivery feedback
3. **Favorites** - Save favorite vendors
4. **Wallet** - Prepaid wallet system
5. **Coupons & Discounts** - Promotional codes
6. **Order History Analytics** - Spending trends
7. **Dietary Preferences** - Veg/non-veg filters
8. **In-app Chat** - Direct vendor communication
9. **Estimated Delivery Time** - Dynamic ETA calculation
10. **Multiple Delivery Addresses** - Save addresses

## Files Modified/Created

### Models
- `users/models.py` - Added Cart, CartItem, Payment, DeliveryAssignment, OrderTracking

### Views
- `users/views.py` - Added 15+ new views for student functionality

### Templates
- `templates/student/dashboard.html` - Enhanced dashboard with tabs
- `templates/student/vendors_list.html` - Vendor discovery page
- `templates/student/vendor_detail.html` - Vendor menu page
- `templates/student/cart.html` - Shopping cart
- `templates/student/checkout.html` - Checkout with Razorpay
- `templates/student/orders.html` - Order history
- `templates/student/order_detail.html` - Order tracking with Maps

### Configuration
- `backend/settings.py` - Added Razorpay settings
- `users/urls.py` - Updated URL patterns

### Dependencies
- `requirements.txt` - Added razorpay package

## Support & Troubleshooting

For issues with:
- **Razorpay**: Contact support@razorpay.com
- **Google Maps**: Check https://console.cloud.google.com
- **Django**: Refer to https://docs.djangoproject.com
- **Bootstrap**: Check https://getbootstrap.com

---

**Last Updated:** March 27, 2026
**Version:** 1.0
