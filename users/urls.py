from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
urlpatterns = [
    path('register/',          views.register_view,      name='register'),
    path('login/',             views.login_view,         name='login'),
    path('logout/',            views.logout_view,        name='logout'),
    path('apply/',             views.apply_view,         name='apply'),
    path('pending/',           views.pending_view,       name='pending'),
    path('student/dashboard/', views.student_dashboard,  name='student_dashboard'),
    path('vendor/dashboard/',  views.vendor_dashboard,   name='vendor_dashboard'),
    path('delivery/dashboard/',views.delivery_dashboard, name='delivery_dashboard'),
     path('change-password/', 
         auth_views.PasswordChangeView.as_view(
             template_name='users/change_password.html',
             success_url='/change-password/done/'
         ), name='change_password'),
    path('change-password/done/',
         auth_views.PasswordChangeDoneView.as_view(
             template_name='users/change_password_done.html'
         ), name='change_password_done'),
]