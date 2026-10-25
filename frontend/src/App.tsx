import React, { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from '@/components/layout/Layout';
import { SopRepository } from '@/pages/SopRepository';
import { SopContentView } from '@/pages/SopContentView';
import { ReviewPage } from '@/pages/ReviewPage';
import { ReprocessingAdminPage } from '@/pages/ReprocessingAdminPage';
import { TemplateManagement } from '@/pages/TemplateManagement';
import { TemplateContentView } from '@/pages/TemplateContentView';
import { MigrationsList } from '@/pages/MigrationsList';
import { MigrationWorkspace } from '@/pages/MigrationWorkspace';
import { TranslationsList } from '@/pages/TranslationsList';
import { LanguageResources } from '@/pages/LanguageResources';
import { GlossaryEditorPage } from '@/pages/GlossaryEditorPage';
import { LanguageTemplatePage } from '@/pages/LanguageTemplatePage';
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
                  <Route path="/templates" element={<TemplateManagement />} />
                  <Route path="/templates/:templateId" element={<TemplateContentView />} />
                  <Route path="/sops/:recordId" element={<SopContentView />} />
                  <Route path="/review/:recordId" element={<ReviewPage />} />
                  <Route path="/migrations" element={<MigrationsList />} />
                  <Route path="/migrations/:jobId" element={<MigrationWorkspace />} />
                  <Route path="/translations" element={<TranslationsList />} />
                  <Route path="/translations/resources" element={<LanguageResources />} />
                  <Route path="/translations/resources/glossaries/:glossaryId" element={<GlossaryEditorPage />} />
                  <Route path="/translations/resources/templates/:templateId" element={<LanguageTemplatePage />} />
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
