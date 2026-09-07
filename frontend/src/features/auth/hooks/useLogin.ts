import { useState, useCallback } from 'react';
import { UseFormSetError } from 'react-hook-form';
import { LoginFormValues, AuthenticatedUser } from '../types/auth.types';
import { authApi, AuthApiError } from '../services/authApi';
import { useAuthStore } from '@/lib/authStore';

export interface UseLoginOptions {
  setError: UseFormSetError<LoginFormValues>;
  onSuccess?: (user: AuthenticatedUser) => void;
  onSecurityFailure?: () => void;
}

export interface UseLoginResult {
  submitLogin: (values: LoginFormValues) => Promise<boolean>;
  isSubmitting: boolean;
  formError?: string;
  errorCode?: string;
  correlationId: string;
  isSuccess: boolean;
}

export function useLogin({
  setError,
  onSuccess,
  onSecurityFailure,
}: UseLoginOptions): UseLoginResult {
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [formError, setFormError] = useState<string | undefined>(undefined);
  const [errorCode, setErrorCode] = useState<string | undefined>(undefined);
  const [correlationId, setCorrelationId] = useState<string>(() => crypto.randomUUID());
  const [isSuccess, setIsSuccess] = useState<boolean>(false);
  const setAuthenticatedSession = useAuthStore((state) => state.setAuthenticatedSession);

  const submitLogin = useCallback(
    async (values: LoginFormValues): Promise<boolean> => {
      setIsSubmitting(true);
      setFormError(undefined);
      setErrorCode(undefined);
      const currCorrelationId = crypto.randomUUID();
      setCorrelationId(currCorrelationId);

      // Section 15: Trim and lowercase email; do not trim or modify password
      const payload: LoginFormValues = {
        biEmail: values.biEmail.trim().toLowerCase(),
        password: values.password,
        rememberMe: values.rememberMe ?? false,
      };

      try {
        const response = await authApi.login(payload, currCorrelationId);
        setIsSubmitting(false);
        setIsSuccess(true);

        // Store access token and user in zustand store
        setAuthenticatedSession(response.data.user, response.data.authentication);

        if (onSuccess) {
          onSuccess(response.data.user);
        }
        return true;
      } catch (err: any) {
        setIsSubmitting(false);

        if (onSecurityFailure) {
          onSecurityFailure();
        }

        if (err instanceof AuthApiError) {
          const apiError = err.data?.error;
          const code = apiError?.code || 'INVALID_CREDENTIALS';
          const message = apiError?.message || 'Authentication failed. Please check your credentials.';

          setErrorCode(code);
          if (err.data?.meta?.correlationId) {
            setCorrelationId(err.data.meta.correlationId);
          }

          if (code === 'VALIDATION_ERROR' && apiError?.fieldErrors) {
            for (const fe of apiError.fieldErrors) {
              if (fe.field === 'biEmail' || fe.field === 'password') {
                setError(fe.field, {
                  type: 'server',
                  message: fe.message,
                });
              }
            }
            setFormError('Please correct the highlighted errors.');
          } else {
            setFormError(message);
          }
        } else {
          setErrorCode('NETWORK_ERROR');
          setFormError('Unable to connect to the authentication service. Please try again.');
        }

        return false;
      }
    },
    [setError, onSuccess, onSecurityFailure, setAuthenticatedSession]
  );

  return {
    submitLogin,
    isSubmitting,
    formError,
    errorCode,
    correlationId,
    isSuccess,
  };
}
