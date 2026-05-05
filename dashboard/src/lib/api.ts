import { env } from "$env/dynamic/public";

// Can be overridden by setting PUBLIC_API_BASE env var (e.g. http://localhost:8000)
const API_BASE = env.PUBLIC_API_BASE ?? "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    // The API always returns JSON error details; let any parse error propagate naturally
    const body = (await res.json()) as { detail?: string };
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` };
}

// ─── Types ───────────────────────────────────────────────────────────────────

export interface Token {
  access_token: string;
  token_type: string;
}

export interface QueryFilter {
  column: string;
  op: "eq" | "ne" | "in" | "gt" | "lt" | "gte" | "lte";
  value: string | number | (string | number)[];
}

export interface QueryResult {
  csv: string;
  count_csv: string;
  suppressions: Record<string, Record<number, string>>;
  provenance: string[];
}

export interface QueryCatalog {
  dimensions: string[];
  measures: string[];
  scores: string[];
  waves: string[];
  value_suggestions: Record<string, string[]>;
  step_types: string[];
}

export type QueryMetricKind = "count_students" | "mean";

export interface QueryMetric {
  kind: QueryMetricKind;
  column?: string;
  as_column?: string;
}

export interface QueryFilterStep {
  type: "filter";
  column: string;
  op: QueryFilter["op"];
  value: QueryFilter["value"];
}

export interface QueryDeriveScoreStep {
  type: "derive_score";
  score: "phq9_total";
}

export interface QueryPairWavesStep {
  type: "pair_waves";
  from_wave: string;
  to_wave: string;
  measures: string[];
}

export interface QueryBucketBand {
  label: string;
  min_students: number;
  max_students?: number;
}

export interface QueryBucketSchoolSizeStep {
  type: "bucket_school_size";
  output_column: string;
  bands: QueryBucketBand[];
}

export interface QueryAggregateStep {
  type: "aggregate";
  group_by: string[];
  metrics: QueryMetric[];
}

export type QueryStep =
  | QueryFilterStep
  | QueryDeriveScoreStep
  | QueryPairWavesStep
  | QueryBucketSchoolSizeStep
  | QueryAggregateStep;

export interface QueryPlan {
  steps: QueryStep[];
}

export interface UserScope {
  filters: Record<string, string[]>;
}

export interface User {
  id: number;
  username: string;
  scope: UserScope;
  is_active: boolean;
  is_admin: boolean;
  student_count: number | null;
}

export interface UserCreate {
  username: string;
  password: string;
  scope?: UserScope;
  is_admin?: boolean;
}

export interface UserUpdate {
  password?: string;
  scope?: UserScope;
  is_active?: boolean;
  is_admin?: boolean;
}

// ─── Auth ────────────────────────────────────────────────────────────────────

export async function login(
  username: string,
  password: string,
): Promise<Token> {
  const body = new URLSearchParams({ username, password });
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
  if (!res.ok) {
    const j = (await res.json()) as { detail?: string };
    throw new ApiError(res.status, j.detail ?? res.statusText);
  }
  return res.json() as Promise<Token>;
}

export async function getMe(token: string): Promise<User> {
  return apiFetch<User>("/admin/me", { headers: authHeaders(token) });
}

// ─── Data ────────────────────────────────────────────────────────────────────

export async function getColumns(token: string): Promise<string[]> {
  return apiFetch<string[]>("/data/columns", { headers: authHeaders(token) });
}

// ─── Queries ─────────────────────────────────────────────────────────────────

export async function getQueryCatalog(token: string): Promise<QueryCatalog> {
  return apiFetch<QueryCatalog>("/query/catalog", {
    headers: authHeaders(token),
  });
}

export async function query(
  token: string,
  plan: QueryPlan,
): Promise<QueryResult> {
  return apiFetch<QueryResult>("/query", {
    method: "POST",
    headers: { ...authHeaders(token), "Content-Type": "application/json" },
    body: JSON.stringify(plan),
  });
}

// ─── Health ───────────────────────────────────────────────────────────────────

/** Returns true if the API is reachable and healthy. */
export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/health`, {
      signal: AbortSignal.timeout(5000),
    });
    return res.ok;
  } catch {
    return false;
  }
}

// ─── Admin ───────────────────────────────────────────────────────────────────

export async function listUsers(token: string): Promise<User[]> {
  return apiFetch<User[]>("/admin/users", { headers: authHeaders(token) });
}

export async function createUser(
  token: string,
  data: UserCreate,
): Promise<User> {
  return apiFetch<User>("/admin/users", {
    method: "POST",
    headers: { ...authHeaders(token), "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function updateUser(
  token: string,
  id: number,
  data: UserUpdate,
): Promise<User> {
  return apiFetch<User>(`/admin/users/${id}`, {
    method: "PUT",
    headers: { ...authHeaders(token), "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function deleteUser(token: string, id: number): Promise<void> {
  const res = await fetch(`${API_BASE}/admin/users/${id}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
  if (!res.ok && res.status !== 204) {
    const j = (await res.json()) as { detail?: string };
    throw new ApiError(res.status, j.detail ?? res.statusText);
  }
}
