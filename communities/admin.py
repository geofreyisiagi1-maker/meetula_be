from django.contrib import admin

from .models import Community


@admin.register(Community)
class CommunityAdmin(admin.ModelAdmin):
    list_display = ("name", "community_url", "visibility", "owner", "member_count", "created_at")
    list_filter = ("category", "visibility")
    search_fields = ("name", "description")
