from django.urls import path

from . import views

urlpatterns = [
    path('share-links/', views.sharelink_list, name='sharelink_list'),
    path('share-links/create/', views.sharelink_create, name='sharelink_create'),
    path('share-links/<int:pk>/revoke/', views.sharelink_revoke, name='sharelink_revoke'),

    path('share/<str:token>/', views.public_dashboard, name='public_dashboard'),
    path('share/<str:token>/data/', views.public_dashboard_data, name='public_dashboard_data'),
]
