import React from 'react';
import { useLocation, Link } from 'react-router-dom';
import { Bell, HelpCircle, ChevronRight, User } from 'lucide-react';
import { ThemeToggle } from '@/components/ui/ThemeToggle';
import { Button } from '@/components/ui/Button';

interface AppHeaderProps {
  breadcrumbExtra?: React.ReactNode;
}

export const AppHeader: React.FC<AppHeaderProps> = ({ breadcrumbExtra }) => {
  const location = useLocation();

  // Compute breadcrumb from path
  const pathParts = location.pathname.split('/').filter(Boolean);

  return (
    <header className="sticky top-0 z-30 flex h-16 w-full items-center justify-between border-b border-border bg-app/80 px-6 backdrop-blur transition-colors">
      {/* Breadcrumbs */}
      <div className="flex items-center gap-2 text-xs text-text-muted">
        <Link to="/" className="hover:text-text-main transition font-medium">
          GP-DAT
        </Link>

        {pathParts.length > 0 && <ChevronRight className="size-3.5 text-text-muted/60" />}

        {pathParts[0] === 'sops' && (
          <>
            <Link to="/" className="hover:text-text-main transition">
              SOP Repository
            </Link>
            <ChevronRight className="size-3.5 text-text-muted/60" />
            <span className="text-text-main font-medium truncate max-w-[200px]">
              Content Viewer
            </span>
          </>
        )}

        {pathParts[0] === 'review' && (
          <>
            <Link to="/" className="hover:text-text-main transition">
              SOP Repository
            </Link>
            <ChevronRight className="size-3.5 text-text-muted/60" />
            <span className="text-text-main font-medium">Review Workspace</span>
          </>
        )}

        {pathParts[0] === 'admin' && (
          <>
            <span className="text-text-muted">Admin</span>
            <ChevronRight className="size-3.5 text-text-muted/60" />
            <span className="text-text-main font-medium">Reprocessing Queue</span>
          </>
        )}

        {pathParts.length === 0 && (
          <span className="text-text-main font-medium">SOP Repository</span>
        )}

        {breadcrumbExtra}
      </div>

      {/* Right Header Actions */}
      <div className="flex items-center gap-2.5">
        <ThemeToggle />

        <Button variant="icon" aria-label="Help and Documentation" title="Help">
          <HelpCircle className="size-4" />
        </Button>

        <Button variant="icon" aria-label="Notifications" title="Notifications">
          <Bell className="size-4" />
        </Button>

        <div className="h-4 w-px bg-border mx-1" />

        {/* User Account Avatar */}
        <div className="flex items-center gap-2.5 pl-1">
          <div className="grid size-8 place-items-center rounded-full bg-primary/20 text-primary border border-primary/30 font-semibold text-xs">
            BP
          </div>
          <div className="hidden text-left sm:block">
            <div className="text-xs font-medium text-text-main leading-tight">Bhavya P.</div>
            <div className="text-[10px] text-text-muted">Lead Reviewer</div>
          </div>
        </div>
      </div>
    </header>
  );
};
