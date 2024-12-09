import re
from typing import List
from langchain_text_splitters import MarkdownHeaderTextSplitter, NLTKTextSplitter
from langchain_core.documents import Document

from world_graph.objects import NoteSplitter


class MarkdownThenNLTKSentWithLinkMasking(NoteSplitter):
    def __init__(self, headers_to_split_on=None, chunk_size=10, chunk_overlap=0) -> None:
        # Split an all levels of valid markdown headers
        headers_to_split_on = (
            [
                ("#", "Header 1"),
                ("##", "Header 2"),
                ("###", "Header 3"),
                ("####", "Header 4"),
                ("#####", "Header 5"),
                ("######", "Header 6"),
            ]
            if not headers_to_split_on
            else headers_to_split_on
        )

        # MD splits
        self.markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on, strip_headers=False)
        self.nltk_splitter = NLTKTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    def split_string(self, note_content: str) -> List[str]:
        return [c.page_content for c in self.split_documents([Document(note_content)])]

    def split_documents(self, markdown_documents: List[Document]) -> List[Document]:
        """
        Splits a list of markdown documents into smaller segments while preserving
        embedded wiki-style links.

        This function processes each document in the input list, replaces wiki-style
        links (e.g., `[[SomeLink]]`) with temporary placeholders, splits the text into
        smaller segments using markdown and natural language splitters, and restores
        the original wiki-style links in the resulting segments.

        Args:
            markdown_documents (List[Document]):
                A list of `Document` objects containing markdown content to split.

        Returns:
            List[Document]:
                A list of `Document` objects, each representing a smaller segment of
                the original documents, with wiki-style links restored.
        """
        out_docs = []

        wikilink_pattern = r"\[\[.*?\]\]"
        wikilink_placeholders = []
        placeholder_token = "WIKILINK_PLACEHOLDER_{}"

        def replace_wikilinks(match):
            wikilink_placeholders.append(match.group(0))
            return placeholder_token.format(len(wikilink_placeholders) - 1)

        for doc in markdown_documents:
            text_with_placeholders = re.sub(wikilink_pattern, replace_wikilinks, doc.page_content)
            md_header_splits = self.markdown_splitter.split_text(text_with_placeholders)

            splits = self.nltk_splitter.split_documents(md_header_splits)
            for s in splits:
                s = s.page_content
                for index, wikilink in enumerate(wikilink_placeholders):
                    s = s.replace(placeholder_token.format(index), wikilink)
                else:
                    out_docs.append(Document(s))

        return out_docs
