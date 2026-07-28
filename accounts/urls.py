from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    AdminLogoutView,
    AdminRefreshSilentView,
    AdminTokenObtainPairView,
    CustomTokenObtainPairView,
    LogoutView,
    MFAEnrollConfirmView,
    MFAEnrollView,
    POSLogoutView,
    POSRefreshSilentView,
    POSTokenObtainPairView,
    RefreshSilentView,
    UserAdminViewSet,
)

router = DefaultRouter()
router.register("users", UserAdminViewSet, basename="user-admin")

urlpatterns = [
    # Generic/unscoped — used by the test suite and any non-browser API
    # consumer. Not used by either frontend app; see pos/admin below for why.
    path("auth/login/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/refresh-silent/", RefreshSilentView.as_view(), name="refresh_silent"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),

    # pos-frontend and admin-frontend each get their own cookie namespace
    # (name + path) so logging into one never silently authenticates the
    # other — see _RefreshCookieMixin's docstring in views.py.
    path("auth/pos/login/", POSTokenObtainPairView.as_view(), name="pos_token_obtain_pair"),
    path("auth/pos/refresh-silent/", POSRefreshSilentView.as_view(), name="pos_refresh_silent"),
    path("auth/pos/logout/", POSLogoutView.as_view(), name="pos_logout"),

    path("auth/admin/login/", AdminTokenObtainPairView.as_view(), name="admin_token_obtain_pair"),
    path("auth/admin/refresh-silent/", AdminRefreshSilentView.as_view(), name="admin_refresh_silent"),
    path("auth/admin/logout/", AdminLogoutView.as_view(), name="admin_logout"),

    # MFA enrollment — Owner/Manager only (see MFA_REQUIRED_ROLES). One pair
    # of endpoints regardless of which frontend the user is on: enrollment
    # only needs the access token (Authorization header), which both apps'
    # tokens satisfy identically — it doesn't touch the refresh cookie at
    # all, so there's no pos/admin namespacing concern here.
    path("auth/mfa/enroll/", MFAEnrollView.as_view(), name="mfa_enroll"),
    path("auth/mfa/enroll/confirm/", MFAEnrollConfirmView.as_view(), name="mfa_enroll_confirm"),
] + router.urls
