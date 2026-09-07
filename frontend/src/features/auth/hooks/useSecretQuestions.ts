import { useState, useEffect, useCallback, useRef } from 'react';
import { SecretQuestion } from '../types/auth.types';
import { authApi, AuthApiError } from '../services/authApi';

export interface UseSecretQuestionsResult {
  questions: SecretQuestion[];
  isLoading: boolean;
  isError: boolean;
  isEmpty: boolean;
  errorMessage?: string;
  correlationId?: string;
  reload: () => void;
}

export function useSecretQuestions(): UseSecretQuestionsResult {
  const [questions, setQuestions] = useState<SecretQuestion[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isError, setIsError] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | undefined>(undefined);
  const [correlationId, setCorrelationId] = useState<string>(() => crypto.randomUUID());
  const abortControllerRef = useRef<AbortController | null>(null);

  const fetchQuestions = useCallback(async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    const currCorrelationId = crypto.randomUUID();
    setCorrelationId(currCorrelationId);
    setIsLoading(true);
    setIsError(false);
    setErrorMessage(undefined);

    try {
      const response = await authApi.getSecretQuestions(currCorrelationId, controller.signal);
      const items = response?.data?.items || [];
      setQuestions(items);
      setIsLoading(false);
    } catch (err: any) {
      if (err.name === 'AbortError') return;
      setIsError(true);
      setIsLoading(false);
      if (err instanceof AuthApiError) {
        setErrorMessage(err.data?.error?.message || 'Secret questions are temporarily unavailable.');
      } else {
        setErrorMessage('Unable to load secret questions. Please check your connection.');
      }
    }
  }, []);

  useEffect(() => {
    fetchQuestions();
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [fetchQuestions]);

  const isEmpty = !isLoading && !isError && questions.length === 0;

  return {
    questions,
    isLoading,
    isError,
    isEmpty,
    errorMessage,
    correlationId,
    reload: fetchQuestions,
  };
}
