import React, { useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { FileText, Shield } from 'lucide-react';
import { LoginForm } from '@/components/auth/LoginForm';
import { useAuthStore } from '@/lib/authStore';

export const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  const handleSuccess = () => {
    navigate('/', { replace: true });
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col justify-center py-12 px-4 sm:px-6 lg:px-8">
      {/* Header Branding */}
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center">
        <div className="inline-flex h-12 w-12 items-center justify-center rounded-xl bg-blue-600 text-white shadow-md shadow-blue-500/20 mb-4">
          <FileText className="h-6 w-6" />
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
          Sign in to your account
        </h1>
        <p className="mt-2 text-sm text-slate-600">
          Governance Procedure (SOP) Document Automator
        </p>
      </div>

      {/* Main Card Container */}
      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white py-8 px-6 shadow-sm ring-1 ring-slate-900/5 rounded-2xl sm:px-10 border border-slate-200/80">
          <LoginForm onSuccess={handleSuccess} />

          {/* Footer Link to Signup */}
          <div className="mt-6 border-t border-slate-200/80 pt-6 text-center text-sm text-slate-600">
            <span>Don&apos;t have an account? </span>
            <Link
              to="/signup"
              className="font-semibold text-blue-600 hover:text-blue-700 focus:outline-none focus:underline"
            >
              Create account
            </Link>
          </div>
        </div>

        {/* Bottom Security Assurance */}
        <div className="mt-6 flex items-center justify-center gap-2 text-xs text-slate-500">
          <Shield className="h-3.5 w-3.5 text-slate-400" />
          <span>Enterprise-grade encryption and Argon2id credential protection</span>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
