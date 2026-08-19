"""Semantic chunking strategy (torch-free).

Takes a list of structurally defined Chunks (from the HierarchicalChunker)
and refines them by splitting large chunks into smaller semantic blocks based
on TF-IDF cosine similarity of adjacent paragraphs.

Uses scikit-learn only — no torch or sentence-transformers required.
"""

import uuid
from pathlib import Path
import numpy as np

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.schemas.document import Chunk
from app.schemas.ast_nodes import DocumentNode
from .base_chunker import BaseChunker


class SemanticChunker(BaseChunker):
    """Refines chunks by splitting them at points of low semantic similarity."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._vectorizer = TfidfVectorizer(
            stop_words="english",
            max_features=5000,
            ngram_range=(1, 2),
        )

    def _merge_continuation_paragraphs(self, paragraphs: list[str]) -> list[str]:
        """Merge adjacent paragraphs that are continuations of each other.

        PDF layout engines often split a single logical sentence or list item
        across multiple text blocks due to changes in indentation, bold/regular
        spans, or wrapping. This produces ``\\n\\n``-separated fragments like::

            "1. Channels deliver messages to the Gateway (WS"
            "control plane)."

        A paragraph boundary is treated as a continuation (and therefore merged)
        when ANY of the following conditions holds for the *preceding* paragraph:

        * It has unbalanced open parentheses / brackets / braces (an open bracket
          that was never closed in that block).
        * It ends with a hyphen ``-`` (word-wrap hyphenation).
        * Its last character is not a sentence-ending punctuation mark
          (``.``, ``!``, ``?``, ``:``) AND the next paragraph starts with a
          lower-case letter or a closing bracket/parenthesis.
        """
        if not paragraphs:
            return []

        CLOSING_CHARS = frozenset(")]}»")
        TERMINAL_PUNCT = frozenset(".!?:")

        def _is_continuation(prev: str, nxt: str) -> bool:
            if not prev or not nxt:
                return False

            # 0. Keep inline icon/image/table markers attached to adjacent text
            if nxt.strip().startswith(("[Icon:", "[Image:", "[Table:")) or prev.strip().startswith(("[Icon:", "[Image:", "[Table:")):
                return True

            # 1. Unbalanced open brackets in prev
            open_count = (
                prev.count("(") - prev.count(")")
                + prev.count("[") - prev.count("]")
                + prev.count("{") - prev.count("}")
            )
            if open_count > 0:
                return True

            # 2. Hyphen at end of prev (word-wrap)
            if prev.endswith("-"):
                return True

            # 3. No terminal punctuation at end of prev AND next starts with
            #    a lowercase letter or a closing bracket.
            last_char = prev[-1]
            first_char = nxt[0]
            if last_char not in TERMINAL_PUNCT:
                if first_char.islower() or first_char in CLOSING_CHARS:
                    return True

            return False

        merged: list[str] = [paragraphs[0]]
        for nxt in paragraphs[1:]:
            if _is_continuation(merged[-1], nxt):
                # Join with a single space (the block boundary was a layout artefact)
                merged[-1] = merged[-1] + " " + nxt
            else:
                merged.append(nxt)

        return merged

    def chunk(self, data: DocumentNode | list[Chunk]) -> list[Chunk]:
        if not isinstance(data, list):
            raise TypeError("SemanticChunker expects a list of Chunks.")

        self.logger.info(f"SemanticChunker: refining {len(data)} chunks.")

        refined_chunks: list[Chunk] = []

        for chunk in data:
            # If the chunk is small or mostly tables/images, don't split it.
            if not chunk.content or len(chunk.content.split()) < 50:
                refined_chunks.append(chunk)
                continue

            # Split content into paragraphs
            paragraphs = [p.strip() for p in chunk.content.split("\n\n") if p.strip()]
            paragraphs = self._merge_continuation_paragraphs(paragraphs)

            # If there's only one paragraph, no point in splitting
            if len(paragraphs) <= 1:
                refined_chunks.append(chunk)
                continue

            # Compute TF-IDF vectors for all paragraphs
            try:
                tfidf_matrix = self._vectorizer.fit_transform(paragraphs)
            except ValueError:
                # All paragraphs are stop-words or empty after processing
                refined_chunks.append(chunk)
                continue

            # Calculate similarities between adjacent paragraphs
            similarities = []
            for i in range(tfidf_matrix.shape[0] - 1):
                sim = cosine_similarity(
                    tfidf_matrix[i],
                    tfidf_matrix[i + 1],
                )[0][0]
                similarities.append(sim)

            # Find split indices based on threshold
            split_indices = []
            for i, sim in enumerate(similarities):
                if sim < self.settings.similarity_threshold:
                    split_indices.append(i + 1)

            if not split_indices:
                refined_chunks.append(chunk)
                continue

            self.logger.debug(
                f"Semantic split in chunk {chunk.chunk_id} "
                f"at {len(split_indices)} points"
            )

            # Split the chunk
            start = 0
            sub_chunks = []
            split_indices.append(len(paragraphs))

            for idx, end in enumerate(split_indices):
                sub_paras = paragraphs[start:end]
                sub_content = "\n\n".join(sub_paras)

                # Clone chunk metadata, give new ID
                new_id = str(uuid.uuid4())
                new_meta = chunk.metadata.model_copy(deep=True)
                new_meta.chunk_id = new_id

                # Append a sub-part indicator to the section name if we split
                if len(split_indices) > 1:
                    new_meta.section = f"{chunk.metadata.section} (Part {idx + 1})"

                # Ensure every sub-chunk starts with the section heading so that
                # the section context is preserved for QA retrieval.
                heading_prefix = f"# {chunk.heading}" if chunk.heading else ""
                if heading_prefix and not sub_content.startswith(heading_prefix):
                    sub_content = f"{heading_prefix}\n\n{sub_content}"

                # Distribute tables/images/icons based on inline text marker matching
                images = [
                    img for img in chunk.images
                    if (img.content and img.content in sub_content) or (img.image_path and Path(img.image_path).name in sub_content)
                ]
                if idx == 0 and not images and not any((img.content and img.content in chunk.content) for img in chunk.images):
                    images = chunk.images

                icons = [
                    ic for ic in chunk.icons
                    if (ic.content and ic.content in sub_content) or (ic.image_path and Path(ic.image_path).name in sub_content)
                ]
                if idx == 0 and not icons and not any((ic.content and ic.content in chunk.content) for ic in chunk.icons):
                    icons = chunk.icons

                tables = [
                    t for t in chunk.tables
                    if t.content and t.content in sub_content
                ]
                if idx == 0 and not tables and chunk.tables and not any((t.content and t.content in chunk.content) for t in chunk.tables):
                    tables = chunk.tables

                sub_chunk = Chunk(
                    chunk_id=new_id,
                    chunk_type=chunk.chunk_type,
                    heading=chunk.heading,
                    content=sub_content,
                    tables=tables,
                    images=images,
                    icons=icons,
                    metadata=new_meta,
                )
                sub_chunks.append(sub_chunk)
                start = end

            refined_chunks.extend(sub_chunks)

        self.logger.info(
            f"SemanticChunker: produced {len(refined_chunks)} total refined chunks."
        )
        return refined_chunks
