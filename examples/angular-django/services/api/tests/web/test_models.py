import pytest

from core.models import Todo


@pytest.mark.django_db
def test_todo_str_is_its_title():
    assert str(Todo.objects.create(title='Buy milk')) == 'Buy milk'


@pytest.mark.django_db
def test_todo_defaults_to_not_done():
    assert Todo.objects.create(title='Buy milk').done is False


@pytest.mark.django_db
def test_todos_are_ordered_oldest_first():
    first = Todo.objects.create(title='First')
    second = Todo.objects.create(title='Second')

    assert list(Todo.objects.all()) == [first, second]
