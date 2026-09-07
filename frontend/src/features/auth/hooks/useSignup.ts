import { useState, useCallback } from 'react';
import { UseFormSetError } from 'react-hook-form';
import { SignupFormValues, AuthenticatedUser } from '../types/auth.types';
import { authApi, AuthApiError } from '../services/authApi';
import { useAuthStore } from '@/lib/authStore';

export interface UseSignupOptions {
  setError: UseFormSetError<SignupFormValues>;
  onSuccess?: (user: AuthenticatedUser) => void;
  onSecurityFailure?: () => void;
  onInvalidQuestion?: () => void;
}

export interface UseSignupResult {
  submitSignup: (values: SignupFormValues) => Promise<boolean>;
  isSubmitting: boolean;
  formError?: string;
  correlationId: string;
  isSuccess: boolean;
}

const SUPPORTED_FIELDS = new Set<keyof SignupFormValues>([
  'firstName',
  'lastName',
  'biEmail',
  'password',
  'confirmPassword',
  'secretQuestionId',
  'secretAnswer',
]);

export function useSignup({
  setError,
  onSuccess,
  onSecurityFailure,
  onInvalidQuestion,
}: UseSignupOptions): UseSignupResult {
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [formError, setFormError] = useState<string | undefined>(undefined);
  const [correlationId, setCorrelationId] = useState<string>(() => crypto.randomUUID());
  const [isSuccess, setIsSuccess] = useState<boolean>(false);
  const setAuthenticatedSession = useAuthStore((state) => state.setAuthenticatedSession);

  const submitSignup = useCallback(
    async (values: SignupFormValues): Promise<boolean> => {
      setIsSubmitting(true);
      setFormError(undefined);
      const currCorrelationId = crypto.randomUUID();
      const idempotencyKey = crypto.randomUUID();
      setCorrelationId(currCorrelationId);

      const requestPayload = {
        firstName: values.firstName.trim(),
        lastName: values.lastName.trim(),
        biEmail: values.biEmail.trim().toLowerCase(),
        password: values.password,
        confirmPassword: values.confirmPassword,
        secretQuestionId: values.secretQuestionId.trim(),
        secretAnswer: values.secretAnswer.trim(),
      };

      try {
        const response = await authApi.signup(requestPayload, currCorrelationId, idempotencyKey);
        setIsSubmitting(false);
        setIsSuccess(true);

        // Store session in authStore
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
          const errorCode = apiError?.code;
          const errorMessage = apiError?.message || 'Registration failed.';

          // Check error codes
          if (errorCode === 'EMAIL_ALREADY_REGISTERED') {
            setError('biEmail', {
              type: 'server',
              message: errorMessage,
            });
          } else if (errorCode === 'INVALID_SECRET_QUESTION') {
            setError('secretQuestionId', {
              type: 'server',
              message: errorMessage,
            });
            if (onInvalidQuestion) {
              onInvalidQuestion();
            }
          } else if (errorCode === 'VALIDATION_ERROR' && apiError?.fieldErrors) {
            for (const fe of apiError.fieldErrors) {
              if (SUPPORTED_FIELDS.has(fe.field as keyof SignupFormValues)) {
                setError(fe.field as keyof SignupFormValues, {
                  type: 'server',
                  message: fe.message,
                });
              }
            }
            setFormError(errorMessage);
          } else {
            setFormError(errorMessage);
          }
        } else {
          setFormError('Network connection error. Please check your network and try again.');
        }

        return false;
      }
    },
    [setError, onSuccess, onSecurityFailure, onInvalidQuestion, setAuthenticatedSession]
  );

  return {
    submitSignup,
    isSubmitting,
    formError,
    correlationId,
    isSuccess,
  };
}
