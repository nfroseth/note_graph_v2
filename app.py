from pathlib import Path

import logging
import readline

from neomodel import config, db
from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer

from world_graph.utils import time_function
from world_graph.neo_model_handler import MockFileSystemEvent, NeoModelEventHandler, create_neo_model_connection
from world_graph.read_obs_file import GraphDog
from world_graph.chunking import MarkdownThenNLTKSentWithLinkMasking
from world_graph.embedding import load_embedding_model


@time_function
def start_sync(handle, vault_path):
    for idx, path in enumerate(Path(vault_path).rglob("*.md")):
        handle.on_created()(MockFileSystemEvent(path))


@time_function
def main():
    vault_path = "/home/xoph/repos/github/nfroseth/world_graph_ai_context/world_graph/src_v2/zoo"

    create_neo_model_connection()
    embedding, dim = load_embedding_model()
    splitter = MarkdownThenNLTKSentWithLinkMasking()
    gd = GraphDog(vault_path, None, splitter, embedding)

    handle = NeoModelEventHandler(gd)

    event_handler = PatternMatchingEventHandler(patterns=["*.md"], case_sensitive=True)
    observer = Observer()

    event_handler.on_created = handle.on_created()
    event_handler.on_deleted = handle.on_deleted()
    event_handler.on_modified = handle.on_modified()
    event_handler.on_moved = handle.on_moved()

    observer.schedule(event_handler, path=Path(vault_path), recursive=True)
    observer.start()

    # start_sync(handle, vault_path)

    handle.create_vector_index("FilledNeoNode_content_embedding_mxbai_large", node_type="FilledNeoNote")
    handle.create_vector_index("NeoSplit_content_embedding_mxbai_large", node_type="NeoSplit")

    try:
        print("Stream is active!")
        while True:
            user_input = input("Q:")
            q_embed = embedding.embed_query(user_input)
            results, meta = handle.query_vector_index(q_embed, top_k=8, node_type="FilledNeoNote")
            for row in results:
                print(row[0].name, row[1])
    except KeyboardInterrupt:
        observer.stop()
    except Exception as e:
        db.close_connection()
        raise e

    db.close_connection()


if __name__ == "__main__":
    exit(main())
