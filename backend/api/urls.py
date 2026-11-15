from django.urls import path

from . import views


urlpatterns = [
    path("health/", views.health, name="health"),
    path("ingestion-status/", views.ingestion_status, name="ingestion_status"),
    path("area-requests/", views.area_requests, name="area_requests"),
    path("area-requests/estimate/", views.estimate_area_request, name="estimate_area_request"),
    path("area-requests/create/", views.create_area_request, name="create_area_request"),
    path("hotspots/", views.hotspots, name="hotspots"),
    path("hotspots.csv", views.hotspots_csv, name="hotspots_csv"),
    path("analytics/", views.analytics, name="analytics"),
    path("upload/", views.upload, name="upload"),
    path("template.csv", views.template_csv, name="template_csv"),
]
