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
  logout: () => Promise<void>;
}

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

  initializeAuth: async () => {
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
