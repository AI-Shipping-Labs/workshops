/**
 * Creates a JSON response with standard CORS headers.
 * Used by route handlers in `app.ts`.
 */
export function jsonResponse(body: unknown, status = 200): Response {
  return Response.json(body, {
    status,
    headers: corsHeaders(),
  });
}

/**
 * Creates an HTML response with standard CORS headers.
 * Used by `app.ts` to serve the browser UI.
 */
export function htmlResponse(body: string): Response {
  return new Response(body, {
    headers: {
      "content-type": "text/html; charset=utf-8",
      ...corsHeaders(),
    },
  });
}

/**
 * Creates the CORS preflight response.
 * Used by the Worker `fetch` entrypoint for OPTIONS requests.
 */
export function emptyCorsResponse(): Response {
  return new Response(null, {
    status: 204,
    headers: corsHeaders(),
  });
}

/**
 * Defines the shared CORS policy for this demo API.
 * Used by all response helpers in this module.
 */
export function corsHeaders(): HeadersInit {
  return {
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "GET,POST,OPTIONS",
    "access-control-allow-headers": "content-type,authorization",
  };
}

/**
 * Error type for expected HTTP failures.
 * Thrown by parsers/adapters and converted to responses by `app.ts`.
 */
export class HttpError extends Error {
  /**
   * Attaches an HTTP status to an expected application error.
   * Used by request parsers and Cloudflare adapters before `app.ts` serializes it.
   */
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}
