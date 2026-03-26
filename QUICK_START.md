# Quick Start Guide - Student Dashboard

## 🚀 Getting Started (5 Minutes)

### 1. Update Environment Variables
Add to your `.env` file:
```env
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxx
RAZORPAY_KEY_SECRET=xxxxxxxxxxxxxxxxx
GOOGLE_MAPS_API_KEY=AIzaSyxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 2. Install Dependencies
```bash
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Run Migrations
```bash
python manage.py migrate
```

### 4. Start Development Server
```bash
python manage.py runserver
```

### 5. Access the System
- **Student Dashboard**: http://localhost:8000/users/student/dashboard/
- **Vendor Discovery**: http://localhost:8000/users/student/vendors/
- **Shopping Cart**: http://localhost:8000/users/student/cart/

---

## 📋 Step-by-Step Features

### Feature 1: Vendor Discovery 🏪
1. Login as a student
2. Click "Discover Vendors" from dashboard
3. View all vendors with cuisine type and location
4. Click "View Menu" to see items

✅ **Result**: See all vendors with their menus

### Feature 2: Shopping Cart 🛒
1. Click "Add to Cart" on menu items
2. Adjust quantity with +/- buttons
3. View cart shows items grouped by vendor
4. See subtotal per vendor and total amount

✅ **Result**: Multi-vendor cart with proper grouping

### Feature 3: Checkout 💳
1. Click "Proceed to Checkout" from cart
2. Enter your delivery address
3. Review order summary
4. Click "Proceed to Razorpay Payment"

✅ **Result**: Payment order created

### Feature 4: Payment Processing 💰
1. Razorpay modal opens automatically
2. Complete payment (use test card: 4111 1111 1111 1111)
3. Payment verified automatically
4. Redirected to orders page

✅ **Result**: Order placed and payment confirmed

### Feature 5: Order Tracking 📍
1. Go to "My Orders"
2. Click "View Details & Track Delivery"
3. See order timeline with status
4. View Google Map with delivery location (when active)
5. See delivery partner details

✅ **Result**: Real-time order tracking

---

## 🧪 Test Credentials

### Student Account
```
Username: student1
Email: student1@iitk.ac.in
Password: test123456
```

### Vendor Account (For Testing Delivery)
```
Username: vendor1
Email: vendor1@iitk.ac.in
Password: test123456
```

### Razorpay Test Mode
- **Test Card**: 4111 1111 1111 1111
- **Expiry**: Any future date
- **CVV**: Any 3 digits
- **OTP**: 000000

---

## 🗺️ Google Maps Setup

### Get Your API Key:
1. Go to https://console.cloud.google.com
2. Create new project
3. Enable: Maps JavaScript API, Geocoding API
4. Create API key (HTTP referrers)
5. Add to `.env` as `GOOGLE_MAPS_API_KEY`

### Test Vendor Location:
- Set vendor address in `/users/vendor/location/` 
- System auto-geocodes to lat/lng
- Map displays vendor location

---

## 💳 Razorpay Setup

### Get Your Keys:
1. Go to https://dashboard.razorpay.com
2. Sign in
3. Settings → API Keys
4. Copy Key ID and Key Secret
5. Add to `.env`

### Test Payment:
- Amount will be calculated automatically
- Razorpay modal opens on click
- Payment and signature verification happens
- Order status updates automatically

---

## 📊 Key Database Tables

### Cart (Shopping Cart)
- Stores current student's cart
- Recalculates totals on item addition

### CartItem (Cart Items)
- Individual items with quantities
- Unique per (cart, menu_item)

### Order (Orders)
- One per vendor in checkout
- Tracks payment status

### Payment (Payments)
- Razorpay transaction details
- One per checkout session

### OrderTracking (Location Updates)
- Real-time delivery partner locations
- Updated every 5 seconds

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| Cart is empty | Refresh page, check if user is authenticated |
| Payment doesn't work | Check RAZORPAY_KEY_ID in .env |
| Map not showing | Verify GOOGLE_MAPS_API_KEY is valid |
| Migrations error | Run `python manage.py migrate` again |
| Permission denied | Ensure user role is STUDENT |

---

## 📱 Responsive Design

The system works perfectly on:
- ✅ Mobile phones (320px+)
- ✅ Tablets (768px+)
- ✅ Desktops (1200px+)

Try opening on your phone to see responsive layout!

---

## 🔐 Security Features

- ✅ CSRF token validation on all POST requests
- ✅ User authentication checks on all views
- ✅ Role-based access control (STUDENT, VENDOR, DELIVERY)
- ✅ Razorpay signature verification
- ✅ Order ownership validation

---

## 📞 Support

For detailed setup information, see `STUDENT_DASHBOARD_SETUP.md`

**Razorpay Support**: https://razorpay.com/support
**Google Maps Support**: https://cloud.google.com/maps-platform
**Django Docs**: https://docs.djangoproject.com

---

**Happy Ordering! 🍽️**
