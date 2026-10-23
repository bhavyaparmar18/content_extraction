import { create } from 'zustand';
import { AuthenticatedUser, AuthenticationResult } from '@/features/auth/types/auth.types';
import { authApi } from '@/features/auth/services/authApi';

export interface AuthState {
  isAuthenticated: boolean;
  isInitializing: boolean;
  user: AuthenticatedUser | null;
  accessToken: string | null;
  expiresAt: number | null;
  setAuthenticatedSession: (user: AuthenticatedUser, authentication: AuthenticationResult) => void;
  clearSession: () => void;
  initializeAuth: () => Promise<void>;
  /** The silent refresh behind ``initializeAuth``; call that instead. */
  _refreshSession: () => Promise<void>;
  logout: () => Promise<void>;
}

let initialization: Promise<void> | null = null;

export const useAuthStore = create<AuthState>((set, get) => ({
  isAuthenticated: false,
  isInitializing: true,
  user: null,
  accessToken: null,
  expiresAt: null,

  setAuthenticatedSession: (user: AuthenticatedUser, authentication: AuthenticationResult) => {
    const expiresAt = Date.now() + authentication.expiresIn * 1000;
    set({
      isAuthenticated: true,
      isInitializing: false,
      user,
      accessToken: authentication.accessToken,
      expiresAt,
    });
  },

  clearSession: () => {
    set({
      isAuthenticated: false,
      isInitializing: false,
      user: null,
      accessToken: null,
      expiresAt: null,
    });
  },

  initializeAuth: () => {
    // One refresh at a time: the refresh token rotates, so a second concurrent call (React StrictMode runs
    // effects twice in development) would present a used token and sign the reviewer out.
    initialization ??= get()._refreshSession().finally(() => {
      initialization = null;
    });
    return initialization;
  },

  _refreshSession: async () => {
    try {
      // Attempt silent refresh using HttpOnly cookie
      const refreshResponse = await authApi.refresh();
      const accessToken = refreshResponse.data.authentication.accessToken;
      const user = refreshResponse.data.user;

      get().setAuthenticatedSession(user, refreshResponse.data.authentication);
    } catch {
      // No active or valid session, remain unauthenticated
      set({
        isAuthenticated: false,
        isInitializing: false,
        user: null,
        accessToken: null,
        expiresAt: null,
      });
    }
  },

  logout: async () => {
    const token = get().accessToken;
    try {
      await authApi.logout(token || undefined);
    } catch {
      // Best effort logout
    } finally {
      get().clearSession();
    }
  },
}));
