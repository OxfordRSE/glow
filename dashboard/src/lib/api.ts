import { env } from "$env/dynamic/public";

// Can be overridden by setting PUBLIC_API_BASE env var (e.g. http://localhost:8000)
const API_BASE = env.PUBLIC_API_BASE ?? "/api";

// Target backend version - update this when making breaking changes to API surface
export const TARGET_BACKEND_VERSION = "0.1.0";

export type VersionCompatibility = "compatible" | "minor-mismatch" | "major-mismatch" | "unknown";

/**
 * Compare semantic versions and determine compatibility status.
 * - compatible: versions match exactly or differ only in patch
 * - minor-mismatch: minor versions differ (warning)
 * - major-mismatch: major versions differ (error)
 * - unknown: cannot parse version
 */
export function checkVersionCompatibility(
  backendVersion: string,
  targetVersion: string = TARGET_BACKEND_VERSION,
): VersionCompatibility {
  const parseVersion = (v: string): [number, number, number] | null => {
    const match = v.match(/^(\d+)\.(\d+)\.(\d+)/);
    if (!match) return null;
    return [parseInt(match[1]), parseInt(match[2]), parseInt(match[3])];
  };

  const backend = parseVersion(backendVersion);
  const target = parseVersion(targetVersion);

  if (!backend || !target) return "unknown";

  const [bMajor, bMinor] = backend;
  const [tMajor, tMinor] = target;

  if (bMajor !== tMajor) return "major-mismatch";
  if (bMinor !== tMinor) return "minor-mismatch";
  return "compatible";
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public detail?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * Get a user-friendly error message based on the HTTP status code.
 */
function getFriendlyErrorMessage(status: number, detail?: string): string {
  if (status >= 500) {
    return "The server encountered an error. Please try again later or contact support if the problem persists.";
  }
  
  if (status === 400) {
    return detail 
      ? `Your request could not be processed: ${detail}`
      : "Your request could not be processed. Please check your input and try again.";
  }
  
  if (status === 401) {
    return "You are not authenticated. Please log in and try again.";
  }
  
  if (status === 403) {
    return detail 
      ? `Access denied: ${detail}`
      : "You do not have permission to access this resource.";
  }
  
  if (status === 404) {
    return "The requested resource was not found.";
  }
  
  // For other client errors (4xx)
  if (status >= 400 && status < 500) {
    return detail || "There was a problem with your request. Please try again.";
  }
  
  return detail || "An unexpected error occurred. Please try again.";
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, options);
  
  if (!res.ok) {
    // Try to parse JSON error details
    let errorDetail: string | undefined;
    let rawBody: string | undefined;
    
    try {
      const contentType = res.headers.get("content-type");
      if (contentType?.includes("application/json")) {
        rawBody = await res.text();
        const body = JSON.parse(rawBody) as { detail?: string };
        errorDetail = body.detail;
      } else {
        // Non-JSON response
        rawBody = await res.text();
        errorDetail = rawBody;
      }
    } catch (parseError) {
      // JSON parsing failed
      console.error(`Failed to parse error response from ${path}:`, {
        status: res.status,
        statusText: res.statusText,
        rawBody,
        parseError: parseError instanceof Error ? parseError.message : String(parseError),
      });
      
      errorDetail = "The server returned an invalid response.";
    }
    
    const friendlyMessage = getFriendlyErrorMessage(res.status, errorDetail);
    
    // Log detailed error information for debugging
    console.error(`API Error [${res.status}] ${path}:`, {
      status: res.status,
      statusText: res.statusText,
      detail: errorDetail,
      friendlyMessage,
    });
    
    throw new ApiError(res.status, friendlyMessage, errorDetail);
  }
  
  // Parse successful response
  try {
    const data = await res.json();
    return data as T;
  } catch (parseError) {
    console.error(`Failed to parse successful response from ${path}:`, {
      status: res.status,
      parseError: parseError instanceof Error ? parseError.message : String(parseError),
    });
    
    // Throw a user-friendly error that matches the server error pattern
    throw new Error("The server encountered an error processing your request. The response format was invalid.");
  }
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

export interface QueryOptionItem {
  value: string;
  values?: string[];
  scope?: "shared" | "focus_only";
}

export interface QueryOptions {
  variables: string[];
  waves: string[];
  aggregations: QueryOptionItem[];
  filters: QueryOptionItem[];
}

export interface User {
  id: number;
  username: string;
  school_ids: number[];
  school_names: string[];
  is_active: boolean;
  is_admin: boolean;
}

export interface UserCreate {
  username: string;
  password: string;
  school_ids: number[];
  is_admin?: boolean;
}

export interface UserUpdate {
  password?: string;
  school_ids?: number[];
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

// Legacy /data endpoints removed - use query_options from /schools instead

// ─── Queries ─────────────────────────────────────────────────────────────────

// Legacy /query/catalog endpoint removed - use query_options from /schools instead

// ─── Health ───────────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: string;
  version: string;
}

/** Returns the API health status including version info. */
export async function checkHealth(): Promise<HealthResponse | null> {
  try {
    const res = await fetch(`${API_BASE}/health`, {
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) return null;
    return res.json() as Promise<HealthResponse>;
  } catch {
    return null;
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

// ─── Safe Query (with blanket suppression) ──────────────────────────────────

export interface School {
  id: number;
  name: string;
  size: string | null;
  category: string | null;
  geographical_neighbor_ids: number[];
  statistical_neighbor_ids: number[];
  query_options?: QueryOptions;
}

export interface QueryRequest {
  school_id: number;
  variable: string;
  waves: string[];
  aggregations: string[];
  filters: Record<string, (string | number)[]>;
  include_neighbors?: boolean;
  neighbor_type?: "geographical" | "statistical";
}

export interface QueryResultForWave {
  suppressed: boolean;
  suppression_message: string | null;
  results: Record<string, unknown>[] | null;
}

export interface QueryResult {
  school_id: number;
  results: Record<string, QueryResultForWave>;
}

export interface QueryResponse {
  focus_school: QueryResult;
  neighbors: QueryResult[];
  variable: string;
  waves: string[];
  aggregations: string[];
  filters: Record<string, (string | number)[]>;
}

export async function listSchools(token: string): Promise<School[]> {
  return apiFetch<School[]>("/schools", { headers: authHeaders(token) });
}

export async function createSchool(
  token: string,
  data: { name: string; size?: string | null; category?: string | null },
): Promise<School> {
  return apiFetch<School>("//schools", {
    method: "POST",
    headers: { ...authHeaders(token), "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function updateSchool(
  token: string,
  id: number,
  data: {
    name?: string;
    size?: string | null;
    category?: string | null;
    geographical_neighbor_ids?: number[];
    statistical_neighbor_ids?: number[];
  },
): Promise<School> {
  return apiFetch<School>(`//schools/${id}`, {
    method: "PUT",
    headers: { ...authHeaders(token), "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function deleteSchool(token: string, id: number): Promise<void> {
  const res = await fetch(`${API_BASE}//schools/${id}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
  if (!res.ok && res.status !== 204) {
    const j = (await res.json()) as { detail?: string };
    throw new ApiError(res.status, j.detail ?? res.statusText);
  }
}

export async function query(
  token: string,
  request: QueryRequest,
): Promise<QueryResponse> {
  return apiFetch<QueryResponse>("/query", {
    method: "POST",
    headers: { ...authHeaders(token), "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
}
