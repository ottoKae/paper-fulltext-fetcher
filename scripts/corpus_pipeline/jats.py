from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .common import atomic_write_bytes, atomic_write_text, clean_text


ENTITY_DECLARATION = re.compile(br"<!ENTITY\s", re.I)
REFERENCE_HEADING = re.compile(
    r"^(references|bibliography|literature cited|works cited|参考文献)\b", re.I
)
CONTENT_TAGS = {"article-title", "title", "p", "caption", "td", "th", "kwd", "mixed-citation"}
SECTION_TAGS = {"sec", "ref-list"}


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def element_text(element: ET.Element) -> str:
    return clean_text(" ".join(part.strip() for part in element.itertext() if part.strip()))


def _strip_namespaces(element: ET.Element) -> None:
    for item in element.iter():
        if isinstance(item.tag, str):
            item.tag = local_name(item.tag)
        normalized: dict[str, str] = {}
        for key, value in item.attrib.items():
            normalized.setdefault(local_name(key), value)
        item.attrib.clear()
        item.attrib.update(normalized)


def _article_root(source: Path) -> tuple[ET.Element, str]:
    value = source.read_bytes()
    if ENTITY_DECLARATION.search(value):
        raise ValueError("XML entity declarations are not accepted in corpus preparation")
    root = ET.fromstring(value)
    if local_name(root.tag) == "article":
        mode = "native_jats"
        article = root
    else:
        articles = [item for item in root.iter() if local_name(item.tag) == "article"]
        if len(articles) != 1:
            raise ValueError(f"expected exactly one JATS article, found {len(articles)}")
        mode = "unwrapped_oai_jats"
        article = articles[0]
    _strip_namespaces(article)
    return article, mode


def _immediate_title(element: ET.Element) -> str:
    for child in list(element):
        if local_name(child.tag) == "title":
            return element_text(child)
    return ""


def xpath_rows(article: ET.Element) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def walk(element: ET.Element, xpath: str, sections: list[str]) -> None:
        tag = local_name(element.tag)
        current_sections = list(sections)
        if tag in SECTION_TAGS:
            title = _immediate_title(element)
            if not title and tag == "ref-list":
                title = "References"
            if title:
                current_sections.append(title)
        descendants = list(element.iter())[1:]
        contains_selected_child = any(local_name(item.tag) in CONTENT_TAGS for item in descendants)
        text = element_text(element)
        if tag in CONTENT_TAGS and text and not contains_selected_child:
            section_path = " > ".join(current_sections)
            rows.append(
                {
                    "xpath": xpath,
                    "label": tag,
                    "section_path": section_path,
                    "text": text,
                    "is_reference": bool(
                        any(REFERENCE_HEADING.match(value.strip()) for value in current_sections)
                    ),
                }
            )
        counts: dict[str, int] = {}
        for child in list(element):
            child_tag = local_name(child.tag)
            counts[child_tag] = counts.get(child_tag, 0) + 1
            walk(child, f"{xpath}/{child_tag}[{counts[child_tag]}]", current_sections)

    walk(article, "/article[1]", [])
    return rows


def prepare_jats(source: Path, target: Path, source_map: Path | None = None) -> tuple[Path, str, list[dict[str, Any]]]:
    article, mode = _article_root(source)
    # Docling identifies JATS from the DOCTYPE marker. The marker has no URL,
    # declares no entities and is parsed with Docling's no-network JATS backend.
    value = (
        b'<?xml version="1.0" encoding="utf-8"?>\n'
        b'<!DOCTYPE article SYSTEM "JATS-archive">\n'
        + ET.tostring(article, encoding="utf-8")
    )
    if not target.exists() or target.read_bytes() != value:
        atomic_write_bytes(target, value)
    rows = xpath_rows(article)
    if source_map is not None:
        atomic_write_text(
            source_map,
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        )
    return target, mode, rows
