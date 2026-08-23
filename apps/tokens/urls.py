from django.urls import path

from .views import RedeemCouponView, SubscriptionPackagesView, TransactionHistoryView

urlpatterns = [
    path("redeem/", RedeemCouponView.as_view(), name="redeem-coupon"),
    path("packages/", SubscriptionPackagesView.as_view(), name="subscription-packages"),
    path("transactions/", TransactionHistoryView.as_view(), name="transaction-history"),
]
