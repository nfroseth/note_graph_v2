import os
from pathlib import Path
import time
from typing import Callable, List, Optional, Set
import logging
import socket

from neomodel import db, config
from watchdog.events import FileSystemEvent

from world_graph.neo_model_schema import FilledNeoNote, NeoNote, DanglingNeoNote
from world_graph.objects import GraphEventHandler, Note, Split
from world_graph.read_obs_file import GraphDog

log_file_path = Path("")
logging.getLogger("neo4j").setLevel(logging.WARNING)

RUN_PRUNE_ON_OUT_OF_SYNC = True


def create_neo_model_connection(clear_on_connect: bool = False):
    use_desktop = True
    local_network_port = f"{socket.gethostname()}.local:7687" if use_desktop else "127.0.0.1:7687"
    # URI = f"bolt://{local_network_port}"

    url = os.getenv("NEO4J_URI", local_network_port)
    username = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "neo4jneo4j")

    # driver = GraphDatabase.driver(url, auth=(username, password), telemetry_disabled=True)
    config.DATABASE_URL = f"bolt://{username}:{password}@{url}"

    if clear_on_connect:
        clear_database()


def clear_database():
    cypher = f"MATCH (n) DETACH DELETE n"
    db.cypher_query(cypher)


class NeoModelEventHandler(GraphEventHandler):
    def __init__(self, graphdog: GraphDog):
        self._graphdog = graphdog
        self._file_path_debouncing = {}

    def wrap_debouncing(self, function: Callable, threshold: float = 0.01) -> Callable:
        def _return(event: FileSystemEvent):
            event_path = Path(event.src_path)
            event_time = time.monotonic()

            if event_path in self._file_path_debouncing:
                gap = event_time - self._file_path_debouncing[event_path]

                if gap < threshold:
                    self._file_path_debouncing[event_path] = event_time

                    event_info = f"{event.__class__.__name__} {event.event_type} File: {event_path.name}"
                    logging.info(f"Gap of {round(gap, 2)} less than {threshold} (sec) For Event: {event_info}")

                    return lambda x: x

            self._file_path_debouncing[event_path] = event_time
            return function(event)

        return _return

    @property
    def graghdog(self) -> GraphDog:
        return self._graphdog

    def move_link(self, source_note: NeoNote, old_note: NeoNote, to_note: NeoNote) -> None:
        source_note.mentions.disconnect(old_note)
        source_note.mentions.connect(to_note)

    def promote_dangle_to_note(self, dangle: DanglingNeoNote, note: Note) -> FilledNeoNote:
        promoted_note = FilledNeoNote.from_note(note)
        for source_node in dangle.mentions.all():
            source_node.mentions.reconnect(dangle, promoted_note)

        dangle.delete()

        return promoted_note

    def has_incoming_link(self, note_with_path: NeoNote) -> bool:
        for source_or_target in set(note_with_path.mentions.all()):
            for rel in note_with_path.mentions.all_relationships(source_or_target):
                if rel.end_node() == note_with_path and rel.start_node() != note_with_path:  # Is the end the target, but not a self link?
                    assert not isinstance(rel.start_node(), DanglingNeoNote)  # Validate that Only FilledNeoNotes ever start links
                    return True
        return False

    def demote_note_to_dangle(self, dangle: DanglingNeoNote, neonote: FilledNeoNote) -> Optional[DanglingNeoNote]:
        rel_nodes = set(neonote.mentions.all())
        for source_or_target in rel_nodes:
            for rel in neonote.mentions.all_relationships(source_or_target):
                if rel.end_node() == neonote:
                    assert not isinstance(rel.start_node(), DanglingNeoNote)  # Validate that Only FilledNeoNotes ever start links
                    source_or_target.mentions.reconnect(neonote, dangle)

        neonote.remove()

        self.validate_unsupported_nodes(rel_nodes)
        return dangle

    def validate_unsupported_nodes(self, nodes_to_validate: Set[NeoNote]) -> None:
        for target_node in nodes_to_validate:
            # If the "targets" are Nodes which require support, validate they have that support, otherwise remove the node
            if isinstance(target_node, DanglingNeoNote) and len(target_node.mentions.all()) == 0:
                # This is the payoff, traverse the bi directional relationship, and if there are no relationships remove the node.
                target_node.delete()

    def create_dangle(self, name: str) -> DanglingNeoNote:
        return DanglingNeoNote(name=name).save()

    def on_created(self) -> Callable[[FileSystemEvent], NeoNote]:
        def _on_created(event: FileSystemEvent) -> NeoNote:
            event_path = Path(event.src_path)

            note_with_path = FilledNeoNote.nodes.get_or_none(path=str(event_path))
            if note_with_path:
                logging.critical("Error, Received a Create Event on already existing NeoNote. Deleting prior Note.")
                self.on_deleted()(MockFileSystemEvent(Path(event.src_path)))
                # Update Event

            ghost_note_with_name = DanglingNeoNote.nodes.get_or_none(name=event_path.stem)
            if ghost_note_with_name:
                note = self.graghdog.serialize_obsidian_note(event_path)
                neonote = self.promote_dangle_to_note(ghost_note_with_name, note)
            else:
                note = self.graghdog.serialize_obsidian_note(event_path)
                neonote = FilledNeoNote.from_note(note)

            for link in note.outgoing_links:
                linked_note_path = link.target
                root = self.graghdog.path_to_notes
                specific_path = root / linked_note_path

                pulled_on_path = FilledNeoNote.nodes.first_or_none(path=specific_path)
                if pulled_on_path:
                    neonote.mentions.connect(pulled_on_path)
                    if link.is_link_to_chunk():
                        pass
                else:
                    pulled_on_name = NeoNote.nodes.filter(name__iexact=linked_note_path.stem)
                    if len(pulled_on_name) == 0:
                        dangle = self.create_dangle(linked_note_path.stem)
                        neonote.mentions.connect(dangle)
                    elif len(pulled_on_name) > 1:
                        log_message = f"Failed to link of note path, then note name from {note.name} to the name: {linked_note_path.stem} \n"
                        log_message += f"There were {len(pulled_on_name)} candidates found. Please update this link. Check log file at {log_file_path} for more details."
                        logging.critical(log_message)
                        logging.debug(f"{str(pulled_on_name)=}")  # Change to go to Log File
                    else:
                        neonote.mentions.connect(pulled_on_name[0])
                        if link.is_link_to_chunk():
                            pass

            logging.info(f"Create Operation on {event_path.stem} completed.")
            return neonote

        return _on_created

    def on_modified(self) -> Callable[[FileSystemEvent], NeoNote]:
        def _on_modified(event: FileSystemEvent) -> NeoNote:
            event_path = Path(event.src_path)
            note_with_path = FilledNeoNote.nodes.get_or_none(path=str(event_path))
            if note_with_path is None:
                logging.critical(f"Database Out of Sync: Modified event triggered on Path does not exist.")
                return self.on_created()(MockFileSystemEvent(Path(event.src_path)))

            logging.info(f"Modified Operation on {event_path.stem} Started.")
            self.on_deleted()(MockFileSystemEvent(Path(event.src_path)))
            self.on_created()(MockFileSystemEvent(Path(event.src_path)))
            logging.info(f"Modified Operation on {event_path.stem} completed.")

        return _on_modified

    def prune(self):
        logging.warning("Running Prune is in-advised.")
        pass

    def on_deleted(self) -> Callable[[FileSystemEvent], Optional[DanglingNeoNote]]:
        # When deleting a FilledNeoNote, their Respective Splits needs to removed as well.
        def _on_deleted(event: FileSystemEvent) -> Optional[DanglingNeoNote]:
            event_path = Path(event.src_path)
            note_with_path = FilledNeoNote.nodes.get_or_none(path=str(event_path))
            if note_with_path is None:
                log_message = f"Database Out of Sync: Delete event triggered on Path which did not exist in database.\n"
                logging.critical(log_message)
                if RUN_PRUNE_ON_OUT_OF_SYNC:
                    log_message = f"Running clean up to prune orphans."
                    logging.critical(log_message)
                    self.prune()
                    logging.info(f"Delete Operation on {event_path.stem} completed.")
                    return

            if not self.has_incoming_link(note_with_path):
                nodes_needing_support = set(note_with_path.mentions.all())
                note_with_path.remove()
                self.validate_unsupported_nodes(nodes_needing_support)
                logging.info(f"Delete Operation on {event_path.stem} completed.")
                return

            dangle = self.create_dangle(event_path.stem)
            dangle = self.demote_note_to_dangle(dangle, note_with_path)
            logging.info(f"Delete Operation on {event_path.stem} completed.")
            return dangle

        return _on_deleted

    def on_moved(self) -> Callable[[FileSystemEvent], NeoNote]:
        def _on_moved(event: FileSystemEvent) -> NeoNote:
            event_path = Path(event.src_path)
            logging.info(f"Modified Operation on {event_path.stem} Started.")
            self.on_deleted()(MockFileSystemEvent(Path(event.src_path)))
            self.on_created()(MockFileSystemEvent(Path(event.dest_path)))
            logging.info(f"Modified Operation on {event_path.stem} completed.")

        return _on_moved

    def create_vector_index(
        self,
        name: str,
        node_type: str,
        embed_name: str = "content_embedding",
        dimension: int = 1028,
        sim_func: str = "cosine",
        m: int = 128,
        ef: int = 400,
    ):
        q = f"""
        CREATE VECTOR INDEX {name} IF NOT EXISTS
        FOR (n:{node_type}) ON (n.{embed_name})
        OPTIONS {{ indexConfig: {{
        `vector.dimensions`: $dimension,
        `vector.similarity_function`: $sim_func,
        `vector.hnsw.m`: $m,
        `vector.hnsw.ef_construction`: $ef
        }}}}"""
        q_param = {"dimension": dimension, "sim_func": sim_func, "m": m, "ef": ef}
        return db.cypher_query(q, params=q_param)

    def query_vector_index(self, q_embed: List[float], top_k: int = 5, node_type: Optional[str] = None, embed_name: str = "content_embedding"):
        node_type = f":{node_type}" if node_type else ""
        q = f"""
        MATCH (n{node_type})
        WITH n, vector.similarity.cosine(n.{embed_name}, $vector) AS similarity
        RETURN n, similarity
        ORDER BY similarity DESC
        LIMIT $top_k"""
        q_param = {"vector": q_embed, "top_k": top_k}
        return db.cypher_query(q, q_param, resolve_objects=True)


class MockFileSystemEvent:
    def __init__(self, path, dest_path=""):
        self.src_path = path
        self.dest_path = dest_path
        self.event_type = "Mock"


def main():
    print("Quacks like a duck. Looks like a goose.")


if __name__ == "__main__":
    exit(main())
