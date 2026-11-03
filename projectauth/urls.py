"""
URL configuration for projectauth (all prefixed with 'auth/', included at root '').
"""

from django.urls import path

from . import console_views, views

app_name = "projectauth"

urlpatterns = [
    path("auth/login/", views.login_view, name="login"),
    path("auth/logout/", views.logout_view, name="logout"),
    path("auth/signup/", views.signup_view, name="signup"),
    path("auth/signup/done/", views.signup_done_view, name="signup_done"),
    path("auth/verify-email/<str:token>/", views.verify_email_view, name="verify_email"),
    path("auth/verify-email/resend/", views.verify_email_resend_view, name="verify_email_resend"),
    path("auth/pending/", views.pending_view, name="pending"),
    path("auth/request-access/", views.request_access_view, name="request_access"),
    path("auth/access-denied/<str:app_label>/", views.access_denied_view, name="access_denied"),
    path("auth/forgot-password/", views.forgot_password_view, name="forgot_password"),
    path("auth/reset/<str:token>/", views.reset_password_view, name="reset_password"),
    path("auth/forgot-username/", views.forgot_username_view, name="forgot_username"),
    path("auth/force-password-change/", views.force_password_change_view, name="force_password_change"),
    path("auth/2fa/challenge/", views.twofa_challenge_view, name="twofa_challenge"),
    path("auth/2fa/setup/", views.twofa_setup_view, name="twofa_setup"),
    path("auth/2fa/recovery/", views.twofa_recovery_view, name="twofa_recovery"),
    path("auth/reauth/", views.reauth_view, name="reauth"),
    path("auth/account/", views.account_view, name="account"),
    path("auth/confirm-email-change/<str:token>/", views.confirm_email_change_view, name="confirm_email_change"),
    path("auth/account/export/", views.account_export_view, name="account_export"),
    path("auth/account/delete/", views.account_delete_view, name="account_delete"),
    path("auth/invite/<str:token>/", console_views.invite_accept_view, name="invite_accept"),
    path("auth/console/", console_views.console_dashboard_view, name="console_dashboard"),
    path("auth/console/pending/", console_views.console_pending_view, name="console_pending"),
    path("auth/console/users/", console_views.console_users_view, name="console_users"),
    path("auth/console/users/<int:user_id>/", console_views.console_user_detail_view, name="console_user_detail"),
    path("auth/console/apps/", console_views.console_apps_view, name="console_apps"),
    path("auth/console/requests/", console_views.console_requests_view, name="console_requests"),
    path("auth/console/admins/", console_views.console_admins_view, name="console_admins"),
    path("auth/console/invites/", console_views.console_invites_view, name="console_invites"),
    path("auth/console/audit/", console_views.console_audit_view, name="console_audit"),
    path("auth/console/audit/export/", console_views.console_audit_export_view, name="console_audit_export"),
    path("auth/console/settings/", console_views.console_settings_view, name="console_settings"),
]
