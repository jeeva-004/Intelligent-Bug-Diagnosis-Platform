import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { BugReport, BugReportService } from '../bug-report.service';
import { ALLOWED_EXTENSIONS, MAX_FILE_BYTES } from '../config';

type FieldKey = 'description' | 'stack_trace' | 'error_log';

interface FieldConfig {
  key: FieldKey;
  label: string;
  required: boolean;
  placeholder: string;
  rows: number;
}

@Component({
  selector: 'app-submit-bug',
  imports: [ReactiveFormsModule],
  templateUrl: './submit-bug.html',
  styleUrl: './submit-bug.css',
})
export class SubmitBug {
  private readonly api = inject(BugReportService);

  protected readonly fields: FieldConfig[] = [
    {
      key: 'description',
      label: 'Bug description',
      required: true,
      placeholder: 'What happened, what you expected, and the steps to reproduce it',
      rows: 7,
    },
    {
      key: 'stack_trace',
      label: 'Stack trace',
      required: false,
      placeholder: 'Paste the exception and the stack frames',
      rows: 7,
    },
    {
      key: 'error_log',
      label: 'Error log',
      required: false,
      placeholder: 'Paste the relevant log lines',
      rows: 7,
    },
  ];

  protected readonly allowedList = ALLOWED_EXTENSIONS.join(', ');
  protected readonly maxMb = MAX_FILE_BYTES / (1024 * 1024);

  protected readonly form = new FormGroup({
    title: new FormControl('', { nonNullable: true }),
    description: new FormControl('', { nonNullable: true }),
    stack_trace: new FormControl('', { nonNullable: true }),
    error_log: new FormControl('', { nonNullable: true }),
    environment: new FormControl('', { nonNullable: true }),
  });

  protected readonly files = signal<Partial<Record<FieldKey, File>>>({});
  protected readonly fieldErrors = signal<Partial<Record<FieldKey, string>>>({});
  protected readonly serverError = signal<string | null>(null);
  protected readonly submitting = signal(false);
  protected readonly result = signal<BugReport | null>(null);

  protected onFileSelected(key: FieldKey, event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = ''; // allow choosing the same file again later
    if (!file) {
      return;
    }
    const error = this.checkFile(file);
    if (error) {
      this.fieldErrors.update((e) => ({ ...e, [key]: error }));
      return;
    }
    this.fieldErrors.update((e) => ({ ...e, [key]: undefined }));
    this.files.update((f) => ({ ...f, [key]: file }));
  }

  protected removeFile(key: FieldKey): void {
    this.files.update((f) => ({ ...f, [key]: undefined }));
  }

  protected formatSize(bytes: number): string {
    if (bytes < 1024) {
      return `${bytes} B`;
    }
    if (bytes < 1024 * 1024) {
      return `${(bytes / 1024).toFixed(1)} KB`;
    }
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  protected submit(): void {
    this.serverError.set(null);
    const value = this.form.getRawValue();
    const files = this.files();

    if (!files.description && !value.description.trim()) {
      this.fieldErrors.update((e) => ({
        ...e,
        description: 'Enter a bug description or upload a file.',
      }));
      return;
    }
    this.fieldErrors.update((e) => ({ ...e, description: undefined }));

    const data = new FormData();
    if (value.title.trim()) data.append('title', value.title.trim());
    if (value.environment.trim()) data.append('environment', value.environment.trim());
    for (const { key } of this.fields) {
      const file = files[key];
      if (file) {
        data.append(`${key}_file`, file, file.name);
      } else if (value[key].trim()) {
        data.append(key, value[key]);
      }
    }

    this.submitting.set(true);
    this.api.submit(data).subscribe({
      next: (report) => {
        this.submitting.set(false);
        this.result.set(report);
      },
      error: (err: HttpErrorResponse) => {
        this.submitting.set(false);
        this.serverError.set(this.describeError(err));
      },
    });
  }

  protected reset(): void {
    this.form.reset();
    this.files.set({});
    this.fieldErrors.set({});
    this.serverError.set(null);
    this.result.set(null);
  }

  private checkFile(file: File): string | null {
    const dot = file.name.lastIndexOf('.');
    const ext = dot >= 0 ? file.name.slice(dot).toLowerCase() : '';
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      return `"${file.name}" is not supported. Use ${this.allowedList}.`;
    }
    if (file.size > MAX_FILE_BYTES) {
      return `"${file.name}" is ${this.formatSize(file.size)}. The limit is ${this.maxMb} MB.`;
    }
    if (file.size === 0) {
      return `"${file.name}" is empty.`;
    }
    return null;
  }

  private describeError(err: HttpErrorResponse): string {
    if (err.status === 0) {
      return 'Cannot reach the server. Check that the backend is running, then try again.';
    }
    const detail = err.error?.detail;
    if (typeof detail === 'string') {
      return detail;
    }
    if (Array.isArray(detail)) {
      return detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join(' ');
    }
    return 'The bug report could not be submitted. Please try again.';
  }
}
