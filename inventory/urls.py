from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet, ProductViewSet, StockViewSet

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("products", ProductViewSet, basename="product")
router.register("stock", StockViewSet, basename="stock")

urlpatterns = router.urls
