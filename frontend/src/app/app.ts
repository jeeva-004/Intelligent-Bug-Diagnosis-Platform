import { Component } from '@angular/core';
import { SubmitBug } from './submit-bug/submit-bug';

@Component({
  imports: [SubmitBug],
  selector: 'app-root',
  styleUrl: './app.css',
  templateUrl: './app.html',
})
export class App {}
