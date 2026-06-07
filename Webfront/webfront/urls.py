from django.urls import path
from . import views

app_name = 'webfront'

urlpatterns = [
    path('', views.index, name='index'),
    path('airfoils/', views.airfoil_list, name='airfoil_list'),
    path('airfoils/<str:code>/', views.airfoil_detail, name='airfoil_detail'),
    path('search/', views.search_airfoils, name='search_airfoils'),
    path('compare/', views.compare_airfoils, name='compare_airfoils'),
    path('anomalies/', views.anomaly_list, name='anomaly_list'),
    path('visualize/', views.visualize, name='visualize'),
    path('nl2sql/', views.nl2sql, name='nl2sql'),
    path('nl2sql/api/', views.nl2sql_api, name='nl2sql_api'),
]
