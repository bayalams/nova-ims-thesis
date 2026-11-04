"""
Tests for knowledge-base text chunking.
"""

import unittest

from knowledge_bases.chunking.chunk_text import chunk_article_text


class KnowledgeBaseChunkingTests(unittest.TestCase):
    def test_no_chunking_returns_one_chunk(self):
        chunks = chunk_article_text("First paragraph.\n\nSecond paragraph.", "none", 0, 0)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["chunk_index"], 0)
        self.assertEqual(chunks[0]["text"], "First paragraph.\n\nSecond paragraph.")

    def test_fixed_chunking_uses_overlap(self):
        chunks = chunk_article_text("abcdefghij", "fixed_size", 4, 1)

        self.assertEqual([item["text"] for item in chunks], ["abcd", "defg", "ghij", "j"])

    def test_recursive_chunking_prefers_paragraph_breaks(self):
        text = "Alpha sentence.\n\nBeta sentence.\n\nGamma sentence."

        chunks = chunk_article_text(text, "recursive", 24, 0)

        self.assertGreaterEqual(len(chunks), 2)
        self.assertIn("Alpha", chunks[0]["text"])

    def test_unknown_chunking_method_fails_clearly(self):
        with self.assertRaises(ValueError):
            chunk_article_text("Text", "mystery", 10, 0)

    def test_overlap_must_be_smaller_than_chunk_size(self):
        with self.assertRaises(ValueError):
            chunk_article_text("Text", "fixed_size", 10, 10)


if __name__ == "__main__":
    unittest.main()
