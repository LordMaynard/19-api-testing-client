from django.contrib import admin
from .models import (
    Collection,
    SavedRequest,
    Environment,
    EnvironmentVariable,
    TestAssertion,
)


class SavedRequestInline(admin.TabularInline):
    model = SavedRequest
    extra = 1


class EnvironmentVariableInline(admin.TabularInline):
    model = EnvironmentVariable
    extra = 1


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at", "updated_at")
    search_fields = ("name", "description")
    inlines = [SavedRequestInline]


@admin.register(SavedRequest)
class SavedRequestAdmin(admin.ModelAdmin):
    list_display = ("name", "method", "collection", "updated_at")
    list_filter = ("method", "collection")
    search_fields = ("name", "url")


@admin.register(Environment)
class EnvironmentAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    inlines = [EnvironmentVariableInline]


@admin.register(EnvironmentVariable)
class EnvironmentVariableAdmin(admin.ModelAdmin):
    list_display = ("key", "environment", "is_secret")
    list_filter = ("is_secret", "environment")
    search_fields = ("key",)
@admin.register(TestAssertion)
class TestAssertionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "saved_request",
        "assertion_type",
        "expected_value",
    )
    list_filter = ("assertion_type",)
    search_fields = ("name", "saved_request__name")