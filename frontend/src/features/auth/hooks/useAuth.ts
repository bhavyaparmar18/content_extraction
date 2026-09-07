import { useAuthStore } from '@/lib/authStore';
import { UserRole } from '../types/auth.types';

export const landingRouteByRole: Record<UserRole, string> = {
  ADMIN: '/',
  POWER_USER: '/',
  REGULAR_USER: '/',
};

export function useAuth() {
  const user = useAuthStore((state) => state.user);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const isInitializing = useAuthStore((state) => state.isInitializing);
  const logout = useAuthStore((state) => state.logout);

  const role = user?.role;
  const landingRoute = role ? landingRouteByRole[role] || '/' : '/';

  return {
    user,
    isAuthenticated,
    isInitializing,
    role,
    landingRoute,
    logout,
  };
}
