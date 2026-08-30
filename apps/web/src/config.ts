export const API_BASE =
  ((import.meta as any).env?.VITE_API_URL as string) ||
  (typeof window !== 'undefined' &&
  (window.location.hostname.includes('vercel.app') ||
    window.location.hostname.includes('github.dev') ||
    window.location.hostname.includes('hf.space'))
    ? 'https://ufns-backend.centralindia.cloudapp.azure.com'
    : '');

export function apiUrl(endpoint: string): string {
  if (endpoint.startsWith('http://') || endpoint.startsWith('https://')) {
    return endpoint;
  }
  const cleanPath = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  return `${API_BASE}${cleanPath}`;
}
