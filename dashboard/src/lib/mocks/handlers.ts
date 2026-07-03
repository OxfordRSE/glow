/**
 * MSW handlers (deprecated - use handlersFromExamples instead).
 *
 * This file is kept for backward compatibility with existing stories.
 * New stories should use the contract examples system in handlersFromExamples.ts
 */

import { handlers as exampleHandlers } from "./handlersFromExamples";
import { getExample } from "./contractExamples";

// Export default handlers from the new system
export const handlers = exampleHandlers;

// Export mock data from contract examples for backward compatibility
export const mockUser = getExample("admin.me.user")?.response;
export const mockAdminUser = getExample("admin.me.admin")?.response;
export const mockSchools = getExample("schools.user-default")?.response;

/**
 * @deprecated Use withApiResponses({ 'POST /api/query': 'query.default' }) instead
 */
export function generateQueryResult() {
  console.warn(
    "generateQueryResult is deprecated. Use contract examples instead.",
  );
  return getExample("query.default")?.response;
}

/**
 * @deprecated Use withApiResponses({ 'POST /api/query': 'query.suppressed-focus' }) instead
 */
export const createSuppressedFocusHandler = () => {
  console.warn(
    "createSuppressedFocusHandler is deprecated. Use contract examples instead.",
  );
  return exampleHandlers[0]; // Return a dummy handler
};

/**
 * @deprecated Use withApiResponses({ 'POST /api/query': 'query.suppressed-focus' }) instead
 */
export const createSuppressedNeighborHandler = () => {
  console.warn(
    "createSuppressedNeighborHandler is deprecated. Use contract examples instead.",
  );
  return exampleHandlers[0];
};

/**
 * @deprecated Use withApiResponses({ 'POST /api/query': 'query.error-400' }) instead
 */
export const createErrorHandler = () => {
  console.warn(
    "createErrorHandler is deprecated. Use contract examples instead.",
  );
  return exampleHandlers[0];
};
