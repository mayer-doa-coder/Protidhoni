export type ApiHealth = {service: string; status: 'ok'; version: string};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

export async function getApiHealth(signal?: AbortSignal): Promise<ApiHealth> {
  const response = await fetch(`${apiBaseUrl}/health`, {signal});
  if (!response.ok) throw new Error(`Backend health check failed (${response.status}).`);
  return response.json() as Promise<ApiHealth>;
}
