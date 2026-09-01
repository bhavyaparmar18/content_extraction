import React, { useState } from 'react';
import { BookOpen, Search, Plus, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/Button';

interface GlossaryTerm {
  source: string;
  target: string;
  category: string;
  isProtected?: boolean;
}

export const GlossaryPanel: React.FC = () => {
  const [search, setSearch] = useState('');
  const [terms, setTerms] = useState<GlossaryTerm[]>([
    { source: 'Standard Operating Procedure', target: 'Procédure Opératoire Normalisée', category: 'General' },
    { source: 'Quality Assurance', target: 'Assurance Qualité', category: 'GxP' },
    { source: 'Good Manufacturing Practice', target: 'Bonnes Pratiques de Fabrication', category: 'GxP' },
    { source: 'BI-VQD-24416', target: 'BI-VQD-24416', category: 'Protected Code', isProtected: true },
    { source: 'Batch Record', target: 'Dossier de Lot', category: 'Manufacturing' },
  ]);

  const filtered = terms.filter(
    (t) =>
      t.source.toLowerCase().includes(search.toLowerCase()) ||
      t.target.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="dashboard-card flex flex-col h-full overflow-hidden">
      <div className="flex items-center justify-between border-b border-border bg-card/60 px-4 py-2.5 text-xs">
        <div className="flex items-center gap-1.5 font-semibold text-text-main">
          <BookOpen className="size-3.5 text-primary" />
          <span>Translation Glossary ({terms.length})</span>
        </div>
      </div>

      <div className="p-3 border-b border-border">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search glossary terms..."
          className="field h-8 text-xs px-2.5 bg-black/20"
        />
      </div>

      <div className="flex-1 p-3 overflow-y-auto space-y-2 text-xs">
        {filtered.map((t, idx) => (
          <div key={idx} className="rounded-lg border border-border bg-card p-2.5 space-y-1">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-text-main">{t.source}</span>
              {t.isProtected && (
                <span className="rounded bg-sky-500/15 text-sky-400 text-[10px] px-1.5 py-0.2 font-mono flex items-center gap-1">
                  <ShieldCheck className="size-3" /> Protected
                </span>
              )}
            </div>
            <div className="text-primary font-medium">{t.target}</div>
            <div className="text-[10px] text-text-muted">{t.category}</div>
          </div>
        ))}
      </div>
    </div>
  );
};
