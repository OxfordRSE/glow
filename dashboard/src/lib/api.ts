// Can be overridden by setting PUBLIC_API_BASE env var (e.g. http://localhost:8000)
const API_BASE = import.meta.env.PUBLIC_API_BASE ?? "/api";

// Target backend version - update this when making breaking changes to API surface
export const TARGET_BACKEND_VERSION = "0.1.0";

export type VersionCompatibility =
  | "compatible"
  | "minor-mismatch"
  | "major-mismatch"
  | "unknown";

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
        parseError:
          parseError instanceof Error ? parseError.message : String(parseError),
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
      parseError:
        parseError instanceof Error ? parseError.message : String(parseError),
    });

    // Throw a user-friendly error that matches the server error pattern
    throw new Error(
      "The server encountered an error processing your request. The response format was invalid.",
    );
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

export interface VariableMetadata {
  min?: number;
  max?: number;
}

export interface QueryOptions {
  variables: string[];
  waves: string[];
  aggregations: QueryOptionItem[];
  filters: QueryOptionItem[];
  metadata: Record<string, VariableMetadata>;
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
    try {
      const j = (await res.json()) as { detail?: string };
      throw new ApiError(res.status, j.detail ?? res.statusText);
    } catch (parseError) {
      // If JSON parsing fails, throw a generic authentication error
      if (parseError instanceof ApiError) throw parseError;
      throw new ApiError(res.status, "Authentication failed");
    }
  }
  return res.json() as Promise<Token>;
}

export async function getMe(token: string): Promise<User> {
  return apiFetch<User>("/admin/me", { headers: authHeaders(token) });
}

// ─── New /me Endpoint ────────────────────────────────────────────────────────

export interface SchoolSummary {
  id: number;
  name: string;
}

export interface MeAnonymous {
  kind: "anonymous";
}

export interface MeAuthenticated {
  kind: "authenticated";
  id: number;
  username: string;
  is_admin: boolean;
  schools: SchoolSummary[];
}

export type MeResponse = MeAnonymous | MeAuthenticated;

/**
 * Get current user identity (works for both anonymous and authenticated users).
 * Returns anonymous response if no token provided or token is invalid.
 */
export async function me(token?: string): Promise<MeResponse> {
  const options: RequestInit = token ? { headers: authHeaders(token) } : {};
  try {
    return await apiFetch<MeResponse>("/me", options);
  } catch (error) {
    // If authentication fails, return anonymous
    if (
      error instanceof ApiError &&
      (error.status === 401 || error.status === 403)
    ) {
      return { kind: "anonymous" };
    }
    throw error;
  }
}

// ─── New /dimensions Endpoint ────────────────────────────────────────────────

export interface DimensionDefinition {
  key: string;
  type: "string" | "number";
}

export interface VariableDefinition {
  key: string;
  raw_key?: string | null;
  form_id?: string | null;
}

export interface DimensionsResponse {
  school_id?: number;
  variables: VariableDefinition[];
  dimensions: DimensionDefinition[];
}

/**
 * Get available variables and dimensions for querying.
 * - No school_id: returns dataset-level dimensions (public, no auth required)
 * - With school_id: returns school-specific dimensions (requires auth for that school)
 */
export async function getDimensions(params: {
  school_id?: number;
  token?: string;
}): Promise<DimensionsResponse> {
  const { school_id, token } = params;
  const queryParams = school_id ? `?school_id=${school_id}` : "";
  const options: RequestInit = token ? { headers: authHeaders(token) } : {};

  return apiFetch<DimensionsResponse>(`/dimensions${queryParams}`, options);
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
    try {
      const j = (await res.json()) as { detail?: string };
      throw new ApiError(res.status, j.detail ?? res.statusText);
    } catch (parseError) {
      // If JSON parsing fails, throw a generic delete error
      if (parseError instanceof ApiError) throw parseError;
      throw new ApiError(res.status, "Failed to delete user");
    }
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
    try {
      const j = (await res.json()) as { detail?: string };
      throw new ApiError(res.status, j.detail ?? res.statusText);
    } catch (parseError) {
      // If JSON parsing fails, throw a generic delete error
      if (parseError instanceof ApiError) throw parseError;
      throw new ApiError(res.status, "Failed to delete school");
    }
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

// ─── New Period-Based GET /query Endpoint ────────────────────────────────────

export interface CanonicalQuery {
  school_id?: number;
  variables: string[];
  dimensions: string[];
  variable_prefixes: string[];
}

export interface PeriodSliceCell {
  mean?: number;
  n: number;
  [key: string]: unknown; // Dynamic coordinate fields
}

export interface PeriodSlice {
  suppressed: boolean;
  suppression_reason?: "small-n" | "incompatible-version";
  notes?: "values-rescaled"[];
  question_versions?: Record<string, number>;
  cells?: PeriodSliceCell[];
}

export interface VariableSlice {
  variable: string;
  periods: Record<string, PeriodSlice>; // period_id -> PeriodSlice
}

export interface NewQueryResponse {
  query: CanonicalQuery;
  dimensions: string[];
  periods: string[]; // Observed period IDs in chronological order
  variables: VariableSlice[];
}

export interface QueryParams {
  v?: string[]; // Variable names (repeatable)
  d?: string[]; // Dimension names (repeatable)
  variable_prefix?: string[]; // Variable prefixes (repeatable)
  school_id?: number; // Optional school ID for school-scoped query
  token?: string; // Optional token (required for school-scoped queries)
}

/**
 * Execute a new period-oriented multi-variable query.
 *
 * This endpoint supports:
 * - Dataset-scoped queries (no school_id, anonymous access OK)
 * - School-scoped queries (with school_id, requires authorization)
 * - Variable selection via 'v' params or 'variable_prefix' params
 * - Dimension selection via 'd' params
 * - Period-organized results with independent suppression per period
 * - ETag-based caching with If-None-Match support
 */
export async function queryPeriodBased(
  params: QueryParams,
): Promise<NewQueryResponse> {
  const { v = [], d = [], variable_prefix = [], school_id, token } = params;

  // Build query string with repeated parameters
  const queryParts: string[] = [];
  v.forEach((variable) => queryParts.push(`v=${encodeURIComponent(variable)}`));
  d.forEach((dimension) =>
    queryParts.push(`d=${encodeURIComponent(dimension)}`),
  );
  variable_prefix.forEach((prefix) =>
    queryParts.push(`variable_prefix=${encodeURIComponent(prefix)}`),
  );
  if (school_id !== undefined) {
    queryParts.push(`school_id=${school_id}`);
  }

  const queryString = queryParts.length > 0 ? `?${queryParts.join("&")}` : "";
  const options: RequestInit = token ? { headers: authHeaders(token) } : {};

  return apiFetch<NewQueryResponse>(`/query${queryString}`, options);
}
