import React, { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import {
  Eye,
  EyeOff,
  AlertCircle,
  Loader2,
  RefreshCw,
  CheckCircle2,
  ShieldCheck,
} from 'lucide-react';
import { clsx } from 'clsx';
import { signupSchema, SignupSchemaType } from '@/features/auth/schemas/signupSchema';
import { SignupFormValues } from '@/features/auth/types/auth.types';
import { useSecretQuestions } from '@/features/auth/hooks/useSecretQuestions';
import { useSignup } from '@/features/auth/hooks/useSignup';

interface SignupFormProps {
  onSuccess?: () => void;
}

export const SignupForm: React.FC<SignupFormProps> = ({ onSuccess }) => {
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [showSecretAnswer, setShowSecretAnswer] = useState(false);

  const {
    register,
    handleSubmit,
    setError,
    resetField,
    formState: { errors },
  } = useForm<SignupFormValues>({
    resolver: zodResolver(signupSchema),
    mode: 'onTouched',
    defaultValues: {
      firstName: '',
      lastName: '',
      biEmail: '',
      password: '',
      confirmPassword: '',
      secretQuestionId: '',
      secretAnswer: '',
    },
  });

  const secretQuestions = useSecretQuestions();

  const { submitSignup, isSubmitting, formError, correlationId, isSuccess } = useSignup({
    setError,
    onSuccess: () => {
      if (onSuccess) {
        onSuccess();
      }
    },
    onSecurityFailure: () => {
      resetField('password');
      resetField('confirmPassword');
      resetField('secretAnswer');
    },
    onInvalidQuestion: () => {
      secretQuestions.reload();
    },
  });

  const onSubmit = async (values: SignupFormValues) => {
    await submitSignup(values);
  };

  const isFormDisabled =
    isSubmitting ||
    secretQuestions.isLoading ||
    secretQuestions.isError ||
    secretQuestions.isEmpty;

  if (isSuccess) {
    return (
      <div
        className="rounded-xl border border-emerald-200 bg-emerald-50/70 p-6 text-center shadow-sm"
        role="alert"
      >
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 mb-3">
          <CheckCircle2 className="h-6 w-6" />
        </div>
        <h3 className="text-lg font-semibold text-emerald-950">Registration Complete!</h3>
        <p className="mt-1 text-sm text-emerald-700">
          Your account has been created. Redirecting to your workspace...
        </p>
      </div>
    );
  }

  return (
    <form noValidate onSubmit={handleSubmit(onSubmit)} className="space-y-5" aria-label="Sign up form">
      {/* Form Level Error Alert */}
      {formError && (
        <div
          role="alert"
          aria-live="polite"
          className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800"
        >
          <AlertCircle className="h-5 w-5 flex-shrink-0 text-red-600 mt-0.5" />
          <div className="flex-1">
            <p className="font-medium">{formError}</p>
            {correlationId && (
              <p className="mt-1 text-xs text-red-500 font-mono">
                Support ID: {correlationId}
              </p>
            )}
          </div>
        </div>
      )}

      {/* Name Grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {/* First Name */}
        <div>
          <label htmlFor="firstName" className="block text-sm font-medium text-slate-700">
            First Name <span className="text-red-500">*</span>
          </label>
          <div className="mt-1">
            <input
              id="firstName"
              type="text"
              autoComplete="given-name"
              disabled={isSubmitting}
              aria-invalid={errors.firstName ? 'true' : 'false'}
              aria-describedby={errors.firstName ? 'firstName-error' : undefined}
              className={clsx(
                'block w-full rounded-lg border px-3.5 py-2.5 text-sm shadow-sm transition placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-offset-1',
                errors.firstName
                  ? 'border-red-300 bg-red-50/30 text-red-900 focus:border-red-500 focus:ring-red-500'
                  : 'border-slate-300 bg-white text-slate-900 focus:border-blue-600 focus:ring-blue-600'
              )}
              placeholder="e.g. John"
              {...register('firstName')}
            />
          </div>
          {errors.firstName && (
            <p id="firstName-error" className="mt-1.5 text-xs text-red-600">
              {errors.firstName.message}
            </p>
          )}
        </div>

        {/* Last Name */}
        <div>
          <label htmlFor="lastName" className="block text-sm font-medium text-slate-700">
            Last Name <span className="text-red-500">*</span>
          </label>
          <div className="mt-1">
            <input
              id="lastName"
              type="text"
              autoComplete="family-name"
              disabled={isSubmitting}
              aria-invalid={errors.lastName ? 'true' : 'false'}
              aria-describedby={errors.lastName ? 'lastName-error' : undefined}
              className={clsx(
                'block w-full rounded-lg border px-3.5 py-2.5 text-sm shadow-sm transition placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-offset-1',
                errors.lastName
                  ? 'border-red-300 bg-red-50/30 text-red-900 focus:border-red-500 focus:ring-red-500'
                  : 'border-slate-300 bg-white text-slate-900 focus:border-blue-600 focus:ring-blue-600'
              )}
              placeholder="e.g. Doe"
              {...register('lastName')}
            />
          </div>
          {errors.lastName && (
            <p id="lastName-error" className="mt-1.5 text-xs text-red-600">
              {errors.lastName.message}
            </p>
          )}
        </div>
      </div>

      {/* BI Email */}
      <div>
        <label htmlFor="biEmail" className="block text-sm font-medium text-slate-700">
          BI Email <span className="text-red-500">*</span>
        </label>
        <div className="mt-1">
          <input
            id="biEmail"
            type="email"
            autoComplete="email"
            disabled={isSubmitting}
            aria-invalid={errors.biEmail ? 'true' : 'false'}
            aria-describedby={errors.biEmail ? 'biEmail-error' : undefined}
            className={clsx(
              'block w-full rounded-lg border px-3.5 py-2.5 text-sm shadow-sm transition placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-offset-1',
              errors.biEmail
                ? 'border-red-300 bg-red-50/30 text-red-900 focus:border-red-500 focus:ring-red-500'
                : 'border-slate-300 bg-white text-slate-900 focus:border-blue-600 focus:ring-blue-600'
            )}
            placeholder="john.doe@company.com"
            {...register('biEmail')}
          />
        </div>
        {errors.biEmail && (
          <p id="biEmail-error" className="mt-1.5 text-xs text-red-600">
            {errors.biEmail.message}
          </p>
        )}
      </div>

      {/* Password */}
      <div>
        <label htmlFor="password" className="block text-sm font-medium text-slate-700">
          Password <span className="text-red-500">*</span>
        </label>
        <div className="relative mt-1">
          <input
            id="password"
            type={showPassword ? 'text' : 'password'}
            autoComplete="new-password"
            disabled={isSubmitting}
            aria-invalid={errors.password ? 'true' : 'false'}
            aria-describedby={errors.password ? 'password-error' : 'password-hint'}
            className={clsx(
              'block w-full rounded-lg border px-3.5 py-2.5 pr-10 text-sm shadow-sm transition placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-offset-1',
              errors.password
                ? 'border-red-300 bg-red-50/30 text-red-900 focus:border-red-500 focus:ring-red-500'
                : 'border-slate-300 bg-white text-slate-900 focus:border-blue-600 focus:ring-blue-600'
            )}
            placeholder="At least 12 characters"
            {...register('password')}
          />
          <button
            type="button"
            onClick={() => setShowPassword((prev) => !prev)}
            className="absolute inset-y-0 right-0 flex items-center pr-3 text-slate-400 hover:text-slate-600 focus:outline-none focus:text-blue-600"
            aria-label={showPassword ? 'Hide password' : 'Show password'}
            tabIndex={0}
          >
            {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>
        {errors.password ? (
          <p id="password-error" className="mt-1.5 text-xs text-red-600">
            {errors.password.message}
          </p>
        ) : (
          <p id="password-hint" className="mt-1 text-xs text-slate-500">
            Must contain at least 12 characters and not match your email.
          </p>
        )}
      </div>

      {/* Confirm Password */}
      <div>
        <label htmlFor="confirmPassword" className="block text-sm font-medium text-slate-700">
          Confirm Password <span className="text-red-500">*</span>
        </label>
        <div className="relative mt-1">
          <input
            id="confirmPassword"
            type={showConfirmPassword ? 'text' : 'password'}
            autoComplete="new-password"
            disabled={isSubmitting}
            aria-invalid={errors.confirmPassword ? 'true' : 'false'}
            aria-describedby={errors.confirmPassword ? 'confirmPassword-error' : undefined}
            className={clsx(
              'block w-full rounded-lg border px-3.5 py-2.5 pr-10 text-sm shadow-sm transition placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-offset-1',
              errors.confirmPassword
                ? 'border-red-300 bg-red-50/30 text-red-900 focus:border-red-500 focus:ring-red-500'
                : 'border-slate-300 bg-white text-slate-900 focus:border-blue-600 focus:ring-blue-600'
            )}
            placeholder="Re-enter password"
            {...register('confirmPassword')}
          />
          <button
            type="button"
            onClick={() => setShowConfirmPassword((prev) => !prev)}
            className="absolute inset-y-0 right-0 flex items-center pr-3 text-slate-400 hover:text-slate-600 focus:outline-none focus:text-blue-600"
            aria-label={showConfirmPassword ? 'Hide confirm password' : 'Show confirm password'}
            tabIndex={0}
          >
            {showConfirmPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>
        {errors.confirmPassword && (
          <p id="confirmPassword-error" className="mt-1.5 text-xs text-red-600">
            {errors.confirmPassword.message}
          </p>
        )}
      </div>

      {/* Secret Question */}
      <div>
        <div className="flex items-center justify-between">
          <label htmlFor="secretQuestionId" className="block text-sm font-medium text-slate-700">
            Security Question <span className="text-red-500">*</span>
          </label>
          {secretQuestions.isError && (
            <button
              type="button"
              onClick={secretQuestions.reload}
              className="inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800"
            >
              <RefreshCw className="h-3 w-3" /> Retry loading
            </button>
          )}
        </div>
        <div className="mt-1">
          <select
            id="secretQuestionId"
            disabled={isSubmitting || secretQuestions.isLoading || secretQuestions.isError}
            aria-invalid={errors.secretQuestionId ? 'true' : 'false'}
            aria-describedby={errors.secretQuestionId ? 'secretQuestionId-error' : undefined}
            className={clsx(
              'block w-full rounded-lg border px-3.5 py-2.5 text-sm shadow-sm transition focus:outline-none focus:ring-2 focus:ring-offset-1',
              errors.secretQuestionId
                ? 'border-red-300 bg-red-50/30 text-red-900 focus:border-red-500 focus:ring-red-500'
                : 'border-slate-300 bg-white text-slate-900 focus:border-blue-600 focus:ring-blue-600',
              (secretQuestions.isLoading || secretQuestions.isError) && 'bg-slate-50 text-slate-400'
            )}
            {...register('secretQuestionId')}
          >
            {secretQuestions.isLoading ? (
              <option value="">Loading secret questions...</option>
            ) : secretQuestions.isError ? (
              <option value="">Secret questions unavailable</option>
            ) : secretQuestions.isEmpty ? (
              <option value="">No secret questions available</option>
            ) : (
              <>
                <option value="">Select a security question...</option>
                {secretQuestions.questions.map((q) => (
                  <option key={q.questionId} value={q.questionId}>
                    {q.questionText}
                  </option>
                ))}
              </>
            )}
          </select>
        </div>
        {errors.secretQuestionId && (
          <p id="secretQuestionId-error" className="mt-1.5 text-xs text-red-600">
            {errors.secretQuestionId.message}
          </p>
        )}
      </div>

      {/* Secret Answer */}
      <div>
        <label htmlFor="secretAnswer" className="block text-sm font-medium text-slate-700">
          Security Answer <span className="text-red-500">*</span>
        </label>
        <div className="relative mt-1">
          <input
            id="secretAnswer"
            type={showSecretAnswer ? 'text' : 'password'}
            autoComplete="off"
            disabled={isSubmitting}
            aria-invalid={errors.secretAnswer ? 'true' : 'false'}
            aria-describedby={errors.secretAnswer ? 'secretAnswer-error' : 'secretAnswer-hint'}
            className={clsx(
              'block w-full rounded-lg border px-3.5 py-2.5 pr-10 text-sm shadow-sm transition placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-offset-1',
              errors.secretAnswer
                ? 'border-red-300 bg-red-50/30 text-red-900 focus:border-red-500 focus:ring-red-500'
                : 'border-slate-300 bg-white text-slate-900 focus:border-blue-600 focus:ring-blue-600'
            )}
            placeholder="Your confidential recovery answer"
            {...register('secretAnswer')}
          />
          <button
            type="button"
            onClick={() => setShowSecretAnswer((prev) => !prev)}
            className="absolute inset-y-0 right-0 flex items-center pr-3 text-slate-400 hover:text-slate-600 focus:outline-none focus:text-blue-600"
            aria-label={showSecretAnswer ? 'Hide security answer' : 'Show security answer'}
            tabIndex={0}
          >
            {showSecretAnswer ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>
        {errors.secretAnswer ? (
          <p id="secretAnswer-error" className="mt-1.5 text-xs text-red-600">
            {errors.secretAnswer.message}
          </p>
        ) : (
          <p id="secretAnswer-hint" className="mt-1 text-xs text-slate-500">
            Used to securely recover your account. Minimum 2 characters.
          </p>
        )}
      </div>

      {/* Role Notice */}
      <div className="flex items-center gap-2 rounded-lg bg-slate-50 p-3 text-xs text-slate-600 border border-slate-200/60">
        <ShieldCheck className="h-4 w-4 text-blue-600 flex-shrink-0" />
        <span>New accounts are assigned default Regular User operational permissions.</span>
      </div>

      {/* Submit Button */}
      <div className="pt-2">
        <button
          type="submit"
          disabled={isFormDisabled}
          className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isSubmitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Creating account...</span>
            </>
          ) : (
            <span>Create account</span>
          )}
        </button>
      </div>
    </form>
  );
};
