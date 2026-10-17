from django.urls import path
from .views import RegisterView, LoginView, MeView

urlpatterns = [
    path('auth/register', RegisterView.as_view()),
    path('auth/login', LoginView.as_view()),
    path('users/me', MeView.as_view()),
]
