from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.participation_request_view, name='home'),
    path('request-submitted/', views.request_submitted_view, name='request_submitted'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('change-password/', views.FirstLoginPasswordChangeView.as_view(), name='change_password'),

    path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='accounts/password_reset.html',
        email_template_name='accounts/email/password_reset.txt',
        subject_template_name='accounts/email/password_reset_subject.txt',
        success_url=reverse_lazy('password_reset_done'),
    ), name='password_reset'),

    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='accounts/password_reset_done.html',
    ), name='password_reset_done'),

    path('password-reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='accounts/password_reset_confirm.html',
        success_url=reverse_lazy('password_reset_complete'),
    ), name='password_reset_confirm'),

    path('password-reset/complete/', auth_views.PasswordResetCompleteView.as_view(
        template_name='accounts/password_reset_complete.html',
    ), name='password_reset_complete'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('accounts/profile/', views.profile_view, name='profile'),
    path('accounts/users/', views.user_list_view, name='user_list'),
    path('accounts/users/create/', views.user_create_view, name='user_create'),
    path('accounts/users/<int:pk>/edit/', views.user_edit_view, name='user_edit'),
    path('accounts/users/<int:pk>/delete/', views.user_delete_view, name='user_delete'),
    path('accounts/users/<int:pk>/resend-welcome/', views.resend_welcome_email_view, name='resend_welcome_email'),
    path('emails/', views.email_log_view, name='email_log'),
    path('accounts/organizations/', views.org_list_view, name='org_list'),
    path('accounts/organizations/create/', views.org_create_view, name='org_create'),
    path('accounts/organizations/<int:pk>/edit/', views.org_edit_view, name='org_edit'),
    path('accounts/organizations/<int:pk>/delete/', views.org_delete_view, name='org_delete'),
    path('accounts/requests/', views.request_list_view, name='request_list'),
    path('accounts/requests/approval-success/', views.request_approval_success_view, name='request_approval_success'),
    path('accounts/requests/<int:pk>/', views.request_detail_view, name='request_detail'),
    path('accounts/requests/<int:pk>/approve/', views.request_approve_view, name='request_approve'),
    path('accounts/requests/<int:pk>/reject/', views.request_reject_view, name='request_reject'),
    path('accounts/requests/<int:pk>/reopen/', views.request_reopen_view, name='request_reopen'),
]
