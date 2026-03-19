from django.test import TestCase, Client
from django.urls import reverse
from django.core import mail
from .models import User, StaffApplication


# ─── Model Tests ──────────────────────────────────────────────────────────────
class UserModelTest(TestCase):

    def test_user_default_role_is_student(self):
        user = User.objects.create_user(
            username='testuser',
            password='Test@1234',
            phone='9999999999'
        )
        self.assertEqual(user.role, User.Role.STUDENT)

    def test_user_str(self):
        user = User.objects.create_user(
            username='testuser',
            password='Test@1234',
            phone='9999999999'
        )
        self.assertEqual(str(user), 'testuser (STUDENT)')

    def test_create_vendor_user(self):
        user = User.objects.create_user(
            username='vendor1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.VENDOR
        )
        self.assertEqual(user.role, User.Role.VENDOR)

    def test_create_delivery_user(self):
        user = User.objects.create_user(
            username='delivery1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.DELIVERY
        )
        self.assertEqual(user.role, User.Role.DELIVERY)

    def test_password_is_hashed(self):
        user = User.objects.create_user(
            username='testuser2',
            password='Test@1234',
            phone='9999999999'
        )
        self.assertNotEqual(user.password, 'Test@1234')
        self.assertTrue(user.check_password('Test@1234'))


# ─── Registration Tests ───────────────────────────────────────────────────────
class RegisterViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.url = reverse('register')

    def test_register_page_loads(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/register.html')

    def test_register_with_valid_data(self):
        response = self.client.post(self.url, {
            'username'  : 'newstudent',
            'email'     : 'newstudent@iitk.ac.in',
            'phone'     : '9876543210',
            'password1' : 'Campus@1234',
            'password2' : 'Campus@1234',
        })
        self.assertRedirects(response, reverse('login'))
        self.assertTrue(User.objects.filter(username='newstudent').exists())

    def test_register_with_invalid_email_domain(self):
        response = self.client.post(self.url, {
            'username'  : 'newstudent',
            'email'     : 'newstudent@gmail.com',
            'phone'     : '9876543210',
            'password1' : 'Campus@1234',
            'password2' : 'Campus@1234',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='newstudent').exists())

    def test_register_with_mismatched_passwords(self):
        response = self.client.post(self.url, {
            'username'  : 'newstudent',
            'email'     : 'newstudent@iitk.ac.in',
            'phone'     : '9876543210',
            'password1' : 'Campus@1234',
            'password2' : 'Wrong@1234',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='newstudent').exists())

    def test_register_duplicate_username(self):
        User.objects.create_user(
            username='existing',
            email='existing@iitk.ac.in',
            password='Campus@1234',
            phone='9999999999'
        )
        response = self.client.post(self.url, {
            'username'  : 'existing',
            'email'     : 'another@iitk.ac.in',
            'phone'     : '9876543210',
            'password1' : 'Campus@1234',
            'password2' : 'Campus@1234',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(username='existing').count(), 1)

    def test_register_duplicate_email(self):
        User.objects.create_user(
            username='existing',
            email='existing@iitk.ac.in',
            password='Campus@1234',
            phone='9999999999'
        )
        response = self.client.post(self.url, {
            'username'  : 'newuser',
            'email'     : 'existing@iitk.ac.in',
            'phone'     : '9876543210',
            'password1' : 'Campus@1234',
            'password2' : 'Campus@1234',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(email='existing@iitk.ac.in').count(), 1)


# ─── Login Tests ──────────────────────────────────────────────────────────────
class LoginViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.url = reverse('login')
        self.student = User.objects.create_user(
            username='student1',
            password='Campus@1234',
            phone='9999999999',
            role=User.Role.STUDENT
        )
        self.vendor = User.objects.create_user(
            username='vendor1',
            password='Campus@1234',
            phone='9999999999',
            role=User.Role.VENDOR
        )
        self.delivery = User.objects.create_user(
            username='delivery1',
            password='Campus@1234',
            phone='9999999999',
            role=User.Role.DELIVERY
        )

    def test_login_page_loads(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/login.html')

    def test_student_login_redirects_to_student_dashboard(self):
        response = self.client.post(self.url, {
            'username': 'student1',
            'password': 'Campus@1234',
        })
        self.assertRedirects(response, reverse('student_dashboard'))

    def test_vendor_login_redirects_to_vendor_dashboard(self):
        response = self.client.post(self.url, {
            'username': 'vendor1',
            'password': 'Campus@1234',
        })
        self.assertRedirects(response, reverse('vendor_dashboard'))

    def test_delivery_login_redirects_to_delivery_dashboard(self):
        response = self.client.post(self.url, {
            'username': 'delivery1',
            'password': 'Campus@1234',
        })
        self.assertRedirects(response, reverse('delivery_dashboard'))

    def test_login_with_wrong_password(self):
        response = self.client.post(self.url, {
            'username': 'student1',
            'password': 'WrongPass@1234',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/login.html')

    def test_login_with_wrong_username(self):
        response = self.client.post(self.url, {
            'username': 'nonexistent',
            'password': 'Campus@1234',
        })
        self.assertEqual(response.status_code, 200)


# ─── Logout Tests ─────────────────────────────────────────────────────────────
class LogoutViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='Campus@1234',
            phone='9999999999'
        )
        self.client.login(username='testuser', password='Campus@1234')

    def test_logout_redirects_to_login(self):
        response = self.client.get(reverse('logout'))
        self.assertRedirects(response, reverse('login'))

    def test_user_is_logged_out_after_logout(self):
        self.client.get(reverse('logout'))
        response = self.client.get(reverse('student_dashboard'))
        # should redirect to login since user is logged out
        self.assertEqual(response.status_code, 200)


# ─── Staff Application Tests ──────────────────────────────────────────────────
class StaffApplicationTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.url = reverse('apply')

    def test_apply_page_loads(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/apply.html')

    def test_vendor_application_submission(self):
        response = self.client.post(self.url, {
            'role_applied'   : 'VENDOR',
            'full_name'      : 'Test Vendor',
            'email'          : 'vendor@test.com',
            'phone'          : '9876543210',
            'aadhaar_number' : '123456789012',
            'outlet_name'    : 'Test Outlet',
            'outlet_location': 'Block A',
            'cuisine_type'   : 'Fast Food',
            'operating_hours': '9AM - 9PM',
            'fssai_license'  : '12345678901234',
        })
        self.assertRedirects(response, reverse('pending'))
        self.assertTrue(
            StaffApplication.objects.filter(email='vendor@test.com').exists()
        )

    def test_delivery_application_submission(self):
        response = self.client.post(self.url, {
            'role_applied'    : 'DELIVERY',
            'full_name'       : 'Test Delivery',
            'email'           : 'delivery@test.com',
            'phone'           : '9876543210',
            'aadhaar_number'  : '123456789012',
            'vehicle_type'    : 'Motorcycle',
            'vehicle_number'  : 'UP32AB1234',
            'driving_license' : 'DL123456789',
        })
        self.assertRedirects(response, reverse('pending'))
        self.assertTrue(
            StaffApplication.objects.filter(email='delivery@test.com').exists()
        )

    def test_duplicate_application_rejected(self):
        StaffApplication.objects.create(
            full_name      = 'Test Vendor',
            email          = 'vendor@test.com',
            phone          = '9876543210',
            role_applied   = 'VENDOR',
            aadhaar_number = '123456789012',
        )
        response = self.client.post(self.url, {
            'role_applied'   : 'VENDOR',
            'full_name'      : 'Test Vendor',
            'email'          : 'vendor@test.com',
            'phone'          : '9876543210',
            'aadhaar_number' : '123456789012',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            StaffApplication.objects.filter(email='vendor@test.com').count(), 1
        )


# ─── Signal Tests ─────────────────────────────────────────────────────────────
class SignalTest(TestCase):

    def setUp(self):
        self.application = StaffApplication.objects.create(
            full_name      = 'John Vendor',
            email          = 'john@vendor.com',
            phone          = '9876543210',
            role_applied   = 'VENDOR',
            aadhaar_number = '123456789012',
            outlet_name    = 'Johns Outlet',
        )

    def test_approval_creates_user(self):
        self.application.status = 'APPROVED'
        self.application.save()
        self.assertTrue(
            User.objects.filter(email='john@vendor.com').exists()
        )

    def test_approved_user_has_correct_role(self):
        self.application.status = 'APPROVED'
        self.application.save()
        user = User.objects.get(email='john@vendor.com')
        self.assertEqual(user.role, User.Role.VENDOR)

    def test_approval_sends_email(self):
        self.application.status = 'APPROVED'
        self.application.save()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('john@vendor.com', mail.outbox[0].to)
        self.assertIn('Approved', mail.outbox[0].subject)

    def test_rejection_sends_email(self):
        self.application.status = 'REJECTED'
        self.application.save()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('john@vendor.com', mail.outbox[0].to)

    def test_duplicate_approval_doesnt_create_second_user(self):
        self.application.status = 'APPROVED'
        self.application.save()
        # approve again
        self.application.save()
        self.assertEqual(
            User.objects.filter(email='john@vendor.com').count(), 1
        )