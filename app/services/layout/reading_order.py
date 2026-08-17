"""Reading-order reconstruction using the recursive XY-cut algorithm.

The XY-cut (Breuel 2002) alternates between horizontal and vertical cuts
at the widest whitespace gap to recursively partition page content into
reading-order regions.  Within each leaf region, blocks are sorted
top-to-bottom.

This module is consumed by ``PDFLayoutAnalyzer`` to produce a correct
reading order from spatially unordered PDF blocks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from loguru import logger as _default_logger


@dataclass
class Block:
    """A minimal spatial block extracted from a PDF page."""
    block_id: str
    x0: float
    y0: float
    x1: float
    y1: float
    content: str = ""


@dataclass
class ReadingOrderResult:
    """The output of reading-order analysis for a single page."""
    ordered_blocks: list[Block] = field(default_factory=list)
    column_count: int = 1
    column_boundaries: list[tuple[float, float]] = field(default_factory=list)


class ReadingOrderAnalyzer:
    """Reconstructs reading order via recursive XY-cut.

    Parameters
    ----------
    min_gap_ratio : float
        Minimum whitespace gap as a fraction of page width/height to
        trigger a cut.  Default 0.03 (3%).
    min_blocks_per_region : int
        Don't split a region with fewer blocks than this.
    """

    def __init__(
        self,
        min_gap_ratio: float = 0.03,
        min_blocks_per_region: int = 1,
        logger=None,
    ) -> None:
        self._min_gap_ratio = min_gap_ratio
        self._min_blocks_per_region = min_blocks_per_region
        self.logger = logger or _default_logger

    # ── Public API ────────────────────────────────────────────────────

    def compute_reading_order(
        self,
        blocks: list[Block],
        page_width: float,
        page_height: float,
    ) -> ReadingOrderResult:
        """Return *blocks* sorted into reading order.

        Also detects column count and column boundaries as a side effect.
        """
        if not blocks:
            return ReadingOrderResult()

        ordered: list[Block] = []
        column_boundaries: list[tuple[float, float]] = []

        self._xy_cut(
            blocks,
            page_width,
            page_height,
            ordered,
            column_boundaries,
            depth=0,
            is_vertical_cut=True,  # start with a vertical cut (column detection)
        )

        return ReadingOrderResult(
            ordered_blocks=ordered,
            column_count=max(1, len(column_boundaries)),
            column_boundaries=column_boundaries,
        )

    # ── Recursive XY-cut ──────────────────────────────────────────────

    def _xy_cut(
        self,
        blocks: list[Block],
        region_width: float,
        region_height: float,
        result: list[Block],
        column_boundaries: list[tuple[float, float]],
        depth: int,
        is_vertical_cut: bool,
    ) -> None:
        """Recursively split *blocks* and append leaves to *result* in order."""
        if len(blocks) <= self._min_blocks_per_region:
            # Leaf: sort top-to-bottom, left-to-right
            blocks.sort(key=lambda b: (b.y0, b.x0))
            result.extend(blocks)
            return

        if is_vertical_cut:
            split = self._find_vertical_gap(blocks, region_width)
        else:
            split = self._find_horizontal_gap(blocks, region_height)

        if split is None:
            # No significant gap found — try the other direction
            if is_vertical_cut:
                split = self._find_horizontal_gap(blocks, region_height)
                if split is not None:
                    left, right = self._split_blocks_horizontal(blocks, split)
                    for group in [left, right]:
                        if group:
                            self._xy_cut(
                                group, region_width, region_height,
                                result, column_boundaries, depth + 1,
                                is_vertical_cut=True,
                            )
                    return
            else:
                split = self._find_vertical_gap(blocks, region_width)
                if split is not None:
                    left, right = self._split_blocks_vertical(blocks, split)
                    if depth == 0:
                        # Top-level vertical split → columns detected
                        if left:
                            col_min = min(b.x0 for b in left)
                            col_max = max(b.x1 for b in left)
                            column_boundaries.append((col_min, col_max))
                        if right:
                            col_min = min(b.x0 for b in right)
                            col_max = max(b.x1 for b in right)
                            column_boundaries.append((col_min, col_max))
                    for group in [left, right]:
                        if group:
                            self._xy_cut(
                                group, region_width, region_height,
                                result, column_boundaries, depth + 1,
                                is_vertical_cut=False,
                            )
                    return

            # No gap in either direction — this is a leaf
            blocks.sort(key=lambda b: (b.y0, b.x0))
            result.extend(blocks)
            return

        # Perform the split
        if is_vertical_cut:
            left, right = self._split_blocks_vertical(blocks, split)
            if depth == 0:
                # Top-level vertical split → columns detected
                if left:
                    col_min = min(b.x0 for b in left)
                    col_max = max(b.x1 for b in left)
                    column_boundaries.append((col_min, col_max))
                if right:
                    col_min = min(b.x0 for b in right)
                    col_max = max(b.x1 for b in right)
                    column_boundaries.append((col_min, col_max))
        else:
            left, right = self._split_blocks_horizontal(blocks, split)

        next_cut = not is_vertical_cut
        for group in [left, right]:
            if group:
                self._xy_cut(
                    group, region_width, region_height,
                    result, column_boundaries, depth + 1,
                    is_vertical_cut=next_cut,
                )

    # ── Gap Detection ─────────────────────────────────────────────────

    def _find_vertical_gap(
        self, blocks: list[Block], region_width: float,
    ) -> Optional[float]:
        """Find the widest vertical whitespace gap (column separator).

        Returns the x-coordinate of the gap midpoint, or None.
        """
        if len(blocks) < 2:
            return None

        min_gap = region_width * self._min_gap_ratio

        # Project all blocks onto the x-axis
        # Collect all block edges
        edges: list[tuple[float, float]] = [(b.x0, b.x1) for b in blocks]
        edges.sort(key=lambda e: e[0])

        best_gap_x: Optional[float] = None
        best_gap_size = min_gap

        for i in range(len(edges) - 1):
            gap_start = edges[i][1]  # right edge of current
            gap_end = edges[i + 1][0]  # left edge of next
            gap_size = gap_end - gap_start

            if gap_size > best_gap_size:
                best_gap_size = gap_size
                best_gap_x = (gap_start + gap_end) / 2.0

        return best_gap_x

    def _find_horizontal_gap(
        self, blocks: list[Block], region_height: float,
    ) -> Optional[float]:
        """Find the widest horizontal whitespace gap (row separator).

        Returns the y-coordinate of the gap midpoint, or None.
        """
        if len(blocks) < 2:
            return None

        min_gap = region_height * self._min_gap_ratio

        # Project all blocks onto the y-axis
        edges: list[tuple[float, float]] = [(b.y0, b.y1) for b in blocks]
        edges.sort(key=lambda e: e[0])

        best_gap_y: Optional[float] = None
        best_gap_size = min_gap

        for i in range(len(edges) - 1):
            gap_start = edges[i][1]  # bottom edge of current
            gap_end = edges[i + 1][0]  # top edge of next
            gap_size = gap_end - gap_start

            if gap_size > best_gap_size:
                best_gap_size = gap_size
                best_gap_y = (gap_start + gap_end) / 2.0

        return best_gap_y

    # ── Block Splitting ───────────────────────────────────────────────

    @staticmethod
    def _split_blocks_vertical(
        blocks: list[Block], split_x: float,
    ) -> tuple[list[Block], list[Block]]:
        """Partition blocks into left-of and right-of *split_x*."""
        left: list[Block] = []
        right: list[Block] = []
        for b in blocks:
            mid_x = (b.x0 + b.x1) / 2.0
            if mid_x < split_x:
                left.append(b)
            else:
                right.append(b)
        return left, right

    @staticmethod
    def _split_blocks_horizontal(
        blocks: list[Block], split_y: float,
    ) -> tuple[list[Block], list[Block]]:
        """Partition blocks into above and below *split_y*."""
        top: list[Block] = []
        bottom: list[Block] = []
        for b in blocks:
            mid_y = (b.y0 + b.y1) / 2.0
            if mid_y < split_y:
                top.append(b)
            else:
                bottom.append(b)
        return top, bottom
