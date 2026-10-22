import re
import json
import requests

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.urls import reverse

from .models import Collection, SavedRequest, Environment, EnvironmentVariable, TestAssertion




def home(request):
    context = {
        "selected_method": "GET",
        "entered_url": "",
        "request_headers": "",
        "request_body": "",
        "params_rows": [{"key": "", "value": ""}],
        "collections": Collection.objects.all(),
        "loaded_request_name": "",
        "selected_collection_id": None,
        "active_environment": Environment.objects.filter(
            is_active=True
        ).first(),
    }

    saved_request_id = request.GET.get("saved_request")

    if request.method == "GET" and saved_request_id:
        saved = get_object_or_404(SavedRequest, pk=saved_request_id)

        context.update({
            "selected_method": saved.method,
            "entered_url": saved.url,
            "request_headers": json.dumps(saved.headers, indent=4),
            "request_body": saved.body,
            "loaded_request_name": saved.name,
            "selected_collection_id": saved.collection_id,
            "params_rows": [
                {"key": key, "value": value}
                for key, value in saved.params.items()
            ] or [{"key": "", "value": ""}],
        })

    if request.method == "POST":
        method = request.POST.get("method", "GET").upper()
        url = request.POST.get("url", "").strip()
        headers_text = request.POST.get("request_headers", "").strip()
        body_text = request.POST.get("request_body", "").strip()

        param_keys = request.POST.getlist("param_key[]")
        param_values = request.POST.getlist("param_value[]")

        params = {}
        params_rows = []

        for key, value in zip(param_keys, param_values):
            key = key.strip()
            params_rows.append({"key": key, "value": value})
            if key:
                params[key] = value

        context.update({
            "selected_method": method,
            "entered_url": url,
            "request_headers": headers_text,
            "request_body": body_text,
            "params_rows": params_rows or [{"key": "", "value": ""}],
            "loaded_request_name": request.POST.get("request_name", ""),
            "selected_collection_id": request.POST.get("collection_id") or None,
        })

        allowed_methods = ["GET", "POST", "PUT", "PATCH", "DELETE"]

        try:
            if method not in allowed_methods:
                raise ValueError("Unsupported HTTP method.")

            # Load variables from the currently active environment.
            active_environment = Environment.objects.filter(
                is_active=True
            ).first()

            variables = {}
            secret_values = []

            if active_environment:
                environment_variables = EnvironmentVariable.objects.filter(
                    environment=active_environment
                )

                for variable in environment_variables:
                    variables[variable.key] = variable.value

                    if variable.is_secret and variable.value:
                        secret_values.append(variable.value)

            # Replace {{variable_name}} placeholders.
            placeholder_pattern = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")

            def resolve_variables(value):
                def replace_placeholder(match):
                    key = match.group(1).strip()

                    if key not in variables:
                        raise ValueError(
                            f'Missing environment variable: "{key}". '
                            "Add it to your active environment."
                        )

                    return variables[key]

                return placeholder_pattern.sub(replace_placeholder, value)

            # Resolve placeholders in the outgoing request.
            resolved_url = resolve_variables(url)

            if not resolved_url.startswith(("http://", "https://")):
                raise ValueError(
                    "Enter a valid URL starting with http:// or https://, "
                    "or configure your base_url environment variable."
                )

            headers = {}

            if headers_text:
                headers = json.loads(headers_text)

                if not isinstance(headers, dict):
                    raise ValueError(
                        "Headers must be a JSON object containing key-value pairs."
                    )

                if not all(
                    isinstance(key, str) and isinstance(value, str)
                    for key, value in headers.items()
                ):
                    raise ValueError(
                        "Every header name and value must be a string."
                    )

                headers = {
                    resolve_variables(key): resolve_variables(value)
                    for key, value in headers.items()
                }

            resolved_params = {
                resolve_variables(str(key)): resolve_variables(str(value))
                for key, value in params.items()
            }

            body = None

            if body_text:
                resolved_body_text = resolve_variables(body_text)
                body = json.loads(resolved_body_text)

            response = requests.request(
                method=method,
                url=resolved_url,
                params=resolved_params,
                headers=headers,
                json=body if body_text else None,
                timeout=15,
            )

            context["status_code"] = response.status_code
            context["response_headers"] = json.dumps(
                dict(response.headers),
                indent=4,
                ensure_ascii=False,
            )

            try:
                context["response_body"] = json.dumps(
                    response.json(),
                    indent=4,
                    ensure_ascii=False,
                )
            except ValueError:
                context["response_body"] = response.text

            context["elapsed_time"] = round(
                response.elapsed.total_seconds() * 1000, 2
            )

            # Avoid displaying secret values in the final URL.
            final_url = response.url
            for secret in sorted(secret_values, key=len, reverse=True):
                final_url = final_url.replace(secret, "[REDACTED]")

            context["final_url"] = final_url

        except json.JSONDecodeError as error:
            context["error"] = (
                f"Invalid JSON: {error.msg} "
                f"(line {error.lineno}, column {error.colno})."
            )
        except ValueError as error:
            context["error"] = str(error)
        except requests.Timeout:
            context["error"] = (
                "The request timed out. The server took too long to respond."
            )
        except requests.ConnectionError:
            context["error"] = (
                "Could not connect to the server. "
                "Check the URL and your internet connection."
            )
        except requests.RequestException:
            context["error"] = (
                "The request failed. Check the URL, headers, and connection."
            )

    return render(request, "tester/home.html", context)


def collections_view(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()

        if not name:
            messages.error(request, "Collection name is required.")
        else:
            collection, created = Collection.objects.get_or_create(
                name=name,
                defaults={"description": description},
            )

            if created:
                messages.success(
                    request,
                    f'Collection "{collection.name}" created successfully.',
                )
            else:
                messages.error(
                    request,
                    "A collection with that name already exists.",
                )

        return redirect("collections")

    collections = Collection.objects.prefetch_related(
        "saved_requests"
    ).all()

    return render(
        request,
        "tester/collections.html",
        {"collections": collections},
    )

def save_request(request):
    if request.method != "POST":
        return redirect("home")

    name = request.POST.get("request_name", "").strip()
    collection_id = request.POST.get("collection_id", "")
    method = request.POST.get("method", "GET").upper()
    url = request.POST.get("url", "").strip()
    headers_text = request.POST.get("request_headers", "").strip()
    body_text = request.POST.get("request_body", "").strip()

    if not name:
        messages.error(request, "Enter a name for this request.")
        return redirect("home")

    if not url.startswith(("http://", "https://")):
        messages.error(request, "Enter a valid HTTP or HTTPS URL.")
        return redirect("home")

    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        messages.error(request, "Unsupported HTTP method.")
        return redirect("home")

    try:
        collection = get_object_or_404(Collection, pk=collection_id)

        headers = json.loads(headers_text) if headers_text else {}
        if not isinstance(headers, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in headers.items()
        ):
            raise ValueError("Headers must be a JSON object of strings.")

        if body_text:
            json.loads(body_text)

        param_keys = request.POST.getlist("param_key[]")
        param_values = request.POST.getlist("param_value[]")

        params = {}
        for key, value in zip(param_keys, param_values):
            key = key.strip()
            if key:
                params[key] = value

        saved = SavedRequest.objects.filter(
            collection=collection,
            name=name,
        ).first()

        if saved:
            saved.method = method
            saved.url = url
            saved.headers = headers
            saved.params = params
            saved.body = body_text
            saved.save()
            messages.success(request, f'Request "{name}" updated.')
        else:
            saved = SavedRequest.objects.create(
                collection=collection,
                name=name,
                method=method,
                url=url,
                headers=headers,
                params=params,
                body=body_text,
            )
            messages.success(request, f'Request "{name}" saved.')

        return redirect(f"{reverse('home')}?saved_request={saved.pk}")

    except json.JSONDecodeError as error:
        messages.error(
            request,
            f"Invalid JSON at line {error.lineno}, column {error.colno}.",
        )
    except ValueError as error:
        messages.error(request, str(error))

    return redirect("home")

def environments_view(request):
    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "create_environment":
            name = request.POST.get("name", "").strip()
            description = request.POST.get("description", "").strip()

            if not name:
                messages.error(request, "Environment name is required.")
            elif Environment.objects.filter(name=name).exists():
                messages.error(request, "An environment with that name already exists.")
            else:
                is_first = not Environment.objects.filter(is_active=True).exists()

                Environment.objects.create(
                    name=name,
                    description=description,
                    is_active=is_first,
                )
                messages.success(request, f'Environment "{name}" created.')

        elif action == "activate_environment":
            environment_id = request.POST.get("environment_id")

            environment = get_object_or_404(
                Environment,
                pk=environment_id,
            )

            Environment.objects.filter(is_active=True).update(is_active=False)
            environment.is_active = True
            environment.save(update_fields=["is_active", "updated_at"])

            messages.success(
                request,
                f'"{environment.name}" is now the active environment.',
            )

        elif action == "add_variable":
            environment_id = request.POST.get("environment_id")
            key = request.POST.get("key", "").strip()
            value = request.POST.get("value", "")
            is_secret = request.POST.get("is_secret") == "on"

            environment = get_object_or_404(
                Environment,
                pk=environment_id,
            )

            if not key:
                messages.error(request, "Variable name is required.")
            elif EnvironmentVariable.objects.filter(
                environment=environment,
                key=key,
            ).exists():
                messages.error(
                    request,
                    "That variable already exists in this environment.",
                )
            else:
                EnvironmentVariable.objects.create(
                    environment=environment,
                    key=key,
                    value=value,
                    is_secret=is_secret,
                )
                messages.success(request, f'Variable "{key}" added.')

        elif action == "delete_variable":
            variable = get_object_or_404(
                EnvironmentVariable,
                pk=request.POST.get("variable_id"),
            )
            variable.delete()
            messages.success(request, "Variable deleted.")

        elif action == "delete_environment":
            environment = get_object_or_404(
                Environment,
                pk=request.POST.get("environment_id"),
            )
            name = environment.name
            environment.delete()
            messages.success(request, f'Environment "{name}" deleted.')

        else:
            messages.error(request, "Unknown environment action.")

        return redirect("environments")

    environments = Environment.objects.prefetch_related("variables").all()
    active_environment = environments.filter(is_active=True).first()

    return render(
        request,
        "tester/environments.html",
        {
            "environments": environments,
            "active_environment": active_environment,
        },
    )

def test_runner(request):
    saved_requests = SavedRequest.objects.select_related(
        "collection"
    ).prefetch_related("assertions").all()

    selected_request = None
    assertions = TestAssertion.objects.none()
    results = None

    if request.method == "POST":
        action = request.POST.get("action", "")
        saved_request_id = request.POST.get("saved_request_id")

        if action == "create_assertion":
            saved_request = get_object_or_404(
                SavedRequest, pk=saved_request_id
            )

            name = request.POST.get("name", "").strip()
            assertion_type = request.POST.get("assertion_type", "")
            json_path = request.POST.get("json_path", "").strip()
            expected_value = request.POST.get(
                "expected_value", ""
            ).strip()

            allowed_types = {
                choice[0]
                for choice in TestAssertion.ASSERTION_TYPES
            }

            if not name:
                messages.error(request, "Assertion name is required.")
            elif assertion_type not in allowed_types:
                messages.error(request, "Choose a valid assertion type.")
            elif assertion_type in {
                "json_path_exists", "json_path_equals"
            } and not json_path:
                messages.error(
                    request, "A JSON path is required for this assertion."
                )
            elif assertion_type in {
                "status_code", "response_time", "json_path_equals"
            } and not expected_value:
                messages.error(
                    request, "An expected value is required."
                )
            else:
                TestAssertion.objects.create(
                    saved_request=saved_request,
                    name=name,
                    assertion_type=assertion_type,
                    json_path=json_path,
                    expected_value=expected_value,
                )
                messages.success(request, "Assertion created.")

            return redirect(
                f"/test-runner/?request_id={saved_request.pk}"
            )

        elif action == "delete_assertion":
            assertion = get_object_or_404(
                TestAssertion, pk=request.POST.get("assertion_id")
            )
            request_id = assertion.saved_request_id
            assertion.delete()
            messages.success(request, "Assertion deleted.")
            return redirect(f"/test-runner/?request_id={request_id}")

        elif action == "run_tests":
            selected_request = get_object_or_404(
                SavedRequest, pk=saved_request_id
            )
            assertions = selected_request.assertions.all()

            try:
                active_environment = Environment.objects.filter(
                    is_active=True
                ).first()

                variables = {}
                if active_environment:
                    variables = {
                        item.key: item.value
                        for item in active_environment.variables.all()
                    }

                placeholder_pattern = re.compile(
                    r"\{\{\s*([^{}]+?)\s*\}\}"
                )

                def resolve(value):
                    def replace(match):
                        key = match.group(1).strip()
                        if key not in variables:
                            raise ValueError(
                                f'Missing environment variable: "{key}".'
                            )
                        return variables[key]

                    return placeholder_pattern.sub(replace, str(value))

                url = resolve(selected_request.url)
                headers = {
                    resolve(key): resolve(value)
                    for key, value in selected_request.headers.items()
                }
                params = {
                    resolve(key): resolve(value)
                    for key, value in selected_request.params.items()
                }

                body = None
                if selected_request.body.strip():
                    body = json.loads(resolve(selected_request.body))

                response = requests.request(
                    method=selected_request.method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=body,
                    timeout=15,
                )

                elapsed_ms = response.elapsed.total_seconds() * 1000

                try:
                    response_data = response.json()
                except ValueError:
                    response_data = None

                results = []

                def get_json_path(data, path):
                    current = data
                    for part in path.split("."):
                        if isinstance(current, dict) and part in current:
                            current = current[part]
                        elif isinstance(current, list) and part.isdigit():
                            index = int(part)
                            if index >= len(current):
                                return False, None
                            current = current[index]
                        else:
                            return False, None
                    return True, current

                for assertion in assertions:
                    passed = False
                    detail = ""

                    if assertion.assertion_type == "status_code":
                        expected = int(assertion.expected_value)
                        passed = response.status_code == expected
                        detail = (
                            f"Expected {expected}; received "
                            f"{response.status_code}."
                        )

                    elif assertion.assertion_type == "response_time":
                        expected = float(assertion.expected_value)
                        passed = elapsed_ms <= expected
                        detail = (
                            f"Expected at most {expected:g} ms; "
                            f"received {elapsed_ms:.2f} ms."
                        )

                    elif assertion.assertion_type in {
                        "json_path_exists", "json_path_equals"
                    }:
                        exists, actual = get_json_path(
                            response_data, assertion.json_path
                        )

                        if assertion.assertion_type == "json_path_exists":
                            passed = exists
                            detail = (
                                f"JSON field '{assertion.json_path}' "
                                + ("exists." if exists else "was not found.")
                            )
                        else:
                            expected_text = assertion.expected_value

                            try:
                                expected = json.loads(expected_text)
                            except ValueError:
                                expected = expected_text

                            passed = exists and actual == expected
                            detail = (
                                f"Expected {expected_text!r}; "
                                f"received {actual!r}."
                                if exists else
                                f"JSON field '{assertion.json_path}' "
                                "was not found."
                            )

                    results.append({
                        "name": assertion.name,
                        "passed": passed,
                        "detail": detail,
                    })

                context = {
                    "saved_requests": saved_requests,
                    "selected_request": selected_request,
                    "assertions": assertions,
                    "results": results,
                    "response_status": response.status_code,
                    "response_time": round(elapsed_ms, 2),
                }
                return render(
                    request, "tester/test_runner.html", context
                )

            except (
                ValueError, TypeError, json.JSONDecodeError
            ) as error:
                messages.error(request, f"Could not run tests: {error}")
            except requests.Timeout:
                messages.error(request, "The API request timed out.")
            except requests.RequestException:
                messages.error(
                    request, "The API request failed. Check the URL and connection."
                )

            return redirect(
                f"/test-runner/?request_id={selected_request.pk}"
            )

    request_id = request.GET.get("request_id")
    if request_id:
        selected_request = get_object_or_404(
            SavedRequest, pk=request_id
        )
        assertions = selected_request.assertions.all()

    return render(
        request,
        "tester/test_runner.html",
        {
            "saved_requests": saved_requests,
            "selected_request": selected_request,
            "assertions": assertions,
            "results": results,
        },
    )