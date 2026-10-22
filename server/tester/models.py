from django.db import models


class Collection(models.Model):
    """A group of related saved API requests."""

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["name"],
                name="unique_collection_name",
            )
        ]

    def __str__(self):
        return self.name


class SavedRequest(models.Model):
    """A reusable API request stored inside a collection."""

    METHOD_CHOICES = [
        ("GET", "GET"),
        ("POST", "POST"),
        ("PUT", "PUT"),
        ("PATCH", "PATCH"),
        ("DELETE", "DELETE"),
    ]

    collection = models.ForeignKey(
        Collection,
        on_delete=models.CASCADE,
        related_name="saved_requests",
    )
    name = models.CharField(max_length=150)
    method = models.CharField(
        max_length=10,
        choices=METHOD_CHOICES,
        default="GET",
    )
    url = models.URLField(max_length=2000)
    headers = models.JSONField(default=dict, blank=True)
    params = models.JSONField(default=dict, blank=True)
    body = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["collection", "name"],
                name="unique_saved_request_name_per_collection",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.method})"


class Environment(models.Model):
    """A configuration environment, such as Development or Production."""

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class EnvironmentVariable(models.Model):
    """A reusable key-value variable belonging to an environment."""

    environment = models.ForeignKey(
        Environment,
        on_delete=models.CASCADE,
        related_name="variables",
    )
    key = models.CharField(max_length=150)
    value = models.TextField(blank=True)
    is_secret = models.BooleanField(default=False)

    class Meta:
        ordering = ["key"]
        constraints = [
            models.UniqueConstraint(
                fields=["environment", "key"],
                name="unique_environment_variable_key",
            )
        ]

    def __str__(self):
        return f"{self.environment.name}: {self.key}"

class TestAssertion(models.Model):
    """A reusable test assertion associated with a saved API request."""

    ASSERTION_TYPES = [
        ("status_code", "Status Code"),
        ("response_time", "Response Time"),
        ("json_path_exists", "JSON Field Exists"),
        ("json_path_equals", "JSON Field Equals"),
    ]

    saved_request = models.ForeignKey(
        SavedRequest,
        on_delete=models.CASCADE,
        related_name="assertions",
    )
    name = models.CharField(max_length=150)
    assertion_type = models.CharField(
        max_length=30,
        choices=ASSERTION_TYPES,
    )
    json_path = models.CharField(
        max_length=255,
        blank=True,
        help_text="Example: userId or data.user.id",
    )
    expected_value = models.TextField(
        blank=True,
        help_text="Expected status code, maximum response time in milliseconds, or JSON value.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.name} - {self.saved_request.name}"