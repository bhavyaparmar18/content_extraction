import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from '@/components/layout/Layout';
import { SopRepository } from '@/pages/SopRepository';
import { SopContentView } from '@/pages/SopContentView';
import { ReviewPage } from '@/pages/ReviewPage';
import { ReprocessingAdminPage } from '@/pages/ReprocessingAdminPage';

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<SopRepository />} />
          <Route path="/sops/:recordId" element={<SopContentView />} />
          <Route path="/review/:recordId" element={<ReviewPage />} />
          <Route path="/admin/reprocessing" element={<ReprocessingAdminPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
};

export default App;
