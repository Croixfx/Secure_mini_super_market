from rest_framework.routers import DefaultRouter

from .views import CheckoutView, SaleViewSet
from django.urls import path

router = DefaultRouter()
router.register("history", SaleViewSet, basename="sale")

urlpatterns = [
    path("checkout/", CheckoutView.as_view(), name="checkout"),
] + router.urls
