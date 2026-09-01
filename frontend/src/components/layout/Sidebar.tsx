import React, { useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  FileText,
  Layers,
  BookOpen,
  Sparkles,
  ArrowRightLeft,
  Languages,
  ScanText,
  Users,
  Settings,
  ShieldCheck,
  ChevronLeft,
  ChevronRight,
  RotateCcw,
  CheckCircle2,
} from 'lucide-react';
import { clsx } from 'clsx';

interface SidebarProps {
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ isCollapsed, onToggleCollapse }) => {
  const location = useLocation();

  const navSections = [
    {
      title: 'PLATFORM',
      items: [
        { label: 'SOP Repository', path: '/', icon: FileText },
        { label: 'Dashboard', path: '/#dashboard', icon: LayoutDashboard },
        { label: 'Templates', path: '/#templates', icon: Layers },
        { label: 'Glossary', path: '/#glossary', icon: BookOpen },
        { label: 'AI Instructions', path: '/#ai-prompts', icon: Sparkles },
      ],
    },
    {
      title: 'WORKFLOWS',
      items: [
        { label: 'SOP Extraction', path: '/', icon: ScanText },
        { label: 'Translation', path: '/#translation', icon: Languages },
        { label: 'Migration', path: '/#migration', icon: ArrowRightLeft },
      ],
    },
    {
      title: 'ADMIN & SYSTEM',
      items: [
        { label: 'Reprocessing Queue', path: '/admin/reprocessing', icon: RotateCcw },
        { label: 'Model Settings', path: '/#models', icon: Settings },
        { label: 'Audit Logs', path: '/#audit', icon: ShieldCheck },
        { label: 'Users', path: '/#users', icon: Users },
      ],
    },
  ];

  return (
    <aside
      className={clsx(
        'fixed top-0 left-0 bottom-0 z-40 flex flex-col border-r border-border bg-sidebar transition-all duration-300',
        isCollapsed ? 'w-[72px]' : 'w-[224px]'
      )}
    >
      {/* Brand Header */}
      <div className="flex h-16 items-center justify-between px-4 border-b border-border">
        {!isCollapsed ? (
          <div className="flex items-center gap-2.5 overflow-hidden">
            <div className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary text-slate-950 font-black text-sm tracking-tight shadow-glow">
              GP
            </div>
            <div className="min-w-0">
              <div className="text-sm font-bold text-text-main tracking-tight leading-none">
                GP-DAT
              </div>
              <div className="text-[10px] font-medium text-primary mt-0.5 tracking-wider uppercase">
                Platform v1.0
              </div>
            </div>
          </div>
        ) : (
          <div className="mx-auto grid size-9 place-items-center rounded-lg bg-primary text-slate-950 font-black text-sm shadow-glow">
            GP
          </div>
        )}
      </div>

      {/* Navigation Links */}
      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-6">
        {navSections.map((section, idx) => (
          <div key={idx}>
            {!isCollapsed && (
              <div className="px-3 pb-2 text-[10px] font-semibold text-text-muted/70 tracking-wider">
                {section.title}
              </div>
            )}
            <div className="space-y-1">
              {section.items.map((item) => {
                const Icon = item.icon;
                const isActive =
                  item.path === '/'
                    ? location.pathname === '/'
                    : location.pathname.startsWith(item.path.split('#')[0]) && item.path !== '/';

                return (
                  <NavLink
                    key={item.label}
                    to={item.path}
                    title={isCollapsed ? item.label : undefined}
                    className={({ isActive: isExactActive }) =>
                      clsx(
                        'sidebar-item group',
                        (isActive || (item.path === '/' && location.pathname === '/'))
                          ? 'sidebar-item-active'
                          : ''
                      )
                    }
                  >
                    <Icon className="size-4 shrink-0 transition-transform group-hover:scale-110" />
                    {!isCollapsed && (
                      <span className="truncate text-xs font-medium">{item.label}</span>
                    )}
                  </NavLink>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Collapse Toggle Footer */}
      <div className="border-t border-border p-3">
        <button
          type="button"
          onClick={onToggleCollapse}
          className="flex h-10 w-full items-center justify-center gap-2 rounded-md border border-border text-xs text-text-muted hover:bg-white/5 hover:text-text-main transition"
          aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {isCollapsed ? (
            <ChevronRight className="size-4" />
          ) : (
            <>
              <ChevronLeft className="size-4" />
              <span>Collapse</span>
            </>
          )}
        </button>
      </div>
    </aside>
  );
};
