from abc import ABC
from typing import List
from neomodel import db
from neomodel import (
    StructuredRel,
    StructuredNode,
    StringProperty,
    IntegerProperty,
    ArrayProperty,
    FloatProperty,
    Relationship,
    UniqueIdProperty,
    DateTimeProperty,
    FulltextIndex,
)

from world_graph.objects import Note, Split


class Folder(StructuredNode):
    pass


class Tag(StructuredNode):
    pass


class Link(StructuredRel):
    pass


class ObsidianLink(Link):
    uid = UniqueIdProperty()
    format_type = StringProperty()
    display_text = StringProperty()


class NeoSplit(StructuredNode):
    count = IntegerProperty()
    name = StringProperty()
    content = StringProperty(fulltext_index=FulltextIndex(analyzer="english", eventually_consistent=True))
    content_embedding = ArrayProperty(FloatProperty())

    next = Relationship("NeoSplit", "NEXT_SPLIT")

    @classmethod
    def from_split(cls, split: Split):
        kwargs = {
            "count": split.count,
            "name": split.name,
            "content": split.content,
            "content_embedding": split.embedding,
        }
        return cls(**kwargs)


class NeoNote(StructuredNode):
    name = StringProperty()
    mentions = Relationship("NeoNote", "MENTIONED", model=ObsidianLink)


class DanglingNeoNote(NeoNote):
    name = StringProperty(unique_index=True)

    def __hash__(self):
        return hash(self.name)


class FilledNeoNote(NeoNote):
    path = StringProperty(unique_index=True)
    content = StringProperty(fulltext_index=FulltextIndex(analyzer="english", eventually_consistent=True))
    content_embedding = ArrayProperty(FloatProperty())
    modified_time = DateTimeProperty()

    head = Relationship("NeoSplit", "HEAD_SPLIT")
    contain = Relationship("NeoSplit", "CONTAIN_SPLIT")

    def __hash__(self):
        return hash(self.path)

    @classmethod
    # @db.transaction
    def from_note(cls, note: Note):
        kwargs = {
            "path": note.path,
            "content": note.content,
            "name": note.name,
            "modified_time": note.modified_time,
            "content_embedding": note.embedding,
        }
        neonote = cls(**kwargs).save()
        splits = neonote.create_splits(note.splits)

        previous_split = None
        for idx, split in enumerate(splits):
            if idx == 0:
                neonote.head.connect(split)
            else:
                previous_split.next.connect(split)
            neonote.contain.connect(split)
            previous_split = split

        return neonote

    def create_splits(self, splits: List[Split]) -> List[NeoSplit]:
        return [NeoSplit.from_split(split).save() for split in splits]

    def remove(self):
        splits_to_delete = self.contain.all()
        for split in splits_to_delete:
            split.delete()
        self.delete()
