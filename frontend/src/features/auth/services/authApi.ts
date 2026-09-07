import {
  SecretQuestionsResponse,
  SignupRequest,
  SignupSuccessResponse,
  LoginFormValues,
  LoginResponse,
  CurrentUserResponse,
  ApiErrorResponse,
} from '../types/auth.types';

export class AuthApiError extends Error {
  status: number;
  data: ApiErrorResponse;

  constructor(status: number, data: ApiErrorResponse) {
    super(data?.error?.message || `HTTP ${status}`);
    this.name = 'AuthApiError';
    this.status = status;
    this.data = data;
  }
}

async function authRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers || {});
  headers.set('Accept', 'application/json');

  const res = await fetch(path, {
    ...init,
    headers,
    credentials: 'include', // Ensure cookies are sent and received
  });

  let data: any;
  try {
    data = await res.json();
  } catch {
    data = {
      success: false,
      error: {
        code: 'NETWORK_ERROR',
        message: `HTTP ${res.status}: ${res.statusText}`,
      },
      meta: { correlationId: '' },
    };
  }

  if (!res.ok) {
    throw new AuthApiError(res.status, data as ApiErrorResponse);
  }

  return data as T;
}

export const authApi = {
  getSecretQuestions(correlationId: string, signal?: AbortSignal): Promise<SecretQuestionsResponse> {
    return authRequest<SecretQuestionsResponse>('/api/v1/auth/secret-questions', {
      method: 'GET',
      signal,
      headers: {
        'X-Correlation-ID': correlationId,
      },
    });
  },

  signup(
    request: SignupRequest,
    correlationId: string,
    idempotencyKey: string,
    signal?: AbortSignal
  ): Promise<SignupSuccessResponse> {
    return authRequest<SignupSuccessResponse>('/api/v1/auth/signup', {
      method: 'POST',
      signal,
      headers: {
        'Content-Type': 'application/json',
        'X-Correlation-ID': correlationId,
        'Idempotency-Key': idempotencyKey,
      },
      body: JSON.stringify(request),
    });
  },

  login(
    payload: LoginFormValues,
    correlationId?: string,
    signal?: AbortSignal
  ): Promise<LoginResponse> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (correlationId) {
      headers['X-Correlation-ID'] = correlationId;
    }

    return authRequest<LoginResponse>('/api/v1/auth/login', {
      method: 'POST',
      signal,
      headers,
      body: JSON.stringify(payload),
    });
  },

  refresh(correlationId?: string, signal?: AbortSignal): Promise<LoginResponse> {
    const headers: Record<string, string> = {};
    if (correlationId) {
      headers['X-Correlation-ID'] = correlationId;
    }

    return authRequest<LoginResponse>('/api/v1/auth/refresh', {
      method: 'POST',
      signal,
      headers,
    });
  },

  getMe(
    accessToken: string,
    correlationId?: string,
    signal?: AbortSignal
  ): Promise<CurrentUserResponse> {
    const headers: Record<string, string> = {
      Authorization: `Bearer ${accessToken}`,
    };
    if (correlationId) {
      headers['X-Correlation-ID'] = correlationId;
    }

    return authRequest<CurrentUserResponse>('/api/v1/auth/me', {
      method: 'GET',
      signal,
      headers,
    });
  },

  async logout(accessToken?: string, correlationId?: string, signal?: AbortSignal): Promise<void> {
    const headers: Record<string, string> = {};
    if (accessToken) {
      headers['Authorization'] = `Bearer ${accessToken}`;
    }
    if (correlationId) {
      headers['X-Correlation-ID'] = correlationId;
    }

    await fetch('/api/v1/auth/logout', {
      method: 'POST',
      signal,
      headers,
      credentials: 'include',
    });
  },
};
