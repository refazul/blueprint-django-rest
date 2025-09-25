# inventory/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    CategoryViewSet, ProductViewSet, ProductVariationViewSet,
    StockEntryViewSet, RetailSaleViewSet, CategoryPageAPIView,
    OrderViewSet, create_order, update_price, SupplierViewSet,
    NavigationAPIView, CategoryImageViewSet, PriceAnalysisAPIView,
    price_drops_api, price_increases_api, volatile_prices_api,
    SiteConfigAPIView
)

router = DefaultRouter()
router.register(r'categories', CategoryViewSet)
router.register(r'category-images', CategoryImageViewSet)
router.register(r'products', ProductViewSet)
router.register(r'variations', ProductVariationViewSet)
router.register(r'suppliers', SupplierViewSet)
router.register(r'stock-entries', StockEntryViewSet)
router.register(r'retail-sales', RetailSaleViewSet)
#router.register(r'orders', OrderViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('categories/<slug:slug>/products/', CategoryPageAPIView.as_view(), name='category-page'),
    path('orders/create/', create_order, name='create-order'),  # Only this is public
    path('update-price/', update_price, name='update_price'),
    path('navigation/', NavigationAPIView.as_view(), name='navigation'),
    path('site-config/', SiteConfigAPIView.as_view(), name='site-config'),
        # Price Analysis API endpoints
    path('price-analysis/', PriceAnalysisAPIView.as_view(), name='price-analysis'),
    path('price-drops/', price_drops_api, name='price-drops-api'),
    path('price-increases/', price_increases_api, name='price-increases-api'),
    path('volatile-prices/', volatile_prices_api, name='volatile-prices-api'),
]
