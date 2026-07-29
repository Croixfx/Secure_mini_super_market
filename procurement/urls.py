from rest_framework.routers import DefaultRouter

from .views import PurchaseOrderViewSet, SupplierViewSet

router = DefaultRouter()
router.register("suppliers", SupplierViewSet, basename="supplier")
router.register("purchase-orders", PurchaseOrderViewSet, basename="purchaseorder")

urlpatterns = router.urls
