import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed, fakeAsync, tick } from '@angular/core/testing';

import { App } from './app';

describe('App', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('should create the app', fakeAsync(() => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();

    httpMock.expectOne('/api/todos').flush([]);
    tick();

    expect(fixture.componentInstance).toBeTruthy();
  }));

  it('renders the todo list', fakeAsync(() => {
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();

    httpMock.expectOne('/api/todos').flush([
      { id: 1, title: 'Buy milk', done: false, created_at: '2026-01-01T00:00:00+00:00' },
    ]);
    tick();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('app-todos')).toBeTruthy();
    expect(compiled.textContent).toContain('Buy milk');
  }));
});
