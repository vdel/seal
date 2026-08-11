"""End-to-end tests for the todo API (see core/views.py)."""
import json

import pytest

from core.models import Todo


def _post(client, payload):
    return client.post('/todos', data=json.dumps(payload), content_type='application/json')


def _patch(client, todo_id, payload):
    return client.patch(f'/todos/{todo_id}', data=json.dumps(payload), content_type='application/json')


@pytest.mark.django_db
class TestListingTodos:
    def test_empty_list(self, api_client):
        response = api_client.get('/todos')
        assert response.status_code == 200
        assert response.json() == []

    def test_lists_saved_todos_oldest_first(self, api_client):
        Todo.objects.create(title='First')
        Todo.objects.create(title='Second')

        response = api_client.get('/todos')
        assert response.status_code == 200
        assert [item['title'] for item in response.json()] == ['First', 'Second']

    def test_serializes_every_field_the_ui_reads(self, api_client, todo):
        item = api_client.get('/todos').json()[0]
        assert item == {
            'id': todo.id,
            'title': 'Buy milk',
            'done': False,
            'created_at': todo.created_at.isoformat(),
        }


@pytest.mark.django_db
class TestCreatingTodos:
    def test_creates_and_returns_the_new_todo(self, api_client):
        response = _post(api_client, {'title': 'Buy milk'})

        assert response.status_code == 201
        assert response.json()['title'] == 'Buy milk'
        assert response.json()['done'] is False
        assert Todo.objects.count() == 1

    def test_trims_surrounding_whitespace(self, api_client):
        assert _post(api_client, {'title': '  Buy milk  '}).json()['title'] == 'Buy milk'

    @pytest.mark.parametrize('payload', [{}, {'title': ''}, {'title': '   '}, {'title': None}, {'title': 7}])
    def test_rejects_a_missing_or_blank_title(self, api_client, payload):
        assert _post(api_client, payload).status_code == 400
        assert Todo.objects.count() == 0

    def test_rejects_a_malformed_body(self, api_client):
        response = api_client.post('/todos', data='not json', content_type='application/json')
        assert response.status_code == 400


@pytest.mark.django_db
class TestUpdatingTodos:
    def test_marks_a_todo_done(self, api_client, todo):
        response = _patch(api_client, todo.id, {'done': True})

        assert response.status_code == 200
        assert response.json()['done'] is True
        todo.refresh_from_db()
        assert todo.done is True

    def test_marks_a_todo_not_done_again(self, api_client, todo):
        todo.done = True
        todo.save()

        assert _patch(api_client, todo.id, {'done': False}).json()['done'] is False

    def test_renames_a_todo_without_touching_done(self, api_client, todo):
        todo.done = True
        todo.save()

        response = _patch(api_client, todo.id, {'title': 'Buy oat milk'})

        assert response.json() == {**response.json(), 'title': 'Buy oat milk', 'done': True}

    def test_rejects_a_blank_title(self, api_client, todo):
        assert _patch(api_client, todo.id, {'title': '  '}).status_code == 400
        todo.refresh_from_db()
        assert todo.title == 'Buy milk'

    def test_unknown_todo_is_a_404(self, api_client):
        assert _patch(api_client, 404, {'done': True}).status_code == 404


@pytest.mark.django_db
class TestDeletingTodos:
    def test_deletes_the_todo(self, api_client, todo):
        response = api_client.delete(f'/todos/{todo.id}')

        assert response.status_code == 204
        assert Todo.objects.count() == 0

    def test_unknown_todo_is_a_404(self, api_client):
        assert api_client.delete('/todos/404').status_code == 404


@pytest.mark.django_db
class TestMethodsThatArentAllowed:
    def test_put_on_the_collection(self, api_client):
        assert api_client.put('/todos').status_code == 405

    def test_get_on_a_single_todo(self, api_client, todo):
        assert api_client.get(f'/todos/{todo.id}').status_code == 405
