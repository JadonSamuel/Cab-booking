from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', views.index, name='index'),
    path('book/', views.book_taxi, name='book_taxi'),
    path('taxis/', views.display_bookings, name='display_taxi_details'),
    path('cancel_booking/',views.cancel_booking,name='cancel_booking'),
    path('customer-trips/<int:customer_id>/', views.view_customer_trips, name='view_customer_trips'),
    path('modify_booking/', views.modify_booking, name='modify_booking'),
    path('login/', auth_views.LoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(template_name='logout.html'), name='logout'),
    path('register/', views.register, name='register'),
    path('driver-dashboard/', views.driver_dashboard, name='driver_dashboard'),
    path('user_group_list/', views.user_group_list, name='user_group_list'),
    path('display_taxis/',views.display_taxis,name='taxis'),
    path('register-driver/', views.register_driver, name='register-driver'),
    path('activate/<uidb64>/<token>/', views.activate, name='activate'),
    path('send-verification-email/',views.send_verification_email,name='email'),
    path('reset-password/', views.password_reset_request, name='password_reset_request'),
    path('reset-password-confirm/<uidb64>/<token>/', views.password_reset_confirm, name='password_reset_confirm'),

    
    
   
]
