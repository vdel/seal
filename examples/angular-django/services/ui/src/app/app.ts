import { Component } from '@angular/core';

import { Todos } from './todos/todos';

@Component({
  selector: 'app-root',
  imports: [Todos],
  templateUrl: './app.html',
  styleUrl: './app.css'
})
export class App {}
