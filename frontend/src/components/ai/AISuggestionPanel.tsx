import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Sparkles,
  Send,
  Check,
  X,
  Bot,
  ArrowRight,
  HelpCircle,
  CheckCircle2,
} from 'lucide-react';
import { AISuggestion } from '@/types';
import { Button } from '@/components/ui/Button';

interface AISuggestionPanelProps {
  suggestions: AISuggestion[];
  onAccept: (suggestion: AISuggestion) => void;
  onReject: (suggestion: AISuggestion) => void;
  onGenerateSuggestion?: (prompt: string) => void;
}

export const AISuggestionPanel: React.FC<AISuggestionPanelProps> = ({
  suggestions,
  onAccept,
  onReject,
  onGenerateSuggestion,
}) => {
  const [prompt, setPrompt] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);

  const quickPrompts = [
    'Improve clarity & active voice',
    'Standardize terminology',
    'Verify GxP compliance',
    'Format as numbered steps',
  ];

  const handleSend = () => {
    if (!prompt.trim()) return;
    setIsGenerating(true);
    onGenerateSuggestion?.(prompt);
    setTimeout(() => {
      setIsGenerating(false);
      setPrompt('');
    }, 800);
  };

  return (
    <div className="dashboard-card flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border bg-card/60 px-4 py-2.5 text-xs">
        <div className="flex items-center gap-1.5 font-semibold text-text-main">
          <Sparkles className="size-4 text-primary" />
          <span>AI Assistance & Suggestions</span>
        </div>
        <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-mono text-primary">
          Gemini 2.5
        </span>
      </div>

      {/* Body: Prompt input + Suggestion Cards */}
      <div className="flex-1 p-4 overflow-y-auto space-y-4">
        {/* Prompt Input */}
        <div className="space-y-2">
          <div className="relative">
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Ask AI to refine, transform, or review this section..."
              rows={3}
              className="field text-xs p-2.5 resize-none bg-black/20 pr-10"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  handleSend();
                }
              }}
            />
            <Button
              variant="icon"
              size="sm"
              onClick={handleSend}
              isLoading={isGenerating}
              disabled={!prompt.trim()}
              className="absolute right-2 bottom-2 size-7"
              aria-label="Send prompt"
            >
              <Send className="size-3.5 text-primary" />
            </Button>
          </div>

          {/* Quick Action Chips */}
          <div className="flex flex-wrap gap-1.5">
            {quickPrompts.map((qp, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => {
                  setPrompt(qp);
                }}
                className="rounded-md border border-border bg-white/5 px-2 py-1 text-[10px] text-text-muted hover:border-primary/40 hover:text-primary transition"
              >
                {qp}
              </button>
            ))}
          </div>
        </div>

        {/* Suggestions List */}
        <div className="space-y-3 pt-2">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">
            Proposed AI Patches ({suggestions.length})
          </div>

          {suggestions.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border p-5 text-center text-xs text-text-muted">
              <Bot className="size-6 mx-auto mb-1.5 opacity-40 text-primary" />
              <span>No pending suggestions. Type a prompt above or trigger an automated workflow.</span>
            </div>
          ) : (
            <AnimatePresence>
              {suggestions.map((sug) => (
                <motion.div
                  key={sug.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.95 }}
                  className="rounded-lg border border-primary/30 bg-primary/[0.04] p-3.5 space-y-2.5"
                >
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-primary capitalize flex items-center gap-1.5">
                      <Sparkles className="size-3" />
                      {sug.action.replace(/_/g, ' ')}
                    </span>
                    <span className="text-[10px] text-text-muted">
                      {sug.model_metadata || 'AI Proposed'}
                    </span>
                  </div>

                  {sug.explanation && (
                    <p className="text-xs text-text-muted leading-relaxed italic">
                      "{sug.explanation}"
                    </p>
                  )}

                  {/* Patch Content Preview */}
                  <div className="rounded border border-border/80 bg-black/30 p-2.5 text-xs font-mono text-emerald-400 max-h-32 overflow-y-auto whitespace-pre-wrap leading-tight">
                    {sug.patch_json}
                  </div>

                  {/* Accept / Reject Buttons */}
                  <div className="flex items-center justify-end gap-2 pt-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onReject(sug)}
                      leftIcon={<X className="size-3 text-red-400" />}
                      className="text-xs text-red-400 hover:bg-red-500/10"
                    >
                      Reject
                    </Button>

                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => onAccept(sug)}
                      leftIcon={<Check className="size-3" />}
                      className="text-xs"
                    >
                      Accept Patch
                    </Button>
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
          )}
        </div>
      </div>
    </div>
  );
};
