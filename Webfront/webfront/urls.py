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
    path('nl2sql/audits/', views.nl2sql_audit_list, name='nl2sql_audit_list'),
    path('nl2sql/audits/<uuid:audit_id>/', views.nl2sql_audit_detail, name='nl2sql_audit_detail'),
    path('nl2sql/explain-audits/', views.explain_audit_list, name='explain_audit_list'),
    path('nl2sql/explain-audits/<uuid:explain_id>/', views.explain_audit_detail, name='explain_audit_detail'),
    path('nl2sql/history/', views.nl2sql_history, name='nl2sql_history'),
    # 可视化 JSON API
    path('visualize/api/foil-profiles/', views.visualize_api_foil_profiles, name='visualize_api_foil_profiles'),
    path('visualize/api/cl-alpha/', views.visualize_api_cl_alpha, name='visualize_api_cl_alpha'),
    path('visualize/api/cd-ld/', views.visualize_api_cd_ld, name='visualize_api_cd_ld'),
    path('visualize/api/multi-comparison/', views.visualize_api_multi_comparison, name='visualize_api_multi_comparison'),
    path('visualize/api/anomaly-detection/', views.visualize_api_anomaly_detection, name='visualize_api_anomaly_detection'),
    path('visualize/api/data-overview/', views.visualize_api_data_overview, name='visualize_api_data_overview'),
]
