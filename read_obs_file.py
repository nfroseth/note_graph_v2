import datetime
from urllib.parse import quote
import random
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import logging

from joblib import Parallel, delayed, parallel_config

from tqdm import tqdm
from rich.logging import RichHandler

from world_graph.chunking import MarkdownThenNLTKSentWithLinkMasking
import world_graph.note_parsing as np
from world_graph.utils import time_function

from world_graph.objects import GraphEventHandler, Link, Note, NoteSplitter, NoSplitting, Split

logging.basicConfig(level=logging.WARNING, format="%(message)", datefmt="%X", handlers=[RichHandler(rich_tracebacks=True)])

file_log = logging.getLogger("rich_logger")


class GraphDog:
    def __init__(self, path_to_notes, event_handler: GraphEventHandler, splitter: Optional[NoteSplitter] = None, embedder = None):
        self._path_to_notes = path_to_notes
        self._event_handler = event_handler
        self._splitter = splitter if splitter else NoSplitting()
        self._embedder = embedder

    @property
    def path_to_notes(self) -> Path:
        return self._path_to_notes

    @property
    def vault_name(self) -> str:
        return self.path_to_notes.stem

    @property
    def event_handler(self) -> GraphEventHandler:
        return self._event_handler

    @property
    def splitter(self) -> NoSplitting:
        return self._splitter

    @time_function
    def sync_database_with_notes(self, callable_override: Optional[Callable] = None):
        job_number = 1
        parallelism_type = "threading"  # loky

        note_ext_type = ".md"
        sample_size = 50
        random.seed(2342)

        note_path = Path(self._path_to_notes)
        note_tree = note_path.rglob("*" + note_ext_type)

        note_paths = [path for path in note_tree]
        sample_size = sample_size if sample_size else len(note_paths)
        shuffled_sample_notes = random.sample(note_paths, sample_size)

        apply_func = callable_override if callable_override else self.serialize_obsidian_note
        with parallel_config(backend=parallelism_type, n_jobs=job_number):
            # results = list(tqdm(Parallel(return_as="generator")(delayed(self.serialize_obsidian_note)(i) for i in shuffled_sample_notes)))
            results = list(Parallel(return_as="generator")(delayed(apply_func)(i) for i in shuffled_sample_notes))

        file_log.info(f"{len(results)=}")
        return results
        # file_log.info(results)

    def serialize_obsidian_note(self, file_path: Path) -> Note:
        current_note = Note(file_path)

        with open(file_path, mode="r", encoding="utf-8") as file:
            file_content = file.read()

        frontmatter_props = np.get_note_frontmatter(file_content)
        serialized_fm_props = self.special_properties_handler(frontmatter_props)
        # current_tags = set(serialized_fm_props["tags"]) if "tags" in serialized_fm_props else {}

        file_log.debug(f"{serialized_fm_props=}")

        for tag in serialized_fm_props.get("tags", []):
            current_note.add_tag(tag, Link("frontmatter"))

        for alias in serialized_fm_props.get("aliases", []):
            current_note.add_alias(alias, Link("frontmatter"))

        # Add back in the additional Properties we'd like to persist on the Note Object
        added_fm_props = self.add_file_type_properties(file_path)
        current_note.set_modified_time(added_fm_props["modified_time"])

        idx = np.where_does_frontmatter_stop(file_content)
        note_content = file_content[idx:]

        splits = self.splitter.split_string(note_content)

        for chunk_idx, chunk in enumerate(splits):
            current_split = Split(chunk_idx, chunk)
            if self._embedder:
                current_split.set_embedding(self._embedder)

            for line in chunk.split("\n"):
                for tag_it in np.get_tags_from_line(line):
                    # current_tags.add(tag_it)

                    current_note.add_tag(tag_it, Link("inline"))
                    current_split.add_tag(tag_it, Link("inline"))

                links = np.get_wikilinks(line, file_path)

                for wikilink in links:
                    if wikilink.is_link_to_chunk():
                        current_note.add_outgoing_chunk_link(wikilink)
                        current_split.add_outgoing_chunk_link(wikilink)

                    current_note.add_outgoing_note_link(wikilink)
                    current_split.add_outgoing_note_link(wikilink)

            current_note.add_split(current_split)

        if self._embedder:
            current_note.set_embedding(self._embedder)
        return current_note

    def build_fm_tag_relations(self, tags: List[str]) -> Dict[str, List[Link]]:
        return {tag: [Link("frontmatter")] for tag in tags}

    def special_properties_handler(self, fm_properties: Dict[str, Any]) -> Dict[str, Any]:
        key_map = {}
        key_map["tag"] = "tags"
        key_map["alias"] = "aliases"

        content_map = {}
        content_map["id"] = lambda x: f"OBS_{x}"
        content_map["tags"] = np.extract_tags_from_yaml

        serialized_properties = {}
        for name, contents in fm_properties.items():
            serial_name = key_map[name] if name in key_map else name
            serialized_properties[serial_name] = content_map[serial_name](contents) if serial_name in content_map else contents

        return serialized_properties

    def add_file_type_properties(self, path: Path) -> Dict[str, Any]:
        added_fm_properties = {}
        # https://unix.stackexchange.com/questions/398838/is-ctime-of-find-the-creation-time
        modified_time = datetime.datetime.fromtimestamp(path.stat().st_ctime, tz=datetime.timezone.utc)
        added_fm_properties["modified_time"] = modified_time
        return added_fm_properties

    def obsidian_url(self, name: str, vault: str, note_ext_type: str = ".md") -> str:
        return f"obsidian://open?vault={quote(vault)}&file={quote(name)}{note_ext_type}"


if __name__ == "__main__":
    print("Quacks like a duck, looks like a goose.")
    # event_handler = PatternMatchingEventHandler(patterns=["*.md"], case_sensitive=True)
    # observer = Observer()
    # path_to_notes = ""

    event_handler = None
    splitter = MarkdownThenNLTKSentWithLinkMasking()

    path_to_notes = "/home/xoph/ObsidianVaults.git/nodes_all_the_way_down/Slip Box"
    gd = GraphDog(path_to_notes=path_to_notes, event_handler=event_handler)
    gd.sync_database_with_notes()
