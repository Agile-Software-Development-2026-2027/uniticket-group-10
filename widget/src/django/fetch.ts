// Authentication only: AG-UI's HttpAgent handles the protocol.
export function createDjangoFetch(
  csrfToken: string,
  fetchImpl: typeof fetch = (...args) => fetch(...args),
): typeof fetch {
  return async (input, init) => {
    const url = new URL(input instanceof Request ? input.url : String(input), window.location.href);
    if (url.origin !== window.location.origin)
      throw new Error("Expected a same-origin Django endpoint");
    const headers = new Headers(input instanceof Request ? input.headers : undefined);
    new Headers(init?.headers).forEach((value, key) => headers.set(key, value));
    headers.set("X-CSRFToken", csrfToken);
    return fetchImpl(input instanceof Request ? input : url.href, {
      ...init,
      headers,
      credentials: "same-origin",
      redirect: "error",
    });
  };
}
