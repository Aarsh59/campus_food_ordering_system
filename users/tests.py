from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.core import mail
from django.core.exceptions import ValidationError
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from .models import (
    User, StaffApplication, VendorProfile, MenuItem, Order, OrderItem,
    Notification, Cart, CartItem, Payment, DeliveryAssignment,
    DeliveryBroadcast, DeliveryBroadcastResponse, OrderTracking, ContactOTP
)
from .otp_utils import issue_otp
from .admin import StaffApplicationAdmin


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

    def test_model_validation_rejects_emoji_username(self):
        user = User(username='test🍕user', phone='9999999999')
        with self.assertRaises(ValidationError):
            user.full_clean()


# ─── Registration Tests ───────────────────────────────────────────────────────
class RegisterViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.url = reverse('register')

    def _otp_fields(self, email='newstudent@iitk.ac.in', phone='9876543210'):
        _, email_otp = issue_otp(ContactOTP.Purpose.STUDENT_REGISTER, ContactOTP.Channel.EMAIL, email)
        return {
            'email_otp': email_otp,
        }

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
            **self._otp_fields(),
        })
        self.assertRedirects(response, reverse('login'))
        self.assertTrue(User.objects.filter(username='newstudent').exists())

    def test_register_allows_ascii_special_username_characters(self):
        response = self.client.post(self.url, {
            'username'  : 'new.student+test@iitk_1',
            'email'     : 'specialuser@iitk.ac.in',
            'phone'     : '9876543210',
            'password1' : 'Campus@1234',
            'password2' : 'Campus@1234',
            **self._otp_fields(email='specialuser@iitk.ac.in'),
        })
        self.assertRedirects(response, reverse('login'))
        self.assertTrue(User.objects.filter(username='new.student+test@iitk_1').exists())

    def test_register_rejects_emoji_username(self):
        response = self.client.post(self.url, {
            'username'  : 'newstudent🍕',
            'email'     : 'emojiuser@iitk.ac.in',
            'phone'     : '9876543210',
            'password1' : 'Campus@1234',
            'password2' : 'Campus@1234',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email='emojiuser@iitk.ac.in').exists())

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

    def test_register_duplicate_username_is_case_insensitive(self):
        User.objects.create_user(
            username='Existing',
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
        self.assertEqual(User.objects.filter(username__iexact='existing').count(), 1)

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

    def test_send_registration_email_otp_rejects_non_iitk_email(self):
        response = self.client.post(reverse('send_registration_otp'), {
            'purpose': ContactOTP.Purpose.STUDENT_REGISTER,
            'channel': ContactOTP.Channel.EMAIL,
            'email': 'student@gmail.com',
            'phone': '9876543210',
        })

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])

    def test_send_registration_phone_otp_is_disabled(self):
        response = self.client.post(reverse('send_registration_otp'), {
            'purpose': ContactOTP.Purpose.STUDENT_REGISTER,
            'channel': ContactOTP.Channel.PHONE,
            'email': 'student@iitk.ac.in',
            'phone': '9876543210',
        })

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])

    def test_send_staff_application_email_otp_allows_external_email(self):
        response = self.client.post(reverse('send_registration_otp'), {
            'purpose': ContactOTP.Purpose.STAFF_APPLICATION,
            'channel': ContactOTP.Channel.EMAIL,
            'email': 'vendor@gmail.com',
            'phone': '9876543210',
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])

    @override_settings(OTP_RESEND_COOLDOWN_SECONDS=60)
    def test_send_registration_email_otp_enforces_resend_cooldown(self):
        payload = {
            'purpose': ContactOTP.Purpose.STUDENT_REGISTER,
            'channel': ContactOTP.Channel.EMAIL,
            'email': 'student@iitk.ac.in',
            'phone': '9876543210',
        }

        first_response = self.client.post(reverse('send_registration_otp'), payload)
        second_response = self.client.post(reverse('send_registration_otp'), payload)

        self.assertEqual(first_response.status_code, 200)
        self.assertTrue(first_response.json()['success'])
        self.assertEqual(second_response.status_code, 429)
        self.assertFalse(second_response.json()['success'])
        self.assertGreaterEqual(second_response.json()['retry_after_seconds'], 58)
        self.assertLessEqual(second_response.json()['retry_after_seconds'], 60)
        self.assertEqual(ContactOTP.objects.filter(
            purpose=ContactOTP.Purpose.STUDENT_REGISTER,
            channel=ContactOTP.Channel.EMAIL,
            target='student@iitk.ac.in',
            verified_at__isnull=True,
        ).count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(OTP_RESEND_COOLDOWN_SECONDS=60)
    def test_send_registration_email_otp_allows_resend_after_cooldown(self):
        payload = {
            'purpose': ContactOTP.Purpose.STUDENT_REGISTER,
            'channel': ContactOTP.Channel.EMAIL,
            'email': 'student2@iitk.ac.in',
            'phone': '9876543210',
        }

        first_response = self.client.post(reverse('send_registration_otp'), payload)
        otp = ContactOTP.objects.get(
            purpose=ContactOTP.Purpose.STUDENT_REGISTER,
            channel=ContactOTP.Channel.EMAIL,
            target='student2@iitk.ac.in',
            verified_at__isnull=True,
        )
        otp.created_at = timezone.now() - timedelta(seconds=61)
        otp.save(update_fields=['created_at'])

        second_response = self.client.post(reverse('send_registration_otp'), payload)

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertTrue(second_response.json()['success'])
        self.assertEqual(ContactOTP.objects.filter(
            purpose=ContactOTP.Purpose.STUDENT_REGISTER,
            channel=ContactOTP.Channel.EMAIL,
            target='student2@iitk.ac.in',
            verified_at__isnull=True,
        ).count(), 1)
        self.assertEqual(len(mail.outbox), 2)


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

    def test_authenticated_user_visiting_login_redirects_to_dashboard(self):
        self.client.login(username='student1', password='Campus@1234')

        response = self.client.get(self.url)

        self.assertRedirects(response, reverse('student_dashboard'))

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

    def test_logout_response_disables_browser_caching(self):
        response = self.client.get(reverse('logout'))

        self.assertIn('no-store', response['Cache-Control'])
        self.assertIn('no-cache', response['Cache-Control'])

    def test_user_is_logged_out_after_logout(self):
        self.client.get(reverse('logout'))
        response = self.client.get(reverse('student_dashboard'))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('student_dashboard')}")


class HomeViewTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.home_url = reverse('home')
        self.student = User.objects.create_user(
            username='student-home',
            password='Campus@1234',
            phone='9999999999',
            role=User.Role.STUDENT
        )

    def test_home_redirects_anonymous_user_to_login(self):
        response = self.client.get(self.home_url)

        self.assertRedirects(response, reverse('login'))

    def test_home_redirects_authenticated_user_to_dashboard(self):
        self.client.login(username='student-home', password='Campus@1234')

        response = self.client.get(self.home_url)

        self.assertRedirects(response, reverse('student_dashboard'))


class AuthenticatedPageCacheHeadersTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.student = User.objects.create_user(
            username='cache-student',
            password='Campus@1234',
            phone='9999999999',
            role=User.Role.STUDENT
        )
        self.client.login(username='cache-student', password='Campus@1234')

    def test_student_dashboard_disables_browser_caching(self):
        response = self.client.get(reverse('student_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertIn('no-cache', response['Cache-Control'])


class SessionInactivityTimeoutTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='idle-student',
            password='Campus@1234',
            phone='9999999999',
            role=User.Role.STUDENT
        )

    @override_settings(SESSION_COOKIE_AGE=5, SESSION_INACTIVITY_TIMEOUT=5)
    def test_session_expires_after_inactivity_timeout(self):
        self.client.login(username='idle-student', password='Campus@1234')
        session = self.client.session
        session['_last_activity_ts'] = int((timezone.now() - timedelta(seconds=10)).timestamp())
        session.save()

        response = self.client.get(reverse('student_dashboard'), follow=True)

        self.assertRedirects(response, reverse('login'))
        messages_list = list(response.context['messages'])
        self.assertTrue(
            any('logged out due to inactivity' in str(message).lower() for message in messages_list)
        )


class PasswordManagementTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='password-user',
            email='password-user@iitk.ac.in',
            password='Campus@1234',
            phone='9999999999',
            role=User.Role.STUDENT,
        )

    def test_forgot_password_sends_reset_email(self):
        response = self.client.post(reverse('password_reset'), {
            'email': 'password-user@iitk.ac.in',
        })

        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Campus Food password reset', mail.outbox[0].subject)
        self.assertIn('/password-reset-confirm/', mail.outbox[0].body)

    def test_password_reset_confirm_updates_password(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        confirm_url = reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})

        get_response = self.client.get(confirm_url)
        self.assertEqual(get_response.status_code, 302)
        self.assertIn('/password-reset-confirm/', get_response.url)
        self.assertTrue(get_response.url.endswith('/set-password/'))

        post_response = self.client.post(get_response.url, {
            'new_password1': 'Updated@1234',
            'new_password2': 'Updated@1234',
        })

        self.assertRedirects(post_response, reverse('password_reset_complete'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Updated@1234'))

    def test_password_reset_confirm_invalid_token_shows_message(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        response = self.client.get(
            reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': 'invalid-token'})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Reset Link Invalid')

    def test_change_password_shows_error_when_current_password_is_wrong(self):
        self.client.login(username='password-user', password='Campus@1234')

        response = self.client.post(reverse('change_password'), {
            'old_password': 'Wrong@1234',
            'new_password1': 'Updated@1234',
            'new_password2': 'Updated@1234',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Your old password was entered incorrectly')
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Campus@1234'))


# ─── Staff Application Tests ──────────────────────────────────────────────────
class StaffApplicationTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.url = reverse('apply')

    def _otp_fields(self, email, phone='9876543210'):
        _, email_otp = issue_otp(ContactOTP.Purpose.STAFF_APPLICATION, ContactOTP.Channel.EMAIL, email)
        return {
            'email_otp': email_otp,
        }

    def _vendor_application_payload(self, **overrides):
        otp_fields = {}
        if 'email_otp' not in overrides:
            otp_fields = self._otp_fields(email=overrides.get('email', 'vendor@gmail.com'))

        payload = {
            'role_applied': 'VENDOR',
            'full_name': 'Test Vendor',
            'email': 'vendor@gmail.com',
            'phone': '9876543210',
            'aadhaar_number': '123456789012',
            'outlet_name': 'Test Outlet',
            'outlet_location': 'MAIN_CANTEEN',
            'cuisine_type': 'FAST_FOOD',
            'operating_start': '09:00',
            'operating_end': '21:00',
            'fssai_license': '12345678901234',
            'bank_account': '123456789012',
            'ifsc_code': 'SBIN0001234',
            **otp_fields,
        }
        payload.update(overrides)
        return payload

    def test_apply_page_loads(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/apply.html')

    def test_vendor_application_submission(self):
        response = self.client.post(self.url, self._vendor_application_payload())
        self.assertRedirects(response, reverse('pending'))
        self.assertTrue(
            StaffApplication.objects.filter(email='vendor@gmail.com').exists()
        )

    def test_vendor_application_notifies_admin_users(self):
        admin_user = User.objects.create_user(
            username='admin-reviewer',
            email='admin@example.com',
            password='Campus@1234',
            phone='9999999999',
            is_staff=True,
            is_superuser=True,
        )

        self.client.post(self.url, self._vendor_application_payload(
            email='vendor.notify@gmail.com',
            **self._otp_fields(email='vendor.notify@gmail.com'),
        ))

        application = StaffApplication.objects.get(email='vendor.notify@gmail.com')
        notification = Notification.objects.get(recipient=admin_user, application=application)
        self.assertEqual(notification.notification_type, Notification.NotificationType.STAFF_APPLICATION)
        self.assertIn('pending review', notification.message.lower())

    def test_vendor_application_emails_admin_users(self):
        User.objects.create_user(
            username='admin-mail',
            email='admin-mail@example.com',
            password='Campus@1234',
            phone='9999999999',
            is_staff=True,
            is_superuser=True,
        )

        response = self.client.post(self.url, self._vendor_application_payload(
            full_name='Mail Vendor',
            email='vendor.mail@gmail.com',
            outlet_name='Mail Outlet',
            outlet_location='SHOPPING_COMPLEX',
            cuisine_type='SNACKS',
            operating_start='10:00',
            operating_end='20:00',
            **self._otp_fields(email='vendor.mail@gmail.com'),
        ))

        self.assertRedirects(response, reverse('pending'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('admin-mail@example.com', mail.outbox[0].to)
        self.assertIn('pending review', mail.outbox[0].subject.lower())
        self.assertIn('Mail Vendor', mail.outbox[0].body)

    def test_delivery_application_submission(self):
        response = self.client.post(self.url, {
            'role_applied'    : 'DELIVERY',
            'full_name'       : 'Test Delivery',
            'email'           : 'delivery@gmail.com',
            'phone'           : '9876543210',
            'aadhaar_number'  : '123456789012',
            'vehicle_type'    : 'Motorcycle',
            'vehicle_number'  : 'UP32AB1234',
            'driving_license' : 'DL123456789',
            **self._otp_fields(email='delivery@gmail.com'),
        })
        self.assertRedirects(response, reverse('pending'))
        self.assertTrue(
            StaffApplication.objects.filter(email='delivery@gmail.com').exists()
        )

    def test_duplicate_application_rejected(self):
        StaffApplication.objects.create(
            full_name      = 'Test Vendor',
            email          = 'vendor@iitk.ac.in',
            phone          = '9876543210',
            role_applied   = 'VENDOR',
            aadhaar_number = '123456789012',
            outlet_name    = 'Test Outlet',
            outlet_location = 'MAIN_CANTEEN',
            cuisine_type   = 'FAST_FOOD',
            operating_hours = '09:00 - 21:00',
            fssai_license  = '12345678901234',
            bank_account   = '123456789012',
            ifsc_code      = 'SBIN0001234',
        )
        response = self.client.post(self.url, self._vendor_application_payload(
            email='vendor@iitk.ac.in',
            **self._otp_fields(email='vendor@iitk.ac.in'),
        ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            StaffApplication.objects.filter(email='vendor@iitk.ac.in').count(), 1
        )

    def test_vendor_application_rejects_invalid_dropdown_value(self):
        response = self.client.post(self.url, self._vendor_application_payload(
            outlet_location='Block A',
        ))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Select a valid outlet location from the list.')
        self.assertFalse(StaffApplication.objects.filter(email='vendor@gmail.com').exists())

    def test_vendor_application_rejects_invalid_operating_hours(self):
        response = self.client.post(self.url, self._vendor_application_payload(
            operating_start='21:00',
            operating_end='09:00',
        ))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Operating hours end time must be later than the start time.')
        self.assertFalse(StaffApplication.objects.filter(email='vendor@gmail.com').exists())

    def test_vendor_application_rejects_invalid_fssai_and_ifsc(self):
        response = self.client.post(self.url, self._vendor_application_payload(
            fssai_license='12345',
            ifsc_code='12345678901',
        ))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'FSSAI license number must be exactly 14 digits.')
        self.assertContains(response, 'IFSC code must follow the standard 11-character bank format.')
        self.assertFalse(StaffApplication.objects.filter(email='vendor@gmail.com').exists())


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
            outlet_location = 'MAIN_CANTEEN',
            cuisine_type   = 'FAST_FOOD',
            operating_hours = '09:00 - 21:00',
            fssai_license  = '12345678901234',
            bank_account   = '123456789012',
            ifsc_code      = 'SBIN0001234',
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

    def test_reapproval_resends_email_for_existing_user(self):
        existing_user = User.objects.create_user(
            username='john',
            email='john@vendor.com',
            password='Test@1234',
            phone='9876543210',
            role=User.Role.VENDOR
        )
        mail.outbox = []

        self.application.status = 'APPROVED'
        self.application.save()

        self.assertEqual(User.objects.filter(email='john@vendor.com').count(), 1)
        self.assertEqual(existing_user.username, User.objects.get(email='john@vendor.com').username)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('john@vendor.com', mail.outbox[0].to)
        self.assertIn(existing_user.username, mail.outbox[0].body)

    def test_approval_sanitizes_generated_username(self):
        application = StaffApplication.objects.create(
            full_name      = 'Emoji Vendor',
            email          = 'food🍕vendor@vendor.com',
            phone          = '9876543210',
            role_applied   = 'VENDOR',
            aadhaar_number = '123456789012',
            outlet_name    = 'Emoji Outlet',
            outlet_location = 'SHOPPING_COMPLEX',
            cuisine_type   = 'SNACKS',
            operating_hours = '10:00 - 20:00',
            fssai_license  = '12345678901234',
            bank_account   = '123456789012',
            ifsc_code      = 'SBIN0001234',
        )

        application.status = 'APPROVED'
        application.save()

        self.assertTrue(User.objects.filter(username='foodvendor').exists())

    def test_approval_generated_username_clash_is_case_insensitive(self):
        User.objects.create_user(
            username='John',
            email='existing@vendor.com',
            password='Test@1234',
            phone='9876543210',
            role=User.Role.VENDOR
        )

        self.application.status = 'APPROVED'
        self.application.save()

        self.assertTrue(User.objects.filter(username='john1').exists())


class StaffApplicationAdminTest(TestCase):

    def setUp(self):
        self.site = AdminSite()
        self.admin = StaffApplicationAdmin(StaffApplication, self.site)
        self.application = StaffApplication.objects.create(
            full_name='Pending Vendor',
            email='pending@vendor.com',
            phone='9876543210',
            role_applied='VENDOR',
            aadhaar_number='123456789012',
            outlet_name='Pending Outlet',
            outlet_location='MAIN_CANTEEN',
            cuisine_type='FAST_FOOD',
            operating_hours='09:00 - 21:00',
            fssai_license='12345678901234',
            bank_account='123456789012',
            ifsc_code='SBIN0001234',
        )

    def test_save_model_sets_reviewed_at_when_status_changes_from_pending(self):
        class DummyForm:
            changed_data = ['status']

        self.application.status = StaffApplication.Status.APPROVED
        self.admin.save_model(request=None, obj=self.application, form=DummyForm(), change=True)

        self.application.refresh_from_db()
        self.assertIsNotNone(self.application.reviewed_at)


# ─── Model Tests for Student/Vendor/Delivery ───────────────────────────────────
class VendorProfileModelTest(TestCase):

    def setUp(self):
        self.vendor_user = User.objects.create_user(
            username='vendor1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.VENDOR
        )

    def test_vendor_profile_creation(self):
        profile = VendorProfile.objects.create(
            user=self.vendor_user,
            outlet_name='Test Outlet',
            google_maps_location='https://maps.google.com/?q=26.5124,80.2394'
        )
        self.assertEqual(str(profile), 'Test Outlet')

    def test_vendor_profile_str_without_outlet_name(self):
        profile = VendorProfile.objects.create(user=self.vendor_user)
        self.assertEqual(str(profile), 'vendor1')


class MenuItemModelTest(TestCase):

    def setUp(self):
        self.vendor_user = User.objects.create_user(
            username='vendor1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.VENDOR
        )
        self.vendor_profile = VendorProfile.objects.create(
            user=self.vendor_user,
            outlet_name='Test Outlet'
        )

    def test_menu_item_creation(self):
        item = MenuItem.objects.create(
            vendor=self.vendor_profile,
            name='Test Item',
            price=Decimal('100.00'),
            description='Test description'
        )
        self.assertEqual(str(item), 'Test Outlet - Test Item')
        self.assertTrue(item.is_active)


class OrderModelTest(TestCase):

    def setUp(self):
        self.student = User.objects.create_user(
            username='student1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.STUDENT
        )
        self.vendor_user = User.objects.create_user(
            username='vendor1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.VENDOR
        )
        self.vendor_profile = VendorProfile.objects.create(
            user=self.vendor_user,
            outlet_name='Test Outlet'
        )

    def test_order_creation_generates_order_code(self):
        order = Order.objects.create(
            student=self.student,
            vendor=self.vendor_profile,
            total_amount=Decimal('200.00')
        )
        self.assertTrue(order.order_code.startswith('ORD-'))
        self.assertEqual(str(order), f"{order.order_code} (student1 -> Test Outlet)")

    def test_order_default_statuses(self):
        order = Order.objects.create(
            student=self.student,
            vendor=self.vendor_profile,
            total_amount=Decimal('200.00')
        )
        self.assertEqual(order.vendor_decision, Order.VendorDecision.PENDING)
        self.assertEqual(order.vendor_status, Order.VendorStatus.NOT_STARTED)
        self.assertEqual(order.delivery_status, Order.DeliveryStatus.NOT_STARTED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)


class OrderItemModelTest(TestCase):

    def setUp(self):
        self.student = User.objects.create_user(
            username='student1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.STUDENT
        )
        self.vendor_user = User.objects.create_user(
            username='vendor1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.VENDOR
        )
        self.vendor_profile = VendorProfile.objects.create(
            user=self.vendor_user,
            outlet_name='Test Outlet'
        )
        self.order = Order.objects.create(
            student=self.student,
            vendor=self.vendor_profile,
            total_amount=Decimal('200.00')
        )

    def test_order_item_line_total(self):
        item = OrderItem.objects.create(
            order=self.order,
            item_name='Test Item',
            unit_price=Decimal('50.00'),
            quantity=2
        )
        self.assertEqual(item.line_total(), Decimal('100.00'))
        self.assertEqual(str(item), 'Test Item x2')


class CartModelTest(TestCase):

    def setUp(self):
        self.student = User.objects.create_user(
            username='student1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.STUDENT
        )
        self.vendor_user = User.objects.create_user(
            username='vendor1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.VENDOR
        )
        self.vendor_profile = VendorProfile.objects.create(
            user=self.vendor_user,
            outlet_name='Test Outlet'
        )
        self.menu_item = MenuItem.objects.create(
            vendor=self.vendor_profile,
            name='Test Item',
            price=Decimal('50.00')
        )

    def test_cart_creation(self):
        cart = Cart.objects.create(student=self.student)
        self.assertEqual(cart.get_total(), 0)
        self.assertEqual(str(cart), "Cart for student1")

    def test_cart_get_total(self):
        cart = Cart.objects.create(student=self.student)
        CartItem.objects.create(cart=cart, menu_item=self.menu_item, quantity=2)
        self.assertEqual(cart.get_total(), Decimal('100.00'))


class CartItemModelTest(TestCase):

    def setUp(self):
        self.student = User.objects.create_user(
            username='student1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.STUDENT
        )
        self.vendor_user = User.objects.create_user(
            username='vendor1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.VENDOR
        )
        self.vendor_profile = VendorProfile.objects.create(
            user=self.vendor_user,
            outlet_name='Test Outlet'
        )
        self.menu_item = MenuItem.objects.create(
            vendor=self.vendor_profile,
            name='Test Item',
            price=Decimal('50.00')
        )
        self.cart = Cart.objects.create(student=self.student)

    def test_cart_item_subtotal(self):
        item = CartItem.objects.create(cart=self.cart, menu_item=self.menu_item, quantity=3)
        self.assertEqual(item.get_subtotal(), Decimal('150.00'))
        self.assertEqual(str(item), 'Test Item x3 in student1\'s cart')

    def test_unique_cart_menu_item_constraint(self):
        CartItem.objects.create(cart=self.cart, menu_item=self.menu_item, quantity=1)
        with self.assertRaises(Exception):  # IntegrityError
            CartItem.objects.create(cart=self.cart, menu_item=self.menu_item, quantity=2)


# ─── Student Module Tests ─────────────────────────────────────────────────────
class StudentDashboardTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.student = User.objects.create_user(
            username='student1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.STUDENT
        )
        self.client.login(username='student1', password='Test@1234')

    def test_student_dashboard_access(self):
        response = self.client.get(reverse('student_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'student/dashboard.html')

    def test_unauthorized_access_to_student_dashboard(self):
        vendor = User.objects.create_user(
            username='vendor1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.VENDOR
        )
        self.client.login(username='vendor1', password='Test@1234')
        response = self.client.get(reverse('student_dashboard'))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_dashboard_order_count_excludes_failed_orders(self):
        vendor_user = User.objects.create_user(
            username='vendor1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.VENDOR
        )
        vendor_profile = VendorProfile.objects.create(user=vendor_user, outlet_name='Test Vendor')
        Order.objects.create(
            student=self.student,
            vendor=vendor_profile,
            payment_status=Order.PaymentStatus.COMPLETED,
        )
        Order.objects.create(
            student=self.student,
            vendor=vendor_profile,
            payment_status=Order.PaymentStatus.FAILED,
            vendor_status=Order.VendorStatus.CANCELLED,
        )

        response = self.client.get(reverse('student_dashboard'))

        self.assertEqual(response.context['orders_placed_count'], 1)

    @override_settings(GOOGLE_MAPS_API_KEY='test-maps-key')
    def test_student_dashboard_includes_vendor_map_data(self):
        vendor_user = User.objects.create_user(
            username='vendor-map',
            password='Test@1234',
            phone='9999999998',
            role=User.Role.VENDOR
        )
        VendorProfile.objects.create(
            user=vendor_user,
            outlet_name='Map Vendor',
            google_maps_location='https://www.google.com/maps/search/?api=1&query=26.5124,80.2329',
            google_maps_address='IIT Kanpur, Map Vendor'
        )

        response = self.client.get(reverse('student_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'studentDashboardMap')
        self.assertContains(response, 'Map Vendor')
        self.assertEqual(response.context['google_maps_api_key'], 'test-maps-key')


class StudentVendorsListTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.student = User.objects.create_user(
            username='student1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.STUDENT
        )
        self.client.login(username='student1', password='Test@1234')

        # Create vendors
        self.vendor1 = User.objects.create_user(
            username='vendor1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.VENDOR
        )
        self.vendor_profile1 = VendorProfile.objects.create(
            user=self.vendor1,
            outlet_name='Vendor 1',
            cuisine_type='Fast Food'
        )

        self.vendor2 = User.objects.create_user(
            username='vendor2',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.VENDOR
        )
        self.vendor_profile2 = VendorProfile.objects.create(
            user=self.vendor2,
            outlet_name='Vendor 2',
            cuisine_type='Italian'
        )

    def test_vendors_list_display(self):
        response = self.client.get(reverse('student_vendors_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'student/vendors_list.html')
        self.assertContains(response, 'Vendor 1')
        self.assertContains(response, 'Vendor 2')

    def test_vendors_list_filter_by_cuisine(self):
        response = self.client.get(reverse('student_vendors_list') + '?cuisine=Fast+Food')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Vendor 1')
        self.assertNotContains(response, 'Vendor 2')


class StudentVendorDetailTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.student = User.objects.create_user(
            username='student1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.STUDENT
        )
        self.client.login(username='student1', password='Test@1234')

        self.vendor = User.objects.create_user(
            username='vendor1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.VENDOR
        )
        self.vendor_profile = VendorProfile.objects.create(
            user=self.vendor,
            outlet_name='Test Vendor',
            cuisine_type='Fast Food'
        )
        self.menu_item = MenuItem.objects.create(
            vendor=self.vendor_profile,
            name='Burger',
            price=Decimal('100.00'),
            description='Delicious burger'
        )

    def test_vendor_detail_display(self):
        response = self.client.get(reverse('student_vendor_detail', args=[self.vendor_profile.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'student/vendor_detail.html')
        self.assertContains(response, 'Test Vendor')
        self.assertContains(response, 'Burger')

    def test_vendor_detail_quantity_starts_at_zero(self):
        response = self.client.get(reverse('student_vendor_detail', args=[self.vendor_profile.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'id="qty-{self.menu_item.id}" value="0"')

    def test_vendor_detail_shows_existing_cart_quantity(self):
        cart = Cart.objects.create(student=self.student)
        CartItem.objects.create(cart=cart, menu_item=self.menu_item, quantity=3)

        response = self.client.get(reverse('student_vendor_detail', args=[self.vendor_profile.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'id="qty-{self.menu_item.id}" value="3"')


class StudentCartTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.student = User.objects.create_user(
            username='student1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.STUDENT
        )
        self.client.login(username='student1', password='Test@1234')

        self.vendor = User.objects.create_user(
            username='vendor1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.VENDOR
        )
        self.vendor_profile = VendorProfile.objects.create(
            user=self.vendor,
            outlet_name='Test Vendor'
        )
        self.menu_item = MenuItem.objects.create(
            vendor=self.vendor_profile,
            name='Burger',
            price=Decimal('100.00'),
            stock=5,
        )

    def test_add_to_cart(self):
        response = self.client.post(reverse('student_add_to_cart', args=[self.menu_item.id]), {
            'quantity': 2
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        cart = Cart.objects.get(student=self.student)
        cart_item = CartItem.objects.get(cart=cart, menu_item=self.menu_item)
        self.assertEqual(cart_item.quantity, 2)

    def test_add_to_cart_rejects_quantity_above_stock(self):
        response = self.client.post(reverse('student_add_to_cart', args=[self.menu_item.id]), {
            'quantity': 6
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'Only 5 of Burger available right now.')
        self.assertFalse(CartItem.objects.filter(menu_item=self.menu_item, cart__student=self.student).exists())

    def test_view_cart(self):
        cart = Cart.objects.create(student=self.student)
        CartItem.objects.create(cart=cart, menu_item=self.menu_item, quantity=1)
        response = self.client.get(reverse('student_view_cart'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'student/cart.html')
        self.assertContains(response, 'Burger')

    def test_remove_from_cart(self):
        cart = Cart.objects.create(student=self.student)
        cart_item = CartItem.objects.create(cart=cart, menu_item=self.menu_item, quantity=1)
        response = self.client.post(reverse('student_remove_from_cart', args=[cart_item.id]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertFalse(CartItem.objects.filter(id=cart_item.id).exists())

    def test_update_cart_item(self):
        cart = Cart.objects.create(student=self.student)
        cart_item = CartItem.objects.create(cart=cart, menu_item=self.menu_item, quantity=1)
        response = self.client.post(reverse('student_update_cart_item', args=[cart_item.id]), {
            'quantity': 3
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        cart_item.refresh_from_db()
        self.assertEqual(cart_item.quantity, 3)

    def test_update_cart_item_rejects_quantity_above_stock(self):
        cart = Cart.objects.create(student=self.student)
        cart_item = CartItem.objects.create(cart=cart, menu_item=self.menu_item, quantity=1)

        response = self.client.post(reverse('student_update_cart_item', args=[cart_item.id]), {
            'quantity': 6
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'Only 5 of Burger available right now.')
        cart_item.refresh_from_db()
        self.assertEqual(cart_item.quantity, 1)

    def test_update_menu_cart_item_zero_removes_item(self):
        cart = Cart.objects.create(student=self.student)
        CartItem.objects.create(cart=cart, menu_item=self.menu_item, quantity=1)

        response = self.client.post(reverse('student_update_menu_cart_item', args=[self.menu_item.id]), {
            'quantity': 0
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['cart_count'], 0)
        self.assertFalse(CartItem.objects.filter(cart=cart, menu_item=self.menu_item).exists())

    def test_update_menu_cart_item_creates_or_updates_quantity(self):
        response = self.client.post(reverse('student_update_menu_cart_item', args=[self.menu_item.id]), {
            'quantity': 3
        })

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['cart_count'], 1)
        cart = Cart.objects.get(student=self.student)
        cart_item = CartItem.objects.get(cart=cart, menu_item=self.menu_item)
        self.assertEqual(cart_item.quantity, 3)

        response = self.client.post(reverse('student_update_menu_cart_item', args=[self.menu_item.id]), {
            'quantity': 2
        })

        self.assertEqual(response.status_code, 200)
        cart_item.refresh_from_db()
        self.assertEqual(cart_item.quantity, 2)

    def test_update_menu_cart_item_rejects_quantity_above_stock(self):
        response = self.client.post(reverse('student_update_menu_cart_item', args=[self.menu_item.id]), {
            'quantity': 6
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'Only 5 of Burger available right now.')
        self.assertFalse(CartItem.objects.filter(cart__student=self.student, menu_item=self.menu_item).exists())


class StudentCheckoutTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.student = User.objects.create_user(
            username='student1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.STUDENT
        )
        self.client.login(username='student1', password='Test@1234')

        self.vendor = User.objects.create_user(
            username='vendor1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.VENDOR
        )
        self.vendor_profile = VendorProfile.objects.create(
            user=self.vendor,
            outlet_name='Test Vendor'
        )
        self.menu_item = MenuItem.objects.create(
            vendor=self.vendor_profile,
            name='Burger',
            price=Decimal('100.00'),
            stock=5,
        )
        self.cart = Cart.objects.create(student=self.student)
        CartItem.objects.create(cart=self.cart, menu_item=self.menu_item, quantity=2)

    def test_checkout_page_loads(self):
        response = self.client.get(reverse('student_checkout'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'student/checkout.html')
        self.assertContains(response, 'checkout-location-status')
        self.assertContains(response, 'studentCheckoutLocationState')
        self.assertContains(response, 'studentCheckoutPendingPayment')
        self.assertIn('no-store', response['Cache-Control'])
        self.assertIn('no-cache', response['Cache-Control'])

    def test_checkout_with_empty_cart(self):
        CartItem.objects.all().delete()  # Empty cart
        response = self.client.get(reverse('student_checkout'))
        self.assertEqual(response.status_code, 302)  # Redirect to cart

    def test_checkout_reload_cancels_stale_pending_payment_session(self):
        stale_order = Order.objects.create(
            student=self.student,
            vendor=self.vendor_profile,
            total_amount=Decimal('200.00'),
            delivery_address='Hall 1',
            payment_status=Order.PaymentStatus.PENDING,
        )
        stale_payment = Payment.objects.create(
            order=stale_order,
            student=self.student,
            razorpay_order_id='order_reload_123',
            amount=Decimal('200.00'),
            currency='INR',
            status=Payment.PaymentStatus.PENDING,
        )

        response = self.client.get(reverse('student_checkout'))

        self.assertRedirects(response, reverse('student_view_cart'))
        stale_order.refresh_from_db()
        stale_payment.refresh_from_db()
        self.assertEqual(stale_order.payment_status, Order.PaymentStatus.FAILED)
        self.assertEqual(stale_order.vendor_status, Order.VendorStatus.CANCELLED)
        self.assertEqual(stale_payment.status, Payment.PaymentStatus.CANCELLED)

    @patch('users.views.razorpay.Client')
    def test_create_order_rejects_cart_items_above_stock(self, mock_razorpay_client):
        cart_item = CartItem.objects.get(cart=self.cart, menu_item=self.menu_item)
        cart_item.quantity = 6
        cart_item.save()

        response = self.client.post(reverse('student_create_order'), {
            'delivery_address': 'Hall 1'
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'Only 5 of Burger available right now.')
        mock_razorpay_client.assert_not_called()

    @patch('users.views.razorpay.Client')
    def test_create_order_reserves_stock_and_cancel_restores_it(self, mock_razorpay_client):
        mock_client_instance = mock_razorpay_client.return_value
        mock_client_instance.order.create.return_value = {
            'id': 'order_stock_123',
            'amount': 20000,
            'currency': 'INR'
        }

        response = self.client.post(reverse('student_create_order'), {
            'delivery_address': 'Hall 1'
        })

        self.assertEqual(response.status_code, 200)
        self.menu_item.refresh_from_db()
        self.assertEqual(self.menu_item.stock, 3)

        payload = response.json()
        cancel_response = self.client.post(
            reverse('student_cancel_payment'),
            data={
                'razorpay_order_id': payload['razorpay_order_id'],
                'order_ids': payload['orders'],
                'reason': 'Stock restore check',
            },
            content_type='application/json'
        )

        self.assertEqual(cancel_response.status_code, 200)
        self.menu_item.refresh_from_db()
        self.assertEqual(self.menu_item.stock, 5)


class StudentOrdersTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.student = User.objects.create_user(
            username='student1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.STUDENT
        )
        self.client.login(username='student1', password='Test@1234')

        self.vendor = User.objects.create_user(
            username='vendor1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.VENDOR
        )
        self.vendor_profile = VendorProfile.objects.create(
            user=self.vendor,
            outlet_name='Test Vendor'
        )
        self.order = Order.objects.create(
            student=self.student,
            vendor=self.vendor_profile,
            total_amount=Decimal('200.00')
        )

    def test_orders_list(self):
        response = self.client.get(reverse('student_orders'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'student/orders.html')
        self.assertContains(response, self.order.order_code)

    def test_order_detail(self):
        response = self.client.get(reverse('student_order_detail', args=[self.order.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'student/order_detail.html')
        self.assertContains(response, self.order.order_code)

    def test_quick_reorder_caps_quantity_at_current_stock(self):
        reorder_menu_item = MenuItem.objects.create(
            vendor=self.vendor_profile,
            name='Loaded Fries',
            price=Decimal('150.00'),
            stock=7,
        )
        delivered_order = Order.objects.create(
            student=self.student,
            vendor=self.vendor_profile,
            total_amount=Decimal('300.00'),
            delivery_status=Order.DeliveryStatus.DELIVERED,
        )
        OrderItem.objects.create(
            order=delivered_order,
            vendor_item=reorder_menu_item,
            item_name='Loaded Fries',
            unit_price=Decimal('150.00'),
            quantity=25,
        )

        response = self.client.post(reverse('student_quick_reorder_from_order', args=[delivered_order.id]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        cart_item = CartItem.objects.get(cart__student=self.student, menu_item__name='Loaded Fries')
        self.assertEqual(cart_item.quantity, 7)


# ─── Vendor Module Tests ──────────────────────────────────────────────────────
class VendorDashboardTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.vendor = User.objects.create_user(
            username='vendor1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.VENDOR
        )
        self.vendor_profile = VendorProfile.objects.create(
            user=self.vendor,
            outlet_name='Test Outlet'
        )
        self.client.login(username='vendor1', password='Test@1234')

    def test_vendor_dashboard_access(self):
        response = self.client.get(reverse('vendor_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'vendor/dashboard.html')

    def test_vendor_dashboard_shows_account_management_links(self):
        response = self.client.get(reverse('vendor_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Account Management')
        self.assertContains(response, reverse('change_password'))
        self.assertContains(response, reverse('account_settings'))
        self.assertContains(response, 'Delete Account')

    def test_unauthorized_access_to_vendor_dashboard(self):
        student = User.objects.create_user(
            username='student1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.STUDENT
        )
        self.client.login(username='student1', password='Test@1234')
        response = self.client.get(reverse('vendor_dashboard'))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_vendor_dashboard_hides_delivered_and_expired_orders(self):
        student = User.objects.create_user(
            username='student1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.STUDENT
        )

        active_order = Order.objects.create(
            student=student,
            vendor=self.vendor_profile,
            total_amount=Decimal('120.00'),
            vendor_decision=Order.VendorDecision.ACCEPTED,
            vendor_status=Order.VendorStatus.PREPARING,
        )
        delivered_order = Order.objects.create(
            student=student,
            vendor=self.vendor_profile,
            total_amount=Decimal('130.00'),
            vendor_decision=Order.VendorDecision.ACCEPTED,
            delivery_status=Order.DeliveryStatus.DELIVERED,
        )
        expired_order = Order.objects.create(
            student=student,
            vendor=self.vendor_profile,
            total_amount=Decimal('140.00'),
            vendor_decision=Order.VendorDecision.ACCEPTED,
            vendor_status=Order.VendorStatus.READY,
        )
        DeliveryBroadcast.objects.create(
            order=expired_order,
            status=DeliveryBroadcast.BroadcastStatus.ACTIVE,
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        response = self.client.get(reverse('vendor_dashboard'))
        self.assertEqual(response.status_code, 200)

        accepted_orders = list(response.context['accepted_orders'])
        self.assertIn(active_order, accepted_orders)
        self.assertNotIn(delivered_order, accepted_orders)
        self.assertNotIn(expired_order, accepted_orders)

    def test_vendor_update_location_requires_address_and_map_link(self):
        response = self.client.post(reverse('vendor_update_location'), {
            'outlet_name': 'Test Outlet',
            'google_maps_address': '',
            'google_maps_location': '',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        messages = list(response.context['messages'])
        self.assertTrue(any('select and save your outlet address' in str(message).lower() for message in messages))


class VendorMenuTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.vendor = User.objects.create_user(
            username='vendor1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.VENDOR
        )
        self.vendor_profile = VendorProfile.objects.create(
            user=self.vendor,
            outlet_name='Test Outlet'
        )
        self.client.login(username='vendor1', password='Test@1234')

    def test_add_menu_item(self):
        response = self.client.post(reverse('vendor_menu_add'), {
            'name': 'New Item',
            'price': '150.00',
            'stock': '12',
            'description': 'New description'
        })
        self.assertEqual(response.status_code, 302)  # Redirect to dashboard
        self.assertTrue(MenuItem.objects.filter(name='New Item').exists())
        self.assertEqual(MenuItem.objects.get(name='New Item').stock, 12)

    def test_update_menu_item(self):
        menu_item = MenuItem.objects.create(
            vendor=self.vendor_profile,
            name='Old Item',
            price=Decimal('100.00')
        )
        response = self.client.post(reverse('vendor_menu_update', args=[menu_item.id]), {
            'name': 'Updated Item',
            'price': '120.00',
            'stock': '8',
            'description': 'Updated description'
        })
        self.assertEqual(response.status_code, 302)
        menu_item.refresh_from_db()
        self.assertEqual(menu_item.name, 'Updated Item')
        self.assertEqual(menu_item.price, Decimal('120.00'))
        self.assertEqual(menu_item.stock, 8)


class VendorOrderManagementTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.vendor = User.objects.create_user(
            username='vendor1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.VENDOR
        )
        self.vendor_profile = VendorProfile.objects.create(
            user=self.vendor,
            outlet_name='Test Outlet'
        )
        self.client.login(username='vendor1', password='Test@1234')

        self.student = User.objects.create_user(
            username='student1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.STUDENT
        )
        self.order = Order.objects.create(
            student=self.student,
            vendor=self.vendor_profile,
            total_amount=Decimal('200.00')
        )

    def test_accept_order(self):
        response = self.client.post(reverse('vendor_ticket_accept', args=[self.order.id]), follow=True)
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.vendor_decision, Order.VendorDecision.ACCEPTED)

    def test_reject_order(self):
        response = self.client.post(reverse('vendor_ticket_reject', args=[self.order.id]), follow=True)
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.vendor_decision, Order.VendorDecision.REJECTED)

    def test_reject_order_restores_reserved_stock(self):
        menu_item = MenuItem.objects.create(
            vendor=self.vendor_profile,
            name='Wrap',
            price=Decimal('80.00'),
            stock=2,
        )
        OrderItem.objects.create(
            order=self.order,
            vendor_item=menu_item,
            item_name='Wrap',
            unit_price=Decimal('80.00'),
            quantity=3,
        )

        response = self.client.post(reverse('vendor_ticket_reject', args=[self.order.id]), follow=True)

        self.assertEqual(response.status_code, 200)
        menu_item.refresh_from_db()
        self.assertEqual(menu_item.stock, 5)

    def test_update_order_status(self):
        self.order.vendor_decision = Order.VendorDecision.ACCEPTED
        self.order.save()
        response = self.client.post(reverse('vendor_order_status_update', args=[self.order.id]), {
            'vendor_status': 'PREPARING'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.vendor_status, Order.VendorStatus.PREPARING)


# ─── Delivery Module Tests ────────────────────────────────────────────────────
class DeliveryDashboardTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.delivery = User.objects.create_user(
            username='delivery1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.DELIVERY
        )
        self.client.login(username='delivery1', password='Test@1234')

    def test_delivery_dashboard_access(self):
        response = self.client.get(reverse('delivery_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'delivery/dashboard.html')

    def test_delivery_dashboard_shows_account_management_links(self):
        response = self.client.get(reverse('delivery_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Account Management')
        self.assertContains(response, reverse('change_password'))
        self.assertContains(response, reverse('account_settings'))
        self.assertContains(response, 'Delete Account')

    def test_unauthorized_access_to_delivery_dashboard(self):
        student = User.objects.create_user(
            username='student1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.STUDENT
        )
        self.client.login(username='student1', password='Test@1234')
        response = self.client.get(reverse('delivery_dashboard'))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_delivery_dashboard_hides_available_orders_when_driver_has_active_delivery(self):
        vendor = User.objects.create_user(
            username='vendor1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.VENDOR
        )
        vendor_profile = VendorProfile.objects.create(user=vendor, outlet_name='Test Outlet')
        student = User.objects.create_user(
            username='student1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.STUDENT
        )
        active_order = Order.objects.create(student=student, vendor=vendor_profile, total_amount=Decimal('100.00'))
        DeliveryAssignment.objects.create(
            order=active_order,
            delivery_partner=self.delivery,
            status=DeliveryAssignment.AssignmentStatus.ACCEPTED
        )

        another_order = Order.objects.create(student=student, vendor=vendor_profile, total_amount=Decimal('120.00'))
        DeliveryBroadcast.objects.create(
            order=another_order,
            status=DeliveryBroadcast.BroadcastStatus.ACTIVE,
            expires_at=timezone.now() + timedelta(minutes=10)
        )

        response = self.client.get(reverse('delivery_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['has_active_delivery'])
        self.assertEqual(list(response.context['broadcasts']), [])


class DeliveryBroadcastTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.vendor = User.objects.create_user(
            username='vendor1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.VENDOR
        )
        self.vendor_profile = VendorProfile.objects.create(
            user=self.vendor,
            outlet_name='Test Outlet'
        )
        self.client.login(username='vendor1', password='Test@1234')

        self.student = User.objects.create_user(
            username='student1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.STUDENT
        )
        self.order = Order.objects.create(
            student=self.student,
            vendor=self.vendor_profile,
            total_amount=Decimal('200.00'),
            vendor_status=Order.VendorStatus.READY
        )

    def test_broadcast_delivery(self):
        self.vendor_profile.google_maps_location = 'https://www.google.com/maps/search/?api=1&query=26.5124,80.2394'
        self.vendor_profile.google_maps_address = 'IIT Kanpur, Test Outlet'
        self.vendor_profile.save()

        response = self.client.post(reverse('vendor_broadcast_delivery', args=[self.order.id]), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(DeliveryBroadcast.objects.filter(order=self.order).exists())
        messages = list(response.context['messages'])
        self.assertTrue(any('broadcasted' in str(message).lower() for message in messages))

    def test_broadcast_delivery_requires_vendor_location(self):
        response = self.client.post(reverse('vendor_broadcast_delivery', args=[self.order.id]), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(DeliveryBroadcast.objects.filter(order=self.order).exists())
        messages = list(response.context['messages'])
        self.assertTrue(any('outlet address' in str(message).lower() for message in messages))


class DeliveryAcceptanceTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.delivery = User.objects.create_user(
            username='delivery1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.DELIVERY
        )
        self.client.login(username='delivery1', password='Test@1234')

        self.vendor = User.objects.create_user(
            username='vendor1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.VENDOR
        )
        self.vendor_profile = VendorProfile.objects.create(
            user=self.vendor,
            outlet_name='Test Outlet'
        )
        self.student = User.objects.create_user(
            username='student1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.STUDENT
        )
        self.order = Order.objects.create(
            student=self.student,
            vendor=self.vendor_profile,
            total_amount=Decimal('200.00')
        )
        self.broadcast = DeliveryBroadcast.objects.create(
            order=self.order,
            status=DeliveryBroadcast.BroadcastStatus.ACTIVE,
            expires_at=timezone.now() + timedelta(minutes=10)
        )
        DeliveryBroadcastResponse.objects.create(
            broadcast=self.broadcast,
            delivery_partner=self.delivery,
            status=DeliveryBroadcastResponse.ResponseStatus.PENDING
        )

    def test_accept_broadcast(self):
        response = self.client.post(reverse('delivery_accept_broadcast', args=[self.broadcast.id]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.broadcast.refresh_from_db()
        self.assertEqual(self.broadcast.status, DeliveryBroadcast.BroadcastStatus.ACCEPTED)
        self.assertTrue(DeliveryAssignment.objects.filter(order=self.order).exists())

    def test_accept_broadcast_without_existing_response_row(self):
        DeliveryBroadcastResponse.objects.filter(
            broadcast=self.broadcast,
            delivery_partner=self.delivery
        ).delete()

        response = self.client.post(reverse('delivery_accept_broadcast', args=[self.broadcast.id]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        response_obj = DeliveryBroadcastResponse.objects.get(
            broadcast=self.broadcast,
            delivery_partner=self.delivery
        )
        self.assertEqual(response_obj.status, DeliveryBroadcastResponse.ResponseStatus.ACCEPTED)

    def test_accept_broadcast_blocked_when_driver_has_active_delivery(self):
        other_vendor = User.objects.create_user(
            username='vendor2',
            password='Test@1234',
            phone='8888888888',
            role=User.Role.VENDOR
        )
        other_vendor_profile = VendorProfile.objects.create(
            user=other_vendor,
            outlet_name='Other Outlet'
        )
        current_order = Order.objects.create(
            student=self.student,
            vendor=other_vendor_profile,
            total_amount=Decimal('150.00')
        )
        DeliveryAssignment.objects.create(
            order=current_order,
            delivery_partner=self.delivery,
            status=DeliveryAssignment.AssignmentStatus.PICKED_UP
        )

        response = self.client.post(reverse('delivery_accept_broadcast', args=[self.broadcast.id]))
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('Complete your current delivery', data['error'])

    def test_reject_broadcast(self):
        response = self.client.post(reverse('delivery_reject_broadcast', args=[self.broadcast.id]), {
            'reason': 'Too far'
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        response_obj = DeliveryBroadcastResponse.objects.get(
            broadcast=self.broadcast,
            delivery_partner=self.delivery
        )
        self.assertEqual(response_obj.status, DeliveryBroadcastResponse.ResponseStatus.REJECTED)


class DeliveryAssignmentTest(TestCase):

    def setUp(self):
        self.client = Client()
        self.delivery = User.objects.create_user(
            username='delivery1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.DELIVERY
        )
        self.client.login(username='delivery1', password='Test@1234')

        self.vendor = User.objects.create_user(
            username='vendor1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.VENDOR
        )
        self.vendor_profile = VendorProfile.objects.create(
            user=self.vendor,
            outlet_name='Test Outlet'
        )
        self.student = User.objects.create_user(
            username='student1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.STUDENT
        )
        self.order = Order.objects.create(
            student=self.student,
            vendor=self.vendor_profile,
            total_amount=Decimal('200.00'),
            delivery_address='Hall 1, IIT Kanpur'
        )
        self.broadcast = DeliveryBroadcast.objects.create(
            order=self.order,
            status=DeliveryBroadcast.BroadcastStatus.ACCEPTED,
            pickup_latitude=Decimal('26.5124'),
            pickup_longitude=Decimal('80.2394'),
            expires_at=timezone.now() + timedelta(minutes=10)
        )
        self.assignment = DeliveryAssignment.objects.create(
            order=self.order,
            delivery_partner=self.delivery,
            status=DeliveryAssignment.AssignmentStatus.ACCEPTED
        )

    def test_mark_picked_up(self):
        response = self.client.post(reverse('delivery_mark_picked_up', args=[self.assignment.id]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, DeliveryAssignment.AssignmentStatus.PICKED_UP)
        self.order.refresh_from_db()
        self.assertEqual(self.order.delivery_status, Order.DeliveryStatus.OUT_FOR_DELIVERY)

    def test_mark_delivered(self):
        self.assignment.status = DeliveryAssignment.AssignmentStatus.OUT_FOR_DELIVERY
        self.assignment.save()
        response = self.client.post(reverse('delivery_mark_delivered', args=[self.assignment.id]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, DeliveryAssignment.AssignmentStatus.DELIVERED)
        self.order.refresh_from_db()
        self.assertEqual(self.order.delivery_status, Order.DeliveryStatus.DELIVERED)

    @patch('users.views._generate_google_maps_link_from_address')
    def test_navigation_switches_to_student_after_pickup(self, mock_generate_maps_link):
        mock_generate_maps_link.return_value = (
            'https://www.google.com/maps/search/?api=1&query=26.5230,80.2450',
            'Hall 1, IIT Kanpur'
        )

        response = self.client.get(reverse('delivery_navigation', args=[self.assignment.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pickup from Vendor')

        self.assignment.status = DeliveryAssignment.AssignmentStatus.PICKED_UP
        self.assignment.save()

        response = self.client.get(reverse('delivery_navigation', args=[self.assignment.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Delivery to Student')


# ─── Integration Tests ────────────────────────────────────────────────────────
class EndToEndOrderingTest(TestCase):
    """
    Test the complete flow from student ordering to delivery completion.
    """

    def setUp(self):
        # Mock Razorpay settings
        from django.conf import settings
        if not hasattr(settings, 'RAZORPAY_KEY_ID'):
            settings.RAZORPAY_KEY_ID = 'test_key_id'
            settings.RAZORPAY_KEY_SECRET = 'test_key_secret'
        
        # Create users
        self.student = User.objects.create_user(
            username='student1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.STUDENT
        )
        self.vendor = User.objects.create_user(
            username='vendor1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.VENDOR
        )
        self.vendor_profile = VendorProfile.objects.create(
            user=self.vendor,
            outlet_name='Test Outlet'
        )
        self.delivery = User.objects.create_user(
            username='delivery1',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.DELIVERY
        )

        # Create menu item
        self.menu_item = MenuItem.objects.create(
            vendor=self.vendor_profile,
            name='Test Burger',
            price=Decimal('100.00'),
            description='Delicious burger'
        )

    @patch('users.views.razorpay.Client')
    def test_complete_order_flow(self, mock_razorpay_client):
        # Mock Razorpay client
        mock_client_instance = mock_razorpay_client.return_value
        mock_client_instance.order.create.return_value = {
            'id': 'order_test123',
            'amount': 20000,
            'currency': 'INR'
        }
        # Step 1: Student adds item to cart
        client = Client()
        client.login(username='student1', password='Test@1234')
        response = client.post(reverse('student_add_to_cart', args=[self.menu_item.id]), {
            'quantity': 2
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        # Step 2: Student checks out and creates order
        response = client.post(reverse('student_create_order'), {
            'delivery_address': 'IIT Kanpur, Hall 1'
        })
        self.assertEqual(response.status_code, 200)
        mock_client_instance.order.create.assert_called_once_with({
            'amount': 20000,
            'currency': 'INR',
            'payment_capture': '1',
        })
        data = response.json()
        self.assertTrue(data['success'])
        order_ids = data['orders']
        order_id = order_ids[0]  # Get first order
        self.assertEqual(CartItem.objects.filter(cart__student=self.student).count(), 1)
        order = Order.objects.get(id=order_id)
        self.assertEqual(order.student, self.student)
        self.assertEqual(order.vendor, self.vendor_profile)
        self.assertEqual(order.total_amount, Decimal('200.00'))

        # Step 3: Vendor accepts the order
        client.logout()
        client.login(username='vendor1', password='Test@1234')
        response = client.post(reverse('vendor_ticket_accept', args=[order.id]), follow=True)
        self.assertEqual(response.status_code, 200)  # After redirect
        order.refresh_from_db()
        self.assertEqual(order.vendor_decision, Order.VendorDecision.ACCEPTED)

        # Step 4: Vendor marks order as ready and broadcasts
        order.vendor_status = Order.VendorStatus.READY
        order.save()
        response = client.post(reverse('vendor_broadcast_delivery', args=[order.id]), follow=True)
        self.assertEqual(response.status_code, 200)
        broadcast = DeliveryBroadcast.objects.get(order=order)
        self.assertEqual(broadcast.status, DeliveryBroadcast.BroadcastStatus.ACTIVE)

        # Step 5: Delivery partner accepts the broadcast
        client.logout()
        client.login(username='delivery1', password='Test@1234')
        response = client.post(reverse('delivery_accept_broadcast', args=[broadcast.id]))
        self.assertEqual(response.status_code, 200)
        assignment = DeliveryAssignment.objects.get(order=order)
        self.assertEqual(assignment.delivery_partner, self.delivery)
        self.assertEqual(assignment.status, DeliveryAssignment.AssignmentStatus.ACCEPTED)

        # Step 6: Delivery partner marks as picked up
        response = client.post(reverse('delivery_mark_picked_up', args=[assignment.id]))
        self.assertEqual(response.status_code, 200)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, DeliveryAssignment.AssignmentStatus.PICKED_UP)
        order.refresh_from_db()
        self.assertEqual(order.delivery_status, Order.DeliveryStatus.OUT_FOR_DELIVERY)

        # Step 7: Delivery partner marks as delivered
        assignment.status = DeliveryAssignment.AssignmentStatus.OUT_FOR_DELIVERY
        assignment.save()
        response = client.post(reverse('delivery_mark_delivered', args=[assignment.id]))
        self.assertEqual(response.status_code, 200)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, DeliveryAssignment.AssignmentStatus.DELIVERED)
        order.refresh_from_db()
        self.assertEqual(order.delivery_status, Order.DeliveryStatus.DELIVERED)

        # Verify notifications were created
        student_notifications = Notification.objects.filter(recipient=self.student)
        self.assertTrue(student_notifications.exists())

        # Verify order history works
        client.logout()
        client.login(username='student1', password='Test@1234')
        response = client.get(reverse('student_order_history'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, order.order_code)
        self.assertContains(response, order.order_code)

    @patch('users.views.razorpay.Client')
    def test_cancel_payment_marks_pending_orders_cancelled(self, mock_razorpay_client):
        mock_client_instance = mock_razorpay_client.return_value
        mock_client_instance.order.create.return_value = {
            'id': 'order_cancel_123',
            'amount': 10000,
            'currency': 'INR'
        }

        client = Client()
        client.login(username='student1', password='Test@1234')
        client.post(reverse('student_add_to_cart', args=[self.menu_item.id]), {
            'quantity': 1
        })

        create_response = client.post(reverse('student_create_order'), {
            'delivery_address': 'IIT Kanpur, Hall 1'
        })
        self.assertEqual(create_response.status_code, 200)
        created_data = create_response.json()

        cancel_response = client.post(
            reverse('student_cancel_payment'),
            data={
                'razorpay_order_id': created_data['razorpay_order_id'],
                'order_ids': created_data['orders'],
                'reason': 'Payment cancelled by user',
            },
            content_type='application/json'
        )
        self.assertEqual(cancel_response.status_code, 200)
        cancel_data = cancel_response.json()
        self.assertTrue(cancel_data['success'])

        order = Order.objects.get(id=created_data['orders'][0])
        payment = Payment.objects.get(razorpay_order_id=created_data['razorpay_order_id'])

        self.assertEqual(order.payment_status, Order.PaymentStatus.FAILED)
        self.assertEqual(order.vendor_status, Order.VendorStatus.CANCELLED)
        self.assertEqual(payment.status, Payment.PaymentStatus.CANCELLED)
        self.assertEqual(CartItem.objects.filter(cart__student=self.student).count(), 1)

    @patch('users.views.razorpay.Client')
    def test_successful_payment_clears_cart(self, mock_razorpay_client):
        mock_client_instance = mock_razorpay_client.return_value
        mock_client_instance.order.create.return_value = {
            'id': 'order_success_123',
            'amount': 10000,
            'currency': 'INR'
        }

        client = Client()
        client.login(username='student1', password='Test@1234')
        client.post(reverse('student_add_to_cart', args=[self.menu_item.id]), {
            'quantity': 1
        })

        create_response = client.post(reverse('student_create_order'), {
            'delivery_address': 'IIT Kanpur, Hall 1'
        })
        self.assertEqual(create_response.status_code, 200)
        created_data = create_response.json()
        self.assertEqual(CartItem.objects.filter(cart__student=self.student).count(), 1)

        mock_client_instance.utility.verify_payment_signature.return_value = None
        verify_response = client.post(
            reverse('student_verify_payment'),
            data={
                'razorpay_order_id': created_data['razorpay_order_id'],
                'razorpay_payment_id': 'pay_success_123',
                'razorpay_signature': 'signature_123',
                'order_ids': created_data['orders'],
            },
            content_type='application/json'
        )
        self.assertEqual(verify_response.status_code, 200)
        self.assertTrue(verify_response.json()['success'])

        order = Order.objects.get(id=created_data['orders'][0])
        payment = Payment.objects.get(razorpay_order_id=created_data['razorpay_order_id'])

        self.assertEqual(order.payment_status, Order.PaymentStatus.COMPLETED)
        self.assertEqual(payment.status, Payment.PaymentStatus.SUCCESS)
        self.assertEqual(CartItem.objects.filter(cart__student=self.student).count(), 0)


class AccountDeletionTest(TestCase):

    def setUp(self):
        self.client = Client()

    def test_student_can_delete_account_when_no_active_orders(self):
        User.objects.create_user(
            username='delete_student',
            email='delete_student@iitk.ac.in',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.STUDENT,
        )
        ContactOTP.objects.create(
            purpose=ContactOTP.Purpose.STUDENT_REGISTER,
            channel=ContactOTP.Channel.EMAIL,
            target='delete_student@iitk.ac.in',
            code_hash='hash',
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        self.client.login(username='delete_student', password='Test@1234')
        response = self.client.post(
            reverse('delete_account'),
            {'confirmation': 'DELETE'},
            follow=True,
        )

        self.assertRedirects(response, reverse('login'))
        self.assertFalse(User.objects.filter(email='delete_student@iitk.ac.in').exists())
        self.assertFalse(ContactOTP.objects.filter(target='delete_student@iitk.ac.in').exists())

        recreated_user = User.objects.create_user(
            username='delete_student_again',
            email='delete_student@iitk.ac.in',
            password='Test@1234',
            phone='8888888888',
            role=User.Role.STUDENT,
        )
        self.assertEqual(recreated_user.email, 'delete_student@iitk.ac.in')

    def test_student_cannot_delete_account_with_active_order(self):
        student = User.objects.create_user(
            username='active_student',
            email='active_student@iitk.ac.in',
            password='Test@1234',
            phone='9999999999',
            role=User.Role.STUDENT,
        )
        vendor = User.objects.create_user(
            username='active_vendor',
            email='active_vendor@iitk.ac.in',
            password='Test@1234',
            phone='9999999998',
            role=User.Role.VENDOR,
        )
        vendor_profile = VendorProfile.objects.create(user=vendor, outlet_name='Campus Cafe')
        Order.objects.create(
            student=student,
            vendor=vendor_profile,
            total_amount=Decimal('120.00'),
            payment_status=Order.PaymentStatus.COMPLETED,
            vendor_decision=Order.VendorDecision.ACCEPTED,
            vendor_status=Order.VendorStatus.PREPARING,
        )

        self.client.login(username='active_student', password='Test@1234')
        response = self.client.post(
            reverse('delete_account'),
            {'confirmation': 'DELETE'},
            follow=True,
        )

        self.assertRedirects(response, reverse('account_settings'))
        self.assertTrue(User.objects.filter(email='active_student@iitk.ac.in').exists())
        self.assertContains(response, 'You still have active orders.')

    def test_vendor_deletion_clears_existing_application_record(self):
        vendor = User.objects.create_user(
            username='switch_vendor',
            email='switch_vendor@iitk.ac.in',
            password='Test@1234',
            phone='9999999997',
            role=User.Role.VENDOR,
        )
        VendorProfile.objects.create(user=vendor, outlet_name='Role Switch Outlet')
        StaffApplication.objects.create(
            full_name='Switch Vendor',
            email='switch_vendor@iitk.ac.in',
            phone='9999999997',
            role_applied=StaffApplication.Role.VENDOR,
            aadhaar_number='123412341234',
            outlet_name='Role Switch Outlet',
            outlet_location='MAIN_CANTEEN',
            cuisine_type='FAST_FOOD',
            operating_hours='09:00 - 21:00',
            fssai_license='12345678901234',
            bank_account='123456789012',
            ifsc_code='SBIN0001234',
            status=StaffApplication.Status.APPROVED,
        )

        self.client.login(username='switch_vendor', password='Test@1234')
        response = self.client.post(
            reverse('delete_account'),
            {'confirmation': 'DELETE'},
            follow=True,
        )

        self.assertRedirects(response, reverse('login'))
        self.assertFalse(User.objects.filter(email='switch_vendor@iitk.ac.in').exists())
        self.assertFalse(StaffApplication.objects.filter(email='switch_vendor@iitk.ac.in').exists())

        StaffApplication.objects.create(
            full_name='Switch Again',
            email='switch_vendor@iitk.ac.in',
            phone='9999999996',
            role_applied=StaffApplication.Role.DELIVERY,
            aadhaar_number='111122223333',
            status=StaffApplication.Status.PENDING,
        )
        self.assertEqual(
            StaffApplication.objects.filter(email='switch_vendor@iitk.ac.in').count(),
            1,
        )

    def test_delivery_cannot_delete_account_with_active_assignment(self):
        delivery_user = User.objects.create_user(
            username='active_delivery',
            email='active_delivery@iitk.ac.in',
            password='Test@1234',
            phone='9999999995',
            role=User.Role.DELIVERY,
        )
        vendor = User.objects.create_user(
            username='delivery_vendor',
            email='delivery_vendor@iitk.ac.in',
            password='Test@1234',
            phone='9999999994',
            role=User.Role.VENDOR,
        )
        student = User.objects.create_user(
            username='delivery_student',
            email='delivery_student@iitk.ac.in',
            password='Test@1234',
            phone='9999999993',
            role=User.Role.STUDENT,
        )
        vendor_profile = VendorProfile.objects.create(user=vendor, outlet_name='Delivery Outlet')
        order = Order.objects.create(
            student=student,
            vendor=vendor_profile,
            total_amount=Decimal('99.00'),
            payment_status=Order.PaymentStatus.COMPLETED,
            vendor_decision=Order.VendorDecision.ACCEPTED,
            vendor_status=Order.VendorStatus.READY,
        )
        DeliveryAssignment.objects.create(
            order=order,
            delivery_partner=delivery_user,
            status=DeliveryAssignment.AssignmentStatus.ACCEPTED,
        )

        self.client.login(username='active_delivery', password='Test@1234')
        response = self.client.post(
            reverse('delete_account'),
            {'confirmation': 'DELETE'},
            follow=True,
        )

        self.assertRedirects(response, reverse('account_settings'))
        self.assertTrue(User.objects.filter(email='active_delivery@iitk.ac.in').exists())
        self.assertContains(response, 'You still have an active delivery assignment.')
