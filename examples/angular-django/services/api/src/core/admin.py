from django.contrib import admin

from core.models import Todo


@admin.register(Todo)
class TodoAdmin(admin.ModelAdmin):
    list_display = ('title', 'done', 'created_at')
    list_filter = ('done',)
