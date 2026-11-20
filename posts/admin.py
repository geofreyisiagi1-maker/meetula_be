from django.contrib import admin

from .models import Comment, Post, PostImage, Reply


class PostImageInline(admin.TabularInline):
    model = PostImage
    extra = 0


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("title", "post_type", "community", "author", "created_at")
    list_filter = ("post_type", "community")
    search_fields = ("title", "content")
    inlines = [PostImageInline]


admin.site.register(Comment)
admin.site.register(Reply)
