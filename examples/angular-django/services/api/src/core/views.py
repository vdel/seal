"""The example's HTTP surface: a health check plus CRUD over the todo list.

Plain Django views returning `JsonResponse`, rather than a REST framework:
this example exists to exercise the environment (Tilt, Kubernetes, the
`seal` CLI), so its API keeps its dependency list short and its behaviour
easy to read in one file.
"""
import json

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from core.models import Todo


def health_check(request: HttpRequest) -> JsonResponse:
    """Health-check endpoint, exposed as /api/ through nginx (the Angular app
    owns / and everything else, see k8s/dev/web/nginx/nginx-config.yaml).

    Returns a simple JSON payload so it's easy to check the API is up, both
    for humans (browser, curl) and for the Kubernetes readiness/liveness
    probes configured in k8s/dev/web/api/deployment.yaml.
    """
    return JsonResponse({'status': 'ok', 'service': 'api'})


def _serialize(todo: Todo) -> dict:
    return {
        'id': todo.id,
        'title': todo.title,
        'done': todo.done,
        'created_at': todo.created_at.isoformat(),
    }


def _json_body(request: HttpRequest) -> dict | None:
    """The request's JSON body, or None if it isn't parseable -- callers turn
    that into a 400 rather than letting it surface as a 500."""
    try:
        body = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return None
    return body if isinstance(body, dict) else None


def _clean_title(raw: object) -> str | None:
    """A usable title, or None when the value is missing/blank/not a string."""
    if not isinstance(raw, str):
        return None
    title = raw.strip()
    return title or None


# csrf_exempt on a write endpoint is safe *here specifically*: this example has
# no user management, so a request carries no identity a cross-site form could
# borrow -- a forged POST can do nothing a direct one couldn't already do. An
# app with sessions must not copy this; it needs Django's CSRF token flow.
@csrf_exempt
@require_http_methods(['GET', 'POST'])
def todo_list(request: HttpRequest) -> JsonResponse:
    if request.method == 'GET':
        # safe=False: the payload is a JSON array, not an object.
        return JsonResponse([_serialize(todo) for todo in Todo.objects.all()], safe=False)

    body = _json_body(request)
    if body is None:
        return JsonResponse({'error': 'Expected a JSON object body.'}, status=400)

    title = _clean_title(body.get('title'))
    if title is None:
        return JsonResponse({'error': 'A todo needs a non-empty title.'}, status=400)

    return JsonResponse(_serialize(Todo.objects.create(title=title)), status=201)


@csrf_exempt  # see todo_list above
@require_http_methods(['PATCH', 'DELETE'])
def todo_detail(request: HttpRequest, todo_id: int) -> HttpResponse:
    todo = get_object_or_404(Todo, pk=todo_id)

    if request.method == 'DELETE':
        todo.delete()
        return HttpResponse(status=204)

    body = _json_body(request)
    if body is None:
        return JsonResponse({'error': 'Expected a JSON object body.'}, status=400)

    # Both fields are optional, so the UI can toggle `done` without resending
    # the title (and rename without resending `done`). Presence of the key is
    # what marks a field as being changed, not its value.
    if 'title' in body:
        title = _clean_title(body['title'])
        if title is None:
            return JsonResponse({'error': 'A todo needs a non-empty title.'}, status=400)
        todo.title = title
    if 'done' in body:
        todo.done = bool(body['done'])

    todo.save()
    return JsonResponse(_serialize(todo))
