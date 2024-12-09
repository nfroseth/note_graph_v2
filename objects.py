from abc import ABC, abstractmethod
from datetime import datetime
from collections import defaultdict
from pathlib import Path
import string
from typing import Dict, List, Optional


class Node:
    pass


class Alias:
    pass


class Tag:
    pass


class Folder:
    pass


# Obsidian Graph Objects
class Link:
    def __init__(self, type: str, properties={}):
        self.type = type  # "Wikilink", "Markdown", "External"
        self.properties = properties

        self._blacklisted_repr = {"context"}

    def __str__(self):
        return self.type + self.properties.__str__()

    def __repr__(self):
        filtered_properties = {k: v for k, v in self.properties.items() if v and k not in self._blacklisted_repr}
        return f"Link(type={self.type}, properties={filtered_properties})"


# Enumarate through all the different types of links components there could be in a Wikilink
class ObsidianLink:
    def __init__(self, format_type: str, target: Path, display_text: Optional[str] = None, headers: List[str] = [], block_hash: Optional[str] = None):
        self.format_type = format_type  # "Wikilink", "Markdown", "External"
        self.target = target  # The target file or path
        self.display_text = display_text  # Display text, if provided
        self.headers = headers if headers else []  # List of headers (subsections)
        self.block_hash = block_hash  # Block reference, if provided

    def __repr__(self):
        return self.rebuild()

    def rebuild(self):
        base = f"[[{str(self.target)}"
        if self.headers:
            base += "#" + "#".join(self.headers)
        if self.block_hash:
            base += f"^#{self.block_hash}"
        if self.display_text:
            base += f"|{self.display_text}"
        return base + "]]"

    def is_target_relative_path(self) -> bool:
        return len(self.target.parts) > 1

    def __hash__(self):
        # Rebuild without display text
        # Does adding the Display text help or hurt for uniqueness and referencing the correct thing
        hash(self.rebuild())

    def is_self_link(self) -> bool:
        return len(self.target.parts) == 0

    def is_link_to_chunk(self) -> bool:
        has_block_hash = self.block_hash is not None
        has_headers = len(self.headers) > 0

        return has_block_hash or has_headers


class Split:
    def __init__(self, count: int, content: str):
        self._count = count
        self._content = content
        self._tags = defaultdict(list)
        self._aliases = defaultdict(list)
        self._outgoing_chunk_links = []
        self._outgoing_note_links = []
        self._embedding = []

    @property
    def embedding(self) -> List[float]:
        return self._embedding

    @property
    def first_line(self) -> str:
        first_break = self.content.find("\n")
        return self.content[:first_break]

    @property
    def name(self) -> str:
        # count # _
        # Take the first 5 words then the first 32 characters for the name
        # Can/Should be overloaded to have Generative LLM name
        return (
            f"{self.count}_"
            + " ".join(self.first_line.translate(str.maketrans(string.punctuation, " " * len(string.punctuation))).strip().split(" ")[:5])[:32]
            + "..."
        )

    @property
    def count(self) -> int:
        return self._count

    @property
    def content(self) -> str:
        return self._content

    @property
    def tags(self) -> Dict[str, List[Link]]:
        return self._tags

    def add_alias(self, alias: Alias, link: Link) -> None:
        self._aliases[alias].append(link)

    def add_tag(self, tag: Tag, link: Link) -> None:
        self._tags[tag].append(link)

    def add_outgoing_chunk_link(self, link: Link) -> None:
        self._outgoing_chunk_links.append(link)

    def add_outgoing_note_link(self, link: Link) -> None:
        self._outgoing_note_links.append(link)

    def set_embedding(self, vectorizer) -> None:
        # Handle how we want short chunks (less than threshold ex 35 char) to be embedded.
        self._embedding = vectorizer.embed_query(self.content)


class Note:
    def __init__(self, path: Path, tags: List[str] = [], aliases: List[str] = [], splits: Optional[List[Split]] = None):
        self._path = path
        self._tags = defaultdict(list)
        self._outgoing_chunk_links = []
        self._outgoing_note_links = []
        self._embedding = []
        self._splits = splits if splits else []
        self._content = None
        self._created_time = None
        self._modified_time = None

    def __repr__(self) -> str:
        return f"Note(name='{self.name}', path='{self._path}', " f"tags={list(self._tags.keys())}, "
        # f"splits={self._splits})")

    @property
    def content(self) -> str:
        with open(self.path, mode="r", encoding="utf-8") as file:
            return file.read()

    @property
    def embedding(self) -> List[float]:
        return self._embedding

    @property
    def path(self) -> Path:
        return self._path

    @property
    def name(self) -> str:
        return self._path.stem

    @property
    def outgoing_links(self) -> List[ObsidianLink]:
        return self._outgoing_note_links

    @property
    def splits(self) -> List[Split]:
        return self._splits

    @property
    def tags(self) -> Dict[str, List[Link]]:
        return self._tags

    @property
    def modified_time(self) -> datetime:
        return self._modified_time

    def add_tag(self, tag: Tag, link: Link) -> None:
        self._tags[tag].append(link)

    def add_outgoing_chunk_link(self, link: Link) -> None:
        self._outgoing_chunk_links.append(link)

    def add_outgoing_note_link(self, link: Link) -> None:
        self._outgoing_note_links.append(link)

    def set_embedding(self, vectorizer) -> None:
        # Handle how we want long note (more than x char) to be embedded.
        self._embedding = vectorizer.embed_query(self.content)

    def add_split(self, split: Split) -> None:
        self._splits.append(split)

    def set_modified_time(self, time):
        self._modified_time = time


class GraphEventHandler(ABC):
    pass


class NoteSplitter(ABC):
    @abstractmethod
    def split_string(self, note_content: str) -> List[str]:
        return


class NoSplitting(NoteSplitter):
    def split_string(self, note_content: str) -> List[str]:
        return [note_content]
