from rest_framework.routers import DefaultRouter

from .transfer_views import StockTransferViewSet
from .views import CategoryViewSet, ProductViewSet, StockViewSet, StockMovementViewSet

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("products", ProductViewSet, basename="product")
router.register("stock", StockViewSet, basename="stock")
router.register("movements", StockMovementViewSet, basename="movement")
router.register("transfers", StockTransferViewSet, basename="stocktransfer")

urlpatterns = router.urls
