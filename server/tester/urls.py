import requests
from django.urls import path
from django.shortcuts import render
from . import views


def home(request):
    context = {}

    if request.method == "POST":
        method = request.POST.get("method", "GET").upper()
        url = request.POST.get("url", "").strip()

        allowed_methods = ["GET", "POST", "PUT", "PATCH", "DELETE"]

        if method not in allowed_methods:
            context["error"] = "Unsupported HTTP method."

        elif not url.startswith(("http://", "https://")):
            context["error"] = "Enter a valid URL starting with http:// or https://."

        else:
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    timeout=15,
                )

                context["status_code"] = response.status_code
                context["response_headers"] = dict(response.headers)
                context["response_body"] = response.text
                context["elapsed_time"] = round(
                    response.elapsed.total_seconds() * 1000, 2
                )

            except requests.RequestException as error:
                context["error"] = f"Request failed: {error}"

        context["selected_method"] = method
        context["entered_url"] = url

    return render(request, "tester/home.html", context)

from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("collections/", views.collections_view, name="collections"),
    path("requests/save/", views.save_request, name="save_request"),
    path("environments/", views.environments_view, name="environments"),
    path("test-runner/", views.test_runner, name="test_runner"),
]