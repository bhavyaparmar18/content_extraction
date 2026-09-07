/**
 * Unified API client with automatic Bearer token injection,
 * single-flight token refresh on 401, and request retry guard.
 */

import { useAuthStore } from './authStore';
import { authApi } from '@/features/auth/services/authApi';

let refreshPromise: Promise<string | null> | null = null;

async function performRefresh(): Promise<string | null> {
  if (refreshPromise) {
    return refreshPromise;
  }

  refreshPromise = (async () => {
    try {
      const response = await authApi.refresh();
      const newAccessToken = response.data.authentication.accessToken;
      const user = response.data.user;

      useAuthStore.getState().setAuthenticatedSession(user, response.data.authentication);
      return newAccessToken;
    } catch {
      useAuthStore.getState().clearSession();
      return null;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

export interface ApiClientOptions extends RequestInit {
  skipAuth?: boolean;
}

export async function apiClient<T>(
  url: string,
  options: ApiClientOptions = {}
): Promise<T> {
  const { skipAuth = false, headers: customHeaders, ...restOptions } = options;
  const headers = new Headers(customHeaders || {});
  headers.set('Accept', 'application/json');

  const { accessToken } = useAuthStore.getState();
  if (!skipAuth && accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`);
  }

  const response = await fetch(url, {
    ...restOptions,
    headers,
    credentials: 'include',
  });

  // Handle 401 and attempt one-time refresh retry
  if (response.status === 401 && !skipAuth) {
    const newAccessToken = await performRefresh();

    if (newAccessToken) {
      headers.set('Authorization', `Bearer ${newAccessToken}`);
      const retryResponse = await fetch(url, {
        ...restOptions,
        headers,
        credentials: 'include',
      });

      if (!retryResponse.ok) {
        let errData: any;
        try {
          errData = await retryResponse.json();
        } catch {
          errData = { message: retryResponse.statusText };
        }
        throw errData;
      }

      return (await retryResponse.json()) as T;
    } else {
      // Refresh failed, session was cleared
      let errData: any;
      try {
        errData = await response.json();
      } catch {
        errData = { message: 'Authentication required' };
      }
      throw errData;
    }
  }

  if (!response.ok) {
    let errData: any;
    try {
      errData = await response.json();
    } catch {
      errData = { message: response.statusText };
    }
    throw errData;
  }

  return (await response.json()) as T;
}
