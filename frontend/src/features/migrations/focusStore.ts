import type React from 'react';
import { create } from 'zustand';
import type { EvidenceSpan } from './types';

/** What the reviewer is looking at: the context panes scroll to it and highlight it. */
export interface Focus {
  sourceUnitIds?: string[];
  sourceSectionIds?: string[];
  targetSectionId?: string;
  slotId?: string;
  claimId?: string;
  /** The exact passages a claim rests on, underlined inside their units. */
  spans?: EvidenceSpan[];
  issueId?: string;
  /** Where it was set: a pane does not scroll itself to a focus set inside it. */
  origin?: 'source' | 'template' | 'work';
}

interface FocusState {
  /** Follows the pointer; wins over the pinned focus while set. */
  hover: Focus | null;
  /** Set by a click; stays until another click or Escape. */
  pinned: Focus | null;
  setHover: (focus: Focus | null) => void;
  pin: (focus: Focus | null) => void;
  reset: () => void;
}

export const useFocusStore = create<FocusState>((set) => ({
  hover: null,
  pinned: null,
  setHover: (hover) => set({ hover }),
  pin: (pinned) => set({ pinned, hover: null }),
  reset: () => set({ hover: null, pinned: null }),
}));

export const useActiveFocus = (): Focus | null => useFocusStore((s) => s.hover ?? s.pinned);

/** Props that make an element drive the focus: hover previews it, click pins it. */
export function focusProps(focus: Focus, origin: Focus['origin'] = 'work') {
  const { setHover, pin } = useFocusStore.getState();
  const value = { ...focus, origin };
  return {
    onMouseEnter: () => setHover(value),
    onMouseLeave: () => setHover(null),
    onClick: (event: React.MouseEvent) => {
      event.stopPropagation();
      pin(value);
    },
  };
}

/** Workspace layout requests: which tab the right pane shows on the draft step, and panes to bring into view. */
interface ReviewUiState {
  rightTab: 'issues' | 'template';
  setRightTab: (tab: 'issues' | 'template') => void;
  /** Bumped to ask the shell to show a side pane (e.g. the issues, after a click on a claim's badge). */
  paneRequest: { side: 'left' | 'right'; n: number } | null;
  showPane: (side: 'left' | 'right') => void;
}

export const useReviewUi = create<ReviewUiState>((set) => ({
  rightTab: 'issues',
  setRightTab: (rightTab) => set({ rightTab }),
  paneRequest: null,
  showPane: (side) => set((s) => ({ paneRequest: { side, n: (s.paneRequest?.n ?? 0) + 1 } })),
}));
