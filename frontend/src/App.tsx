import React, { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from '@/components/layout/Layout';
import { SopRepository } from '@/pages/SopRepository';
import { SopContentView } from '@/pages/SopContentView';
import { ReviewPage } from '@/pages/ReviewPage';
import { ReprocessingAdminPage } from '@/pages/ReprocessingAdminPage';
import { SignupPage } from '@/pages/SignupPage';
import { LoginPage } from '@/pages/LoginPage';
import { ProtectedRoute } from '@/routes/ProtectedRoute';
import { useAuthStore } from '@/lib/authStore';

export const App: React.FC = () => {
  const initializeAuth = useAuthStore((state) => state.initializeAuth);

  useEffect(() => {
    initializeAuth();
  }, [initializeAuth]);

  return (
    <BrowserRouter>
      <Routes>
        {/* Public Authentication Routes */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />

        {/* Authenticated Workspace Routes */}
        <Route
          path="/*"
          element={
            <ProtectedRoute>
              <Layout>
                <Routes>
                  <Route path="/" element={<SopRepository />} />
                  <Route path="/sops/:recordId" element={<SopContentView />} />
                  <Route path="/review/:recordId" element={<ReviewPage />} />
                  <Route path="/admin/reprocessing" element={<ReprocessingAdminPage />} />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </Layout>
            </ProtectedRoute>
          }
        />
      </Routes>
    </BrowserRouter>
  );
};

export default App;
