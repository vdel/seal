from django.urls import path

from core.views import health_check, todo_detail, todo_list

urlpatterns = [
    path('', health_check, name='health-check'),
    path('todos', todo_list, name='todo-list'),
    path('todos/<int:todo_id>', todo_detail, name='todo-detail'),
]
