const INTERNAL_API_BASE =
  process.env.INTERNAL_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://backend:8000";

export async function fetchServerJson<T>(
  path: string,
  fallback: T,
  init?: RequestInit
): Promise<T> {
  try {
    const response = await fetch(`${INTERNAL_API_BASE}${path}`, {
      cache: "no-store",
      ...init,
    });
    if (!response.ok) {
      return fallback;
    }
    return response.json();
  } catch {
    return fallback;
  }
}

export { INTERNAL_API_BASE };
