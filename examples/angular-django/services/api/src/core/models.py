from django.db import models


class Todo(models.Model):
    """One item on the todo list.

    There's no owner field, and no per-item permissions: this example has no
    user management at all, so every visitor sees and edits the same list.
    """

    title = models.CharField(max_length=255)
    done = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Oldest first, with `id` breaking ties between rows created inside
        # the same clock tick -- otherwise the list order is whatever Postgres
        # happens to return, which makes an assertion on it flaky.
        ordering = ('created_at', 'id')

    def __str__(self) -> str:
        return self.title
