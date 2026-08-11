# ui

The example's Angular frontend: the todo list itself, talking to the Django
API at `/api/todos` (see `src/app/todo.service.ts` and `services/api`).

## Running locally

From the project root (`examples/angular-django/`):

```sh
seal up
```

In dev, this runs `ng serve` inside the `ui` container (merged into the
shared `web` pod, see `k8s/dev/web/ui/deployment.yaml`), reachable directly at
`http://localhost:4200` or through nginx at `http://localhost:8000/` (the
Django API is served at `/api/`, everything else goes to this app).

Outside of dev, there is no long-running `ui` container: the app is built to
static files (`ng build --configuration=production`) and copied into the
nginx container by an initContainer declared in that environment's own
overlay, served at `/`.

## Running in isolation

From this directory:

```sh
npm ci
npm start        # ng serve
npm test         # ng test (karma + jasmine, launches a local Chrome)
npm run build    # ng build
```
