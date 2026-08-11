import { HttpClient } from '@angular/common/http';
import { Injectable, computed, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

export interface Todo {
  id: number;
  title: string;
  done: boolean;
  created_at: string;
}

/**
 * Talks to the `/api/todos` endpoints (see services/api/src/core/views.py) and
 * holds the list as a signal for the rest of the app.
 *
 * The server's response is what updates local state after every write, rather
 * than the component patching its own copy optimistically -- so what's on
 * screen is always what was actually stored.
 */
@Injectable({ providedIn: 'root' })
export class TodoService {
  readonly todos = signal<Todo[]>([]);
  /** True once the first load has resolved, so the list can avoid flashing "nothing here yet". */
  readonly ready = signal(false);
  readonly remaining = computed(() => this.todos().filter((todo) => !todo.done).length);

  constructor(private readonly http: HttpClient) {}

  async load(): Promise<void> {
    this.todos.set(await firstValueFrom(this.http.get<Todo[]>('/api/todos')));
    this.ready.set(true);
  }

  async add(title: string): Promise<void> {
    const created = await firstValueFrom(this.http.post<Todo>('/api/todos', { title }));
    this.todos.update((todos) => [...todos, created]);
  }

  async setDone(todo: Todo, done: boolean): Promise<void> {
    const updated = await firstValueFrom(this.http.patch<Todo>(`/api/todos/${todo.id}`, { done }));
    this.todos.update((todos) => todos.map((item) => (item.id === updated.id ? updated : item)));
  }

  async remove(todo: Todo): Promise<void> {
    await firstValueFrom(this.http.delete(`/api/todos/${todo.id}`));
    this.todos.update((todos) => todos.filter((item) => item.id !== todo.id));
  }
}
