/**
 * Example-driven MSW handlers.
 * 
 * These handlers use contract examples from the API directory as their single source of truth.
 * This ensures frontend mocks stay in sync with backend contracts.
 */

import { http, HttpResponse, delay } from 'msw'
import { getExample, matchQueryExample, type ContractExample } from './contractExamples'

const API_BASE = '/api'

/**
 * Configuration for selecting which examples to use per endpoint.
 * This can be overridden in stories via the apiResponses parameter.
 */
export interface ApiResponseConfig {
  'POST /auth/login'?: string
  'GET /admin/me'?: string
  'GET /schools'?: string
  'POST /api/query'?: string
}

/**
 * Create MSW handlers from example configuration.
 */
export function createHandlersFromExamples(
  config: ApiResponseConfig = {}
): Array<ReturnType<typeof http.get | typeof http.post>> {
  const handlers: Array<ReturnType<typeof http.get | typeof http.post>> = []
  
  // Login handler
  const loginExampleId = config['POST /auth/login'] || 'auth.login.success'
  const loginExample = getExample(loginExampleId)
  if (loginExample) {
    handlers.push(
      http.post('/auth/login', async () => {
        await delay(300)
        return HttpResponse.json(loginExample.response, { status: loginExample.status })
      })
    )
  }
  
  // Current user handler
  const meExampleId = config['GET /admin/me'] || 'admin.me.user'
  const meExample = getExample(meExampleId)
  if (meExample) {
    handlers.push(
      http.get(`${API_BASE}/admin/me`, async () => {
        await delay(100)
        return HttpResponse.json(meExample.response, { status: meExample.status })
      })
    )
  }
  
  // Schools handler
  const schoolsExampleId = config['GET /schools'] || 'schools.user-default'
  const schoolsExample = getExample(schoolsExampleId)
  if (schoolsExample) {
    handlers.push(
      http.get(`${API_BASE}/schools`, async () => {
        await delay(200)
        return HttpResponse.json(schoolsExample.response, { status: schoolsExample.status })
      })
    )
  }
  
  // Query handler
  const queryExampleId = config['POST /api/query']
  handlers.push(
    http.post(`${API_BASE}/query`, async ({ request }) => {
      await delay(500)
      const body = await request.json()
      const example = matchQueryExample(body, queryExampleId)
      
      if (example) {
        return HttpResponse.json(example.response, { status: example.status })
      }
      
      // Fallback to default
      const fallback = getExample('query.default')
      return HttpResponse.json(fallback?.response || {}, { status: fallback?.status || 200 })
    })
  )
  
  return handlers
}

/**
 * Default handlers using the standard "happy path" examples.
 */
export const handlers = createHandlersFromExamples()

/**
 * Behavior-only handlers for edge cases that can't be represented as static examples.
 */
export const behaviorHandlers = {
  /**
   * Handler that never resolves (for testing loading states).
   */
  loading: http.post(`${API_BASE}/query`, async () => {
    await delay('infinite')
    return HttpResponse.json({})
  }),
  
  /**
   * Handler that returns malformed JSON (for testing error handling).
   */
  malformedJson: http.post(`${API_BASE}/query`, async () => {
    await delay(300)
    return new HttpResponse('not valid json{', {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }),
}
