import React, { useState } from 'react';
import { Sidebar } from './Sidebar';
import { AppHeader } from './AppHeader';
import { clsx } from 'clsx';

interface LayoutProps {
  children: React.ReactNode;
  headerExtra?: React.ReactNode;
}

export const Layout: React.FC<LayoutProps> = ({ children, headerExtra }) => {
  const [isCollapsed, setIsCollapsed] = useState(false);

  return (
    <div className="app-shell flex">
      {/* Navigation Sidebar */}
      <Sidebar
        isCollapsed={isCollapsed}
        onToggleCollapse={() => setIsCollapsed((prev) => !prev)}
      />

      {/* Main Workspace Frame */}
      <div
        className={clsx(
          'flex flex-1 flex-col h-screen overflow-hidden transition-all duration-300',
          isCollapsed ? 'pl-[72px]' : 'pl-[224px]'
        )}
      >
        <AppHeader breadcrumbExtra={headerExtra} />

        {/* Scrollable View Content */}
        <main className="flex-1 overflow-y-auto bg-app">{children}</main>
      </div>
    </div>
  );
};
