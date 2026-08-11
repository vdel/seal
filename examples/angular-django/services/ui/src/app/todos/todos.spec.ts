import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';

import { Todo } from '../todo.service';
import { Todos } from './todos';

const BUY_MILK: Todo = { id: 1, title: 'Buy milk', done: false, created_at: '2026-01-01T00:00:00+00:00' };

describe('Todos', () => {
  let httpMock: HttpTestingController;
  let fixture: ComponentFixture<Todos>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Todos],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(Todos);
  });

  afterEach(() => {
    httpMock.verify();
  });

  /** Renders the component and answers its initial GET with `todos`. */
  function load(todos: Todo[]): void {
    fixture.detectChanges();
    httpMock.expectOne('/api/todos').flush(todos);
    tick();
    fixture.detectChanges();
  }

  function element(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  it('lists the todos the API returns', fakeAsync(() => {
    load([BUY_MILK, { ...BUY_MILK, id: 2, title: 'Walk the dog', done: true }]);

    expect(element().querySelectorAll('.item').length).toBe(2);
    expect(element().textContent).toContain('Buy milk');
    expect(element().textContent).toContain('Walk the dog');
  }));

  it('says so when the list is empty', fakeAsync(() => {
    load([]);

    expect(element().textContent).toContain('Nothing here yet.');
  }));

  it('counts what is left to do', fakeAsync(() => {
    load([BUY_MILK, { ...BUY_MILK, id: 2, title: 'Walk the dog', done: true }]);

    expect(element().querySelector('.subtitle')?.textContent).toContain('1 of 2 left');
  }));

  it('strikes through a todo that is done', fakeAsync(() => {
    load([{ ...BUY_MILK, done: true }]);

    expect(element().querySelector('.item')?.classList).toContain('done');
  }));

  it('posts a new todo and appends what the API stored', fakeAsync(() => {
    load([]);

    const input = element().querySelector('input[name="title"]') as HTMLInputElement;
    input.value = '  Buy milk  ';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    (element().querySelector('.add-btn') as HTMLButtonElement).click();

    const request = httpMock.expectOne('/api/todos');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ title: 'Buy milk' });
    request.flush(BUY_MILK);
    tick();
    fixture.detectChanges();
    // ngModel writes the cleared value back to the input in a microtask, so
    // the DOM only catches up on the tick after this change-detection pass.
    tick();

    expect(element().textContent).toContain('Buy milk');
    expect(input.value).toBe('');
  }));

  it('does not post a blank todo', fakeAsync(() => {
    load([]);

    const input = element().querySelector('input[name="title"]') as HTMLInputElement;
    input.value = '   ';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    expect((element().querySelector('.add-btn') as HTMLButtonElement).disabled).toBeTrue();
  }));

  it('patches a todo when its checkbox is toggled', fakeAsync(() => {
    load([BUY_MILK]);

    (element().querySelector('.item input[type="checkbox"]') as HTMLInputElement).click();

    const request = httpMock.expectOne('/api/todos/1');
    expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual({ done: true });
    request.flush({ ...BUY_MILK, done: true });
    tick();
    fixture.detectChanges();

    expect(element().querySelector('.item')?.classList).toContain('done');
  }));

  it('deletes a todo and drops it from the list', fakeAsync(() => {
    load([BUY_MILK]);

    (element().querySelector('.remove-btn') as HTMLButtonElement).click();

    const request = httpMock.expectOne('/api/todos/1');
    expect(request.request.method).toBe('DELETE');
    request.flush(null, { status: 204, statusText: 'No Content' });
    tick();
    fixture.detectChanges();

    expect(element().querySelectorAll('.item').length).toBe(0);
  }));

  it('surfaces an error when the initial load fails', fakeAsync(() => {
    fixture.detectChanges();
    httpMock.expectOne('/api/todos').flush({}, { status: 500, statusText: 'Server Error' });
    tick();
    fixture.detectChanges();

    expect(element().querySelector('.error')?.textContent).toContain("Couldn't load the todo list.");
  }));

  it('surfaces an error when adding fails', fakeAsync(() => {
    load([]);

    const input = element().querySelector('input[name="title"]') as HTMLInputElement;
    input.value = 'Buy milk';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    (element().querySelector('.add-btn') as HTMLButtonElement).click();
    httpMock.expectOne('/api/todos').flush({}, { status: 500, statusText: 'Server Error' });
    tick();
    fixture.detectChanges();

    expect(element().querySelector('.error')?.textContent).toContain("Couldn't add that todo.");
  }));
});
