import itertools
from pathlib import Path
from pprint import pprint
import re
from typing import Any, Dict, List, Optional, Set, Tuple
import yaml
import os
import logging

from rich.logging import RichHandler
import nltk

from world_graph.read_backwards import reverse_readline
from world_graph.objects import Link, ObsidianLink


# Configure the logger with RichHandler
logging.basicConfig(level=logging.INFO, format="%(message)s", datefmt="[%X]", handlers=[RichHandler(rich_tracebacks=True)])

parse_log = logging.getLogger("rich_logger")


def does_not_start_with_frontmatter(file_contents: str) -> bool:
    return len(file_contents) < 4 or (len(file_contents) >= 4 and file_contents[:4] != f"---{os.linesep}")


def get_note_frontmatter(file_contents: str) -> Dict[str, Any]:
    if does_not_start_with_frontmatter(file_contents):
        parse_log.debug(f"No property start token '---' at start of file. Stopping.")
        return {}

    lines = file_contents.split(os.linesep)

    yaml_property_lines = ""
    for idx, line in enumerate(lines[1:], start=1):
        if line == "---":
            parse_log.debug(f"Found end of properties token '---' on line: {idx}. Stopping.")
            return yaml.safe_load(yaml_property_lines)
        yaml_property_lines += line + "\n"
    else:
        parse_log.warning(f"EOF and no end of properties token '---' found.")
        return {}


def where_does_frontmatter_stop(file_contents: str) -> int:
    """
    Args:
        file_contents: the str containing the note

    Returns:
        int: The index where the frontmatter properties stop
    """
    if does_not_start_with_frontmatter(file_contents):
        return 0

    fm_token = f"{os.linesep}---{os.linesep}"
    end_idx = file_contents.find(fm_token, 4) + len(fm_token)
    return end_idx if end_idx != -1 else 0


def extract_tags_from_yaml(yaml_tags: List[str] | str) -> Set[str]:
    if isinstance(yaml_tags, str):
        yaml_tags = [single_tag for single_tag in re.split(", | ", yaml_tags)]
        return extract_hierarchical_tags_from_list(yaml_tags)

    if isinstance(yaml_tags, List) and all([isinstance(tag, str) for tag in yaml_tags]):
        return extract_hierarchical_tags_from_list(yaml_tags)

    return []


def extract_hierarchical_tags_from_list(tag_list: List[str]) -> Set[str]:
    tags = set()
    for single_tag in tag_list:
        hierarchical_split = single_tag.split("/")
        for i, j in itertools.combinations(range(len(hierarchical_split) + 1), 2):
            if i == 0:
                tag = "/".join(hierarchical_split[i:j])
                tags.add(tag)
    return tags


def obsidian_specific_rule_sentence_splitter_nltk(text: str) -> List[str]:
    """
    Splits text into sentences while preserving the integrity of [[wikilinks]],
    even if they contain full sentences or punctuation.

    Args:
        text (str): The input text to split.

    Returns:
        List[str]: A list of sentences with [[wikilinks]] preserved.
    """
    # Regex to match [[wikilinks]] with any content inside
    wikilink_pattern = r"\[\[.*?\]\]"

    # Placeholder for wikilinks to prevent splitting inside them
    wikilink_placeholders = []
    placeholder_token = "WIKILINK_PLACEHOLDER_{}"

    def replace_wikilinks(match):
        wikilink_placeholders.append(match.group(0))
        return placeholder_token.format(len(wikilink_placeholders) - 1)

    # Replace all [[wikilinks]] with placeholders
    text_with_placeholders = re.sub(wikilink_pattern, replace_wikilinks, text)

    sentences = nltk.sent_tokenize(text_with_placeholders)

    restored_sentences = []
    for s in sentences:
        for index, wikilink in enumerate(wikilink_placeholders):
            s = s.replace(placeholder_token.format(index), wikilink)
        else:
            restored_sentences.append(s)

    return restored_sentences


# https://help.obsidian.md/Editing+and+formatting/Tags#Tag+format
def get_tags_from_line(line: str) -> List[str]:
    """
    Extract tags from a given line of text based on specific formatting rules.

    A valid tag:
    - Starts with a `#`.
    - May include `/` for hierarchy (e.g., `#tag/child`).
    - Ends when encountering specific punctuation or whitespace.

    Args:
        line (str): The input line from which to extract tags.

    Returns:
        List[str]: A list of extracted tags without the leading `#`.
    """
    # Characters that signal the end of a tag
    TAG_PUNCTUATION = {
        "#",
        "$",
        "!",
        ".",
        ",",
        "?",
        ":",
        ";",
        "`",
        " ",
        "+",
        "=",
        "|",
        "\\",
        os.linesep,
    }

    # Initialize variables
    tags = []  # List to store extracted tags
    candidate_tag = ""  # Current tag being built
    tag_start_pos = 0  # Starting position of the current candidate tag
    is_valid_tag = False  # Indicates if the candidate tag is valid
    lower_line = line.lower()  # Convert the line to lowercase for case-insensitive processing

    # Iterate through each character in the line
    for idx, char in enumerate(lower_line):
        # Check if we're processing a tag or starting a new one
        does_cand_start_with_tag = candidate_tag.startswith("#")

        if char == "#" or does_cand_start_with_tag:
            # Update the start position of the current tag
            tag_start_pos = idx - len(candidate_tag)

            # Handle the end of a valid tag
            if char in TAG_PUNCTUATION and is_valid_tag:
                # Confirm the tag is valid and preceded by a space or at the start of the line
                if tag_start_pos == 0 or lower_line[tag_start_pos - 1] == " ":
                    tags.append(candidate_tag[1:])  # Add the tag (exclude `#`)
                candidate_tag = ""  # Reset candidate tag
                is_valid_tag = False  # Reset validity flag
            elif char in TAG_PUNCTUATION:
                candidate_tag = ""  # Discard invalid candidate tag
            elif char == "/" and candidate_tag != "#":
                # Allow hierarchy but not for `#/`
                tags.append(candidate_tag[1:])

            # Update the validity flag for the candidate tag
            is_valid_tag = char.isalpha() or char == "/" or is_valid_tag
            candidate_tag += char  # Append the character to the candidate tag

    # Handle any remaining candidate tag after the loop
    if candidate_tag.startswith("#") and is_valid_tag and (tag_start_pos == 0 or lower_line[tag_start_pos - 1] == " "):
        tags.append(candidate_tag[1:])

    return tags


WIKILINK_PATTERN = re.compile(r"\[\[(.*?)\]\]")


def get_links(content: str, source_path: Path, chunk_idx: int) -> List[Link]:
    # Internal
    # Look for all Markdown links
    # Look for all Wikilinks

    # External
    # Look for all External Links
    return get_wikilinks(content, source_path, chunk_idx)


def get_markdown_links() -> List[Link]:
    pass


def get_external_links() -> List[Link]:
    pass


def bottom_up_block_tag_extract(content: str) -> List[str]:
    # reverse_readline()
    pass


def get_wikilinks(content: str, source_path: Path) -> List[ObsidianLink]:
    found_links = re.findall(WIKILINK_PATTERN, content)
    parsed_links = []

    for wikilink in found_links:
        link = parse_wikilink_simple(wikilink)
        parse_log.debug(f"From {source_path.stem} found link: {link.target}")
        parsed_links.append(link)

    return parsed_links


def parse_wikilink_simple(between_brackets: str) -> ObsidianLink:
    link_split = between_brackets.split("|", 1)
    wikilink_url = link_split[0]
    wikilink_display_text = link_split[1] if len(link_split) > 1 else None

    wikilink_section_split = wikilink_url.split("#")
    header_path = wikilink_section_split[1:]

    block_hash = None
    if len(header_path) > 0:
        block_split = header_path[0].split("^", 1)
        block_hash = block_split[1] if len(block_split) > 1 else None

    # path_split = wikilink_section_split[0].split("/")
    target_path = Path(wikilink_section_split[0])

    return ObsidianLink("Wikilink", target=target_path, display_text=wikilink_display_text, headers=header_path, block_hash=block_hash)


def parse_wikilink(between_brackets: str, note_title: str, content: str, chunk_idx: int) -> Optional[Link]:
    # Note Titles cannot have the following \ / :
    # Obsidian warns about # ^ [ ] |
    # File name cannot contain any of the following characters: * " \ / < > : | ?
    title = note_title
    block_hash = ""
    display_text = ""
    blacklisted_chars = {"\\", ":", "*", '"', "<", ">", "?"}
    invalid_link = any([c in blacklisted_chars for c in between_brackets])

    if invalid_link:
        parse_log.warning(f"Found blacklisted character(s) {blacklisted_chars} in link {between_brackets}")
        # return None

    # Parse the link components
    first_pipe = between_brackets.find("|")
    if first_pipe == -1:
        note_location = between_brackets
    else:
        display_text = between_brackets[first_pipe + 1 :]
        note_location = between_brackets[:first_pipe]

    path_relative_to_vault = None
    last_slash = note_location.rfind("/")
    if last_slash != -1:
        path_relative_to_vault = Path(note_location)
        note_location = note_location[last_slash + 1 :]

    first_carrot = note_location.find("^")
    if first_carrot != -1:
        block_hash = note_location[first_carrot + 1 :]
        note_location = note_location[:first_carrot]

    headers = note_location.split("#")

    # Determine display text
    if not display_text:
        if title != note_title and len(headers) > 1:
            display_text = f"{title} > {headers[-1]}"
        elif title == note_title:
            display_text = headers[-1]
        else:
            display_text = title

    if not path_relative_to_vault:
        path_relative_to_vault = Path(headers[-1])

    # Create and return the Link object
    properties = {
        "source_note": title,
        "target_note": path_relative_to_vault,
        "context": content,
        "headers": headers,
        "chunk_index": chunk_idx,
        "link_display_text": display_text,
        "block_hash": block_hash,
    }

    return ObsidianLink("inline", properties)

    # TODO: How should the title(#header) piece be used when creating link
    # Very large Notes are split up with headers, so they maybe their own nodes
    # Lastly the ^ operator allows for links to specific blocks of text to
    # more specific.
    # https://help.obsidian.md/Linking+notes+and+files/Internal+links#Link+to+a+block+in+a+note

    # Currently Tackling this issue, I'll wait to handle the ^ block link operator, but I'd
    # like to be able to link to a the "Closest" Chunk within a Note if it's available.
    # It'll depend upon the chunking strategy
    # Note A, Chunk 3 -> Note B, Chunk 4, Chunk 5, Chunk 6
    # Philosophy, be as specific as possible when linking to another note, as expansion strategies can
    # consider what to do with something too specific.


def test_wikilink_examples():
    wikilink_examples = [
        # Simple wikilinks
        "This is a simple link [[SimpleLink]].",
        # Wikilink with a header
        "Linking to a specific section [[Note#Header]].",
        # Wikilink with a block reference
        "A reference to a block [[Note^blockID]].",
        # Wikilink with both header and block reference
        "Linking to a header and block [[Note#Header^blockID]].",
        # Wikilink with display text
        "This is a [[Note|Custom Display Text]].",
        # Duplicate Notes force the user to define the full path of the note.
        "Example with duplicate names [[00 - Slip Box/Inbox/12-1-24|12-1-24]],",
        # Multiple wikilinks in a single line
        "Here are two links: [[FirstLink]] and [[SecondLink]].",
        # Nested wikilinks (invalid)
        "This has nested [[Wikilinks [[InsideAnotherLink]]]].",
        # Malformed wikilinks (extra pipes)
        "A malformed link with too many pipes [[Note#Header|Display|Extra]].",
        # Multiple headers in the same wikilink
        "Multiple headers in a wikilink [[Note#Header1#Header2]].",
        # No wikilinks in text
        "This sentence contains no wikilinks.",
        # Wikilink at the beginning of the text
        "[[StartingLink]] is the first word.",
        # Wikilink at the end of the text
        "The last word is a [[EndingLink]].",
        # Wikilink with unusual characters
        "This contains unusual characters [[Link/With:Unusual#Characters]].",
        # Edge case with special characters but still valid
        "Valid link with special characters stripped [[Link-With-Special-Chars]].",
        # Unbalanced brackets
        "This has unbalanced brackets [[UnbalancedLink.",
        # Empty wikilink
        "An empty wikilink [[]].",
        # Spaces in titles (valid)
        "Link with spaces [[Link With Spaces]].",
        # Tab or newline around wikilinks
        "Tabs or newlines before and after links \t[[TabbedLink]]\n.",
        # Complex embedded scenario
        "Complex case: [[ParentLink#Header^blockID|Custom Display Text]] followed by [[AnotherLink]].",
    ]
    for line in wikilink_examples:
        parse_log.info(get_wikilinks(line, "Test", 0))


if __name__ == "__main__":
    line = "Example with duplicate names [[00 - Slip Box/Inbox/12-1-24|12-1-24]]."
    parse_log.info(get_wikilinks(line, "Test_name", 0))
