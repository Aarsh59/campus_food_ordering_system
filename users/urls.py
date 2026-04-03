from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
urlpatterns = [
    path('register/',          views.register_view,      name='register'),
    path('login/',             views.login_view,         name='login'),
    path('logout/',            views.logout_view,        name='logout'),
    path('apply/',             views.apply_view,         name='apply'),
    path('pending/',           views.pending_view,       name='pending'),
    
    # Student Dashboard & Ordering
    path('student/dashboard/', views.student_dashboard,  name='student_dashboard'),
    path('student/vendors/', views.student_vendors_list, name='student_vendors_list'),
    path('student/vendor/<int:vendor_id>/', views.student_vendor_detail, name='student_vendor_detail'),
    path('student/cart/add/<int:item_id>/', views.student_add_to_cart, name='student_add_to_cart'),
    path('student/cart/', views.student_view_cart, name='student_view_cart'),
    path('student/cart/remove/<int:item_id>/', views.student_remove_from_cart, name='student_remove_from_cart'),
    path('student/cart/update/<int:item_id>/', views.student_update_cart_item, name='student_update_cart_item'),
    path('student/checkout/', views.student_checkout, name='student_checkout'),
    path('student/checkout/reverse-geocode/', views.student_reverse_geocode_location, name='student_reverse_geocode_location'),
    path('student/order/create/', views.student_create_order, name='student_create_order'),
    path('student/order/verify-payment/', views.student_verify_payment, name='student_verify_payment'),
    path('student/order/cancel-payment/', views.student_cancel_payment, name='student_cancel_payment'),
    path('student/orders/', views.student_orders, name='student_orders'),
    path('student/order/<int:order_id>/', views.student_order_detail, name='student_order_detail'),
    path('student/order/<int:order_id>/tracking/', views.get_order_tracking_updates, name='get_order_tracking_updates'),
    path('student/order-history/', views.student_order_history, name='student_order_history'),
    path('student/order/<int:order_id>/quick-add-to-cart/', views.student_quick_reorder_from_order, name='student_quick_reorder_from_order'),
    
    # Vendor Dashboard & Management
    path('vendor/dashboard/',  views.vendor_dashboard,   name='vendor_dashboard'),
    path('vendor/location/',   views.vendor_update_location, name='vendor_update_location'),
    path('vendor/location/generate/', views.vendor_generate_google_maps_link, name='vendor_generate_google_maps_link'),
    path('vendor/location/reverse/',  views.vendor_reverse_geocode_location, name='vendor_reverse_geocode_location'),
    path('vendor/menu/add/',   views.vendor_menu_add,        name='vendor_menu_add'),
    path('vendor/menu/<int:item_id>/update/', views.vendor_menu_update, name='vendor_menu_update'),
    path('vendor/tickets/<int:order_id>/accept/', views.vendor_ticket_accept, name='vendor_ticket_accept'),
    path('vendor/tickets/<int:order_id>/reject/', views.vendor_ticket_reject, name='vendor_ticket_reject'),
    path('vendor/orders/<int:order_id>/status/', views.vendor_order_status_update, name='vendor_order_status_update'),
    path('vendor/order/<int:order_id>/broadcast/', views.vendor_broadcast_delivery, name='vendor_broadcast_delivery'),
    
    # Delivery Dashboard & Management
    path('delivery/dashboard/',views.delivery_dashboard, name='delivery_dashboard'),
    path('delivery/available-orders/', views.delivery_available_orders, name='delivery_available_orders'),
    path('delivery/broadcast/<int:broadcast_id>/accept/', views.delivery_accept_broadcast, name='delivery_accept_broadcast'),
    path('delivery/broadcast/<int:broadcast_id>/reject/', views.delivery_reject_broadcast, name='delivery_reject_broadcast'),
    path('delivery/assignment/<int:assignment_id>/navigation/', views.delivery_navigation, name='delivery_navigation'),
    path('delivery/assignment/<int:assignment_id>/picked-up/', views.delivery_mark_picked_up, name='delivery_mark_picked_up'),
    path('delivery/assignment/<int:assignment_id>/out-for-delivery/', views.delivery_start_delivery, name='delivery_start_delivery'),
    path('delivery/assignment/<int:assignment_id>/delivered/', views.delivery_mark_delivered, name='delivery_mark_delivered'),
    path('delivery/assignment/<int:assignment_id>/location/', views.delivery_send_location, name='delivery_send_location'),
    
    # Password Reset
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
