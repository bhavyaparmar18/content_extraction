import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import {
  Eye,
  EyeOff,
  AlertCircle,
  Loader2,
  Lock,
  Mail,
  CheckCircle2,
  ShieldAlert,
  Clock,
} from 'lucide-react';
import { clsx } from 'clsx';
import { loginSchema, LoginSchemaType } from '@/features/auth/schemas/loginSchema';
import { LoginFormValues } from '@/features/auth/types/auth.types';
import { useLogin } from '@/features/auth/hooks/useLogin';

interface LoginFormProps {
  onSuccess?: () => void;
}

export const LoginForm: React.FC<LoginFormProps> = ({ onSuccess }) => {
  const [showPassword, setShowPassword] = useState(false);

  const {
    register,
    handleSubmit,
    setError,
    resetField,
    formState: { errors },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    mode: 'onTouched',
    defaultValues: {
      biEmail: '',
      password: '',
      rememberMe: false,
    },
  });

  const { submitLogin, isSubmitting, formError, errorCode, correlationId, isSuccess } =
    useLogin({
      setError,
      onSuccess: () => {
        if (onSuccess) {
          onSuccess();
        }
      },
      onSecurityFailure: () => {
        // Clear sensitive password field on failure
        resetField('password');
      },
    });

  const onSubmit = async (values: LoginFormValues) => {
    await submitLogin(values);
  };

  if (isSuccess) {
    return (
      <div
        className="rounded-xl border border-emerald-200 bg-emerald-50/70 p-6 text-center shadow-sm"
        role="alert"
        aria-live="polite"
      >
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 mb-3">
          <CheckCircle2 className="h-6 w-6" />
        </div>
        <h3 className="text-lg font-semibold text-emerald-950">Authentication Succeeded</h3>
        <p className="mt-1 text-sm text-emerald-700">
          Redirecting to your workspace...
        </p>
      </div>
    );
  }

  return (
    <form noValidate onSubmit={handleSubmit(onSubmit)} className="space-y-5" aria-label="Sign in form">
      {/* Form Error Alert */}
      {formError && (
        <div
          role="alert"
          aria-live="polite"
          className={clsx(
            'flex items-start gap-3 rounded-xl border p-4 text-sm shadow-sm transition-all',
            errorCode === 'ACCOUNT_LOCKED'
              ? 'border-amber-300 bg-amber-50/90 text-amber-900'
              : errorCode === 'RATE_LIMIT_EXCEEDED'
              ? 'border-orange-300 bg-orange-50/90 text-orange-900'
              : 'border-red-200 bg-red-50/90 text-red-900'
          )}
        >
          {errorCode === 'ACCOUNT_LOCKED' ? (
            <ShieldAlert className="h-5 w-5 flex-shrink-0 text-amber-600 mt-0.5" />
          ) : errorCode === 'RATE_LIMIT_EXCEEDED' ? (
            <Clock className="h-5 w-5 flex-shrink-0 text-orange-600 mt-0.5" />
          ) : (
            <AlertCircle className="h-5 w-5 flex-shrink-0 text-red-600 mt-0.5" />
          )}

          <div className="flex-1 space-y-1">
            <p className="font-semibold leading-snug">{formError}</p>

            {errorCode === 'ACCOUNT_LOCKED' && (
              <p className="text-xs text-amber-700">
                Need immediate access? You can reset your credentials via{' '}
                <Link
                  to="/forgot-password"
                  className="font-semibold underline hover:text-amber-800"
                >
                  Password Recovery
                </Link>{' '}
                or contact IT support.
              </p>
            )}

            {correlationId && (
              <p className="text-[11px] font-mono text-slate-500 pt-0.5">
                Support ID: {correlationId}
              </p>
            )}
          </div>
        </div>
      )}

      {/* BI Email Input */}
      <div>
        <label htmlFor="biEmail" className="block text-sm font-medium text-slate-700">
          BI Email <span className="text-red-500">*</span>
        </label>
        <div className="relative mt-1">
          <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
            <Mail className="h-4 w-4" />
          </div>
          <input
            id="biEmail"
            type="email"
            autoComplete="email"
            disabled={isSubmitting}
            aria-invalid={errors.biEmail ? 'true' : 'false'}
            aria-describedby={errors.biEmail ? 'biEmail-error' : undefined}
            className={clsx(
              'block w-full rounded-lg border pl-9 pr-3.5 py-2.5 text-sm shadow-sm transition placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-offset-1',
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

      {/* Password Input */}
      <div>
        <div className="flex items-center justify-between">
          <label htmlFor="password" className="block text-sm font-medium text-slate-700">
            Password <span className="text-red-500">*</span>
          </label>
          <Link
            to="/forgot-password"
            className="text-xs font-semibold text-blue-600 hover:text-blue-700 focus:outline-none focus:underline"
          >
            Forgot password?
          </Link>
        </div>
        <div className="relative mt-1">
          <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
            <Lock className="h-4 w-4" />
          </div>
          <input
            id="password"
            type={showPassword ? 'text' : 'password'}
            autoComplete="current-password"
            disabled={isSubmitting}
            aria-invalid={errors.password ? 'true' : 'false'}
            aria-describedby={errors.password ? 'password-error' : undefined}
            className={clsx(
              'block w-full rounded-lg border pl-9 pr-10 py-2.5 text-sm shadow-sm transition placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-offset-1',
              errors.password
                ? 'border-red-300 bg-red-50/30 text-red-900 focus:border-red-500 focus:ring-red-500'
                : 'border-slate-300 bg-white text-slate-900 focus:border-blue-600 focus:ring-blue-600'
            )}
            placeholder="••••••••••••"
            {...register('password')}
          />
          <button
            type="button"
            onClick={() => setShowPassword(!showPassword)}
            className="absolute inset-y-0 right-0 flex items-center pr-3 text-slate-400 hover:text-slate-600 focus:outline-none"
            aria-label={showPassword ? 'Hide password' : 'Show password'}
          >
            {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>
        {errors.password && (
          <p id="password-error" className="mt-1.5 text-xs text-red-600">
            {errors.password.message}
          </p>
        )}
      </div>

      {/* Remember Me Checkbox */}
      <div className="flex items-center">
        <input
          id="rememberMe"
          type="checkbox"
          disabled={isSubmitting}
          className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-2 focus:ring-blue-500/30 focus:ring-offset-1 cursor-pointer"
          {...register('rememberMe')}
        />
        <label htmlFor="rememberMe" className="ml-2.5 block text-sm text-slate-600 cursor-pointer select-none">
          Remember me for 30 days
        </label>
      </div>

      {/* Submit Button */}
      <div className="pt-1">
        <button
          type="submit"
          disabled={isSubmitting}
          className={clsx(
            'flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-md shadow-blue-500/20 transition duration-150 ease-in-out hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2',
            isSubmitting && 'cursor-not-allowed opacity-75'
          )}
        >
          {isSubmitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Signing in...</span>
            </>
          ) : (
            <span>Sign in to Platform</span>
          )}
        </button>
      </div>
    </form>
  );
};
