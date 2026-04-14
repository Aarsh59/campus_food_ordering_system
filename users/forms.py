from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.tokens import default_token_generator
from django.template import loader
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .sms_utils import send_app_sms


class PasswordResetWithSMSForm(PasswordResetForm):
    def save(
        self,
        domain_override=None,
        subject_template_name='registration/password_reset_subject.txt',
        email_template_name='registration/password_reset_email.html',
        use_https=False,
        token_generator=default_token_generator,
        from_email=None,
        request=None,
        html_email_template_name=None,
        extra_email_context=None,
    ):
        email = self.cleaned_data['email']
        for user in self.get_users(email):
            if not user.email:
                continue

            if domain_override:
                site_name = domain_override
                domain = domain_override
            else:
                site_name = request.get_host()
                domain = request.get_host()

            context = {
                'email': user.email,
                'domain': domain,
                'site_name': site_name,
                'uid': urlsafe_base64_encode(force_bytes(user.pk)),
                'user': user,
                'token': token_generator.make_token(user),
                'protocol': 'https' if use_https else 'http',
                **(extra_email_context or {}),
            }

            subject = loader.render_to_string(subject_template_name, context)
            subject = ''.join(subject.splitlines())
            body = loader.render_to_string(email_template_name, context)
            self.send_mail(subject, body, from_email, user.email, html_email_template_name, context)

            send_app_sms(
                message=(
                    'A password reset email was sent for your Campus Food account. '
                    'Use the reset link from your inbox to continue.'
                ),
                recipient_phone=getattr(user, 'phone', ''),
            )
