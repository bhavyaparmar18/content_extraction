export type UserRole = 'ADMIN' | 'POWER_USER' | 'REGULAR_USER';

export interface SignupFormValues {
  firstName: string;
  lastName: string;
  biEmail: string;
  password: string;
  confirmPassword: string;
  secretQuestionId: string;
  secretAnswer: string;
}

export type SignupRequest = SignupFormValues;

export interface LoginFormValues {
  biEmail: string;
  password: string;
  rememberMe: boolean;
}

export type LoginRequest = LoginFormValues;

export interface SecretQuestion {
  questionId: string;
  questionText: string;
}

export interface ApiMeta {
  correlationId: string;
}

export interface SecretQuestionsResponse {
  success: true;
  data: {
    items: SecretQuestion[];
  };
  meta: ApiMeta;
}

export interface AuthenticatedUser {
  userId: string;
  firstName: string;
  lastName: string;
  biEmail: string;
  role: UserRole;
  status?: 'PENDING_VERIFICATION' | 'ACTIVE' | 'LOCKED' | 'DISABLED';
  emailVerified?: boolean;
}

export interface AuthenticationResult {
  accessToken: string;
  tokenType: 'Bearer';
  expiresIn: number;
}

export interface SignupSuccessResponse {
  success: true;
  message: string;
  data: {
    user: AuthenticatedUser;
    authentication: AuthenticationResult;
  };
  meta: ApiMeta;
}

export interface LoginResponse {
  success: true;
  data: {
    user: AuthenticatedUser;
    authentication: AuthenticationResult;
  };
  meta: ApiMeta;
}

export interface CurrentUserResponse {
  success: true;
  data: AuthenticatedUser;
  meta?: ApiMeta;
}

export interface ApiFieldError {
  field: string;
  code: string;
  message: string;
}

export interface ApiErrorResponse {
  success: false;
  error: {
    code: string;
    message: string;
    fieldErrors?: ApiFieldError[];
  };
  meta?: ApiMeta;
}

export interface AuthState {
  user: AuthenticatedUser | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  isInitializing: boolean;
}
