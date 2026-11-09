import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { API_BASE_URL } from './config';

export interface BugReportFile {
  id: number;
  field: 'description' | 'stack_trace' | 'error_log';
  original_filename: string;
  file_type: string;
  size_bytes: number;
}

export interface BugReport {
  id: number;
  title: string | null;
  description: string;
  stack_trace: string | null;
  error_log: string | null;
  environment: string | null;
  input_method: 'paste' | 'upload';
  status: string;
  created_at: string;
  files: BugReportFile[];
}

@Injectable({ providedIn: 'root' })
export class BugReportService {
  private readonly http = inject(HttpClient);

  submit(data: FormData): Observable<BugReport> {
    return this.http.post<BugReport>(`${API_BASE_URL}/api/bug-reports`, data);
  }
}
