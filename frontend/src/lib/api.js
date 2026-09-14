const API = import.meta.env.VITE_API_URL || (import.meta.env.PROD ? window.location.origin : 'http://localhost:8000');
export const apiBase = API;

export const token = () => localStorage.getItem('classificaja_token');
export const setToken = (value) => value ? localStorage.setItem('classificaja_token', value) : localStorage.removeItem('classificaja_token');

export async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (token()) headers.set('Authorization', `Bearer ${token()}`);
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  const res = await fetch(`${API}${path}`, { ...options, headers });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || 'Erro na operação');
  return data;
}

export const imageUrl = (url) => url ? (url.startsWith('http') ? url : `${API}${url}`) : null;
