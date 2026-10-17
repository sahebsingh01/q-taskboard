from django.urls import path, include
from django.http import JsonResponse


def health(request):
    return JsonResponse({'ok': True})


urlpatterns = [
    path('api/health', health),
    path('api/', include('users.urls')),
    path('api/', include('projects.urls')),
]
