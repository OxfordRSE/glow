import type { HandleClientError } from "@sveltejs/kit";

export const handleError: HandleClientError = ({ error, event, status, message }) => {
  // Log errors to console for debugging
  console.error("Unhandled client error:", {
    error,
    status,
    message,
    url: event.url.toString(),
  });

  // Return a user-friendly error message
  return {
    message: message || "An unexpected error occurred. Please try again.",
  };
};
