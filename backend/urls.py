from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.views.static import serve
from django.views.decorators.cache import cache_page
from users.forms import PasswordResetWithSMSForm
from users.views import home_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home_view, name='home'),
    path('', include('users.urls')),

    # password reset
    path('password-reset/',
         auth_views.PasswordResetView.as_view(
             form_class=PasswordResetWithSMSForm,
             template_name='users/password_reset.html',
             success_url='/password-reset/done/'
         ), name='password_reset'),

    path('password-reset/done/',
         auth_views.PasswordResetDoneView.as_view(
             template_name='users/password_reset_done.html'
         ), name='password_reset_done'),

    path('password-reset-confirm/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(
             template_name='users/password_reset_confirm.html',
             reset_url_token='set-password',
             success_url='/password-reset-complete/'
         ), name='password_reset_confirm'),

    path('password-reset-complete/',
         auth_views.PasswordResetCompleteView.as_view(
             template_name='users/password_reset_complete.html'
         ), name='password_reset_complete'),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # In production, serve media files with proper path handling
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', cache_page(60*60*24)(serve), {
            'document_root': settings.MEDIA_ROOT
        }),
    ]
