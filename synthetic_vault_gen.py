from collections import deque
from contextlib import chdir
import random
from pathlib import Path
import sys
import time
from sh import git

# from git import Repo


# Parameters
class SyntheticVault:
    # fmt: off
    animals = [
            "Aardvark", "Albatross", "Alligator", "Antelope", "Armadillo", "Barnacle", "Bat", "Bear",
            "Beaver", "Bee", "Beetle", "Bison", "Buffalo", "Butterfly", "Camel", "Centipede",
            "Chameleon", "Cheetah", "Chimpanzee", "Clam", "Coral", "Coyote", "Crab", "Crane",
            "Cricket", "Crocodile", "Deer", "Dingo", "Dolphin", "Dragonfly", "Duck", "Eagle",
            "Elephant", "Elk", "Falcon", "Flamingo", "Fox", "Frog", "Gazelle", "Giraffe",
            "Goose", "Gorilla", "Grasshopper", "Hawk", "Hippopotamus", "Hummingbird", "Hyena",
            "Iguana", "Jaguar", "Jellyfish", "Kangaroo", "Koala", "Kookaburra", "Ladybug",
            "Lemur", "Leopard", "Lion", "Lobster", "Lynx", "Manatee", "Meerkat", "Millipede",
            "Moose", "Moth", "Narwhal", "Octopus", "Orangutan", "Otter", "Owl", "Panda", "Parrot",
            "Peacock", "Pelican", "Penguin", "Platypus", "Porcupine", "Pufferfish", "Rabbit",
            "Raven", "Rhinoceros", "Salamander", "Scorpion", "Sea Urchin", "Seahorse", "Seal",
            "Shark", "Shrimp", "Sloth", "Slug", "Snail", "Snake", "Spider", "Squirrel",
            "Starfish", "Stingray", "Swan", "Tapir", "Tiger", "Toucan", "Turtle", "Vulture",
            "Walrus", "Wasp", "Whale", "Wolf", "Woodpecker", "Zebra"
        ]

    tags = [
        "Mammals", "Birds", "Reptiles", "Amphibians", "Fish", "Invertebrates", "Marine Animals",
        "Insects", "Arachnids", "Crustaceans", "Myriapods", "Mollusks"
    ]
    # fmt: on
    def __init__(self, path: str):
        self._path = Path(path) / "notes"
        self._link_density = 3
        self._notes_written = {}

    def generate(self, num_notes: int = 50) -> None:
        while len(self.animals) < num_notes:
            self.animals += [f"Animal_{i}" for i in range(len(self.animals), num_notes + 1)]

        # Directory setup
        self._path.mkdir(parents=True, exist_ok=True)

        note_filenames = [f"{animal}.md" for animal in random.sample(self.animals, k=num_notes)]
        note_queue = deque(note_filenames)

        while note_queue:
            filename = note_queue.popleft()
            animal_name = Path(filename).stem
            # Generate links
            links = random.sample(note_filenames, k=random.randint(1, self._link_density))
            wikilinks = [f"[[{Path(link).stem}#Section-{random.randint(1, 3)}]]" for link in links]

            # Content creation
            content = f"# {animal_name}\n\n"
            content += "## Overview\n\n"
            content += f"This note contains an overview of {animal_name}.\n\n"
            content += "### Section-1\n\n"
            content += "Example Food\n\n"
            content += "### Section-2\n\n"
            content += "Example Habitat\n\n"
            content += "### Section-3\n\n"
            content += "Example Behaviors\n\n"
            content += "## Related Links\n\n"
            content += "Explore related animals:\n\n"
            content += "\n".join(wikilinks) + "\n\n"
            content += "## Details\n\n"
            content += f"This section dives deeper into the details about {animal_name}.\n"

            # Write file
            note_path = self._path / filename
            time.sleep(0.5)
            with open(note_path, "w") as note_file:
                note_file.write(content)

            self._notes_written[filename] = content

    @classmethod
    def with_git_repo(cls, path: str):
        vault = cls(path)
        notes = Path(path)
        notes.mkdir(parents=True, exist_ok=True)
        with chdir(notes):
            git.init(_out=sys.stdout, _err=sys.stderr)
            vault.generate()
            git.add("*.md", _out=sys.stdout, _err=sys.stderr)
            git.commit("-m", "Animal-themed markdown notes", _out=sys.stdout, _err=sys.stderr)

        return vault

    def remove_vault(self):
        for note in self._path.glob("*.md"):
            note.unlink()
        self._path.rmdir()


def main():
    path = "/home/xoph/repos/github/nfroseth/world_graph_ai_context/world_graph/src_v2/zoo"
    vault = SyntheticVault.with_git_repo(path)
    # vault.remove_vault()
    # vault.generate(num_notes=20)


if __name__ == "__main__":
    exit(main())
