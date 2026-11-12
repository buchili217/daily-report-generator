import type { Digest, GenerateResult, Me, ReportPayload, SectionKey } from "./types";

const TOKEN_KEY = "dr_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const response = await fetch(`/api${path}`, { ...init, headers });
  if (response.status === 401) {
    clearToken();
    if (window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
    throw new ApiError(401, "登录已过期，请重新登录");
  }
  if (!response.ok) {
    let detail = `请求失败（${response.status}）`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") {
        detail = body.detail;
      }
    } catch {
      // 保留默认错误信息
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export interface LoginResult {
  token: string;
  member_id: number;
  name: string;
}

export function loginWithCode(code: string): Promise<LoginResult> {
  return request<LoginResult>(`/oauth/feishu/callback?code=${encodeURIComponent(code)}`);
}

export interface LoginUrl {
  url: string;
  state: string;
}

export function fetchLoginUrl(): Promise<LoginUrl> {
  return request<LoginUrl>("/oauth/feishu/login-url");
}

export function fetchMe(): Promise<Me> {
  return request<Me>("/me");
}

export function fetchReport(date: string): Promise<ReportPayload> {
  return request<ReportPayload>(`/reports/${date}`);
}

export function generateReport(date: string): Promise<GenerateResult> {
  return request<GenerateResult>(`/reports/${date}/generate`, { method: "POST" });
}

export interface ItemDraft {
  section: SectionKey;
  content: string;
  source_event_ids: number[];
  confidence: number;
  confirmed: boolean;
}

export function saveItems(reportId: number, items: ItemDraft[]): Promise<ReportPayload> {
  return request<ReportPayload>(`/reports/${reportId}/items`, {
    method: "PUT",
    body: JSON.stringify({ items }),
  });
}

export function submitReport(reportId: number): Promise<ReportPayload> {
  return request<ReportPayload>(`/reports/${reportId}/submit`, { method: "POST" });
}

export interface PushResult {
  success: boolean;
  provider_msg_id: string | null;
}

export function pushReport(reportId: number): Promise<PushResult> {
  return request<PushResult>(`/reports/${reportId}/push`, { method: "POST" });
}

export function fetchDigest(teamId: number, date: string): Promise<Digest> {
  return request<Digest>(`/teams/${teamId}/digest?report_date=${date}`);
}

export function fetchHealth(): Promise<{ status: string; mock_mode: boolean }> {
  return request<{ status: string; mock_mode: boolean }>("/health");
}
