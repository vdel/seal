import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { Todo, TodoService } from '../todo.service';

/** The whole app: one shared todo list, with no sign-in in front of it. */
@Component({
  selector: 'app-todos',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './todos.html',
  styleUrl: './todos.css',
})
export class Todos implements OnInit {
  protected readonly service = inject(TodoService);

  protected readonly draft = signal('');
  protected readonly error = signal<string | null>(null);
  protected readonly submitting = signal(false);

  ngOnInit(): void {
    this.service.load().catch(() => this.error.set("Couldn't load the todo list."));
  }

  protected async onSubmit(): Promise<void> {
    const title = this.draft().trim();
    if (!title || this.submitting()) {
      return;
    }

    this.error.set(null);
    this.submitting.set(true);
    try {
      await this.service.add(title);
      this.draft.set('');
    } catch {
      this.error.set("Couldn't add that todo.");
    } finally {
      this.submitting.set(false);
    }
  }

  protected async onToggle(todo: Todo): Promise<void> {
    this.error.set(null);
    try {
      await this.service.setDone(todo, !todo.done);
    } catch {
      this.error.set("Couldn't update that todo.");
    }
  }

  protected async onRemove(todo: Todo): Promise<void> {
    this.error.set(null);
    try {
      await this.service.remove(todo);
    } catch {
      this.error.set("Couldn't delete that todo.");
    }
  }
}
