const PUBLIC_API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

export async function fetchClientJson<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  const response = await fetch(`${PUBLIC_API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `API Error: ${response.status}`);
  }
  return response.json();
}
