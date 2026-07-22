#!/usr/bin/env python3
"""Prepare migrated recipe pages for modern search engines."""

from __future__ import annotations

import argparse
import html
import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urljoin


SITE_URL = "https://larecetadelafelicidad.com/"
AUTHOR_URL = urljoin(SITE_URL, "sobre-la-autora/")
JSONLD_START = "<!-- seo-recipe-jsonld:start -->"
JSONLD_END = "<!-- seo-recipe-jsonld:end -->"
JSONLD_RE = re.compile(
    re.escape(JSONLD_START) + r".*?" + re.escape(JSONLD_END),
    re.DOTALL,
)
CLASS_RE = re.compile(r"\sclass=(['\"])(.*?)\1", re.IGNORECASE | re.DOTALL)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        value = clean_text(value)
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


@dataclass
class RecipeRecord:
    name_parts: list[str] = field(default_factory=list)
    ingredients: list[str] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)
    yield_parts: list[str] = field(default_factory=list)
    prep_time: str | None = None
    cook_time: str | None = None
    images: list[tuple[int, str]] = field(default_factory=list)

    @property
    def name(self) -> str:
        return clean_text("".join(self.name_parts))

    @property
    def recipe_yield(self) -> str:
        value = clean_text("".join(self.yield_parts))
        return re.sub(
            r"^(?:raciones|porciones|serves|yield)\s*:\s*",
            "",
            value,
            flags=re.IGNORECASE,
        )


class RecipeHTMLParser(HTMLParser):
    VOID_TAGS = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[dict] = []
        self.captures: list[dict] = []
        self.has_hrecipe = False
        self.description = ""
        self.canonical = ""
        self.h1_parts: list[str] = []
        self.page_images: list[tuple[int, str]] = []
        self.records: list[RecipeRecord] = []
        self.legacy = RecipeRecord()

    def _inside_tag(self, tag: str) -> bool:
        return any(entry["tag"] == tag for entry in self.stack)

    def _inside_class(self, class_name: str) -> bool:
        return any(class_name in entry["classes"] for entry in self.stack)

    def _active_record(self) -> RecipeRecord:
        for entry in reversed(self.stack):
            if entry.get("record") is not None:
                return entry["record"]
        return self.legacy

    def _capture(self, entry: dict, destination: list[str]) -> None:
        capture = {"destination": destination, "parts": []}
        entry["captures"].append(capture)
        self.captures.append(capture)

    def _start(self, tag: str, attrs) -> None:
        tag = tag.lower()
        attributes = {str(key).lower(): (value or "") for key, value in attrs}
        classes = set(attributes.get("class", "").split())
        inside_hrecipe = self._inside_class("hrecipe") or "hrecipe" in classes
        if "hrecipe" in classes:
            self.has_hrecipe = True

        entry = {"tag": tag, "classes": classes, "captures": [], "record": None}
        if tag == "div" and "recipe" in classes and inside_hrecipe:
            entry["record"] = RecipeRecord()
            self.records.append(entry["record"])

        active = entry["record"] or self._active_record()

        if tag == "meta" and attributes.get("name", "").lower() == "description":
            self.description = clean_text(attributes.get("content", ""))
        if tag == "link" and "canonical" in attributes.get("rel", "").lower().split():
            self.canonical = attributes.get("href", "").strip()

        if tag == "img" and self._inside_tag("article"):
            source = attributes.get("src", "").strip()
            if source:
                priority = 0 if "photo" in classes else 1
                self.page_images.append((priority, source))
                if active is not self.legacy:
                    active.images.append((priority, source))

        if tag not in self.VOID_TAGS:
            self.stack.append(entry)

            if tag == "h1":
                self._capture(entry, self.h1_parts)
            if "fn" in classes:
                self._capture(entry, active.name_parts)
            if tag == "li" and "ingredient" in classes:
                self._capture(entry, active.ingredients)
            elif tag == "li" and self._inside_class("instructions"):
                self._capture(entry, active.instructions)
            if tag == "p" and "yield" in classes:
                self._capture(entry, active.yield_parts)

        title = attributes.get("title", "").strip()
        if title and "value-title" in classes:
            if self._inside_class("preptime"):
                active.prep_time = title
            elif self._inside_class("cooktime"):
                active.cook_time = title

    def handle_starttag(self, tag: str, attrs) -> None:
        self._start(tag, attrs)

    def handle_startendtag(self, tag: str, attrs) -> None:
        self._start(tag, attrs)
        if tag.lower() not in self.VOID_TAGS:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        for capture in self.captures:
            capture["parts"].append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        match_index = None
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                match_index = index
                break
        if match_index is None:
            return
        closing = self.stack[match_index:]
        del self.stack[match_index:]
        for entry in reversed(closing):
            for capture in entry["captures"]:
                capture["destination"].append(clean_text("".join(capture["parts"])))
                if capture in self.captures:
                    self.captures.remove(capture)


def canonical_for(path: Path, site_root: Path) -> str:
    relative = path.relative_to(site_root).as_posix()
    if relative == "index.html":
        relative = ""
    elif relative.endswith("/index.html"):
        relative = relative[: -len("index.html")]
    return urljoin(SITE_URL, quote(relative, safe="/%-.~"))


def remove_hrecipe_class(document: str) -> str:
    def replace(match: re.Match[str]) -> str:
        tokens = match.group(2).split()
        if "hrecipe" not in {token.lower() for token in tokens}:
            return match.group(0)
        remaining = [token for token in tokens if token.lower() != "hrecipe"]
        return f" class={match.group(1)}{' '.join(remaining)}{match.group(1)}" if remaining else ""

    return CLASS_RE.sub(replace, document)


def best_image(record: RecipeRecord, page_images: list[tuple[int, str]], canonical: str) -> str:
    candidates = record.images or page_images
    if not candidates:
        return ""
    _, source = sorted(enumerate(candidates), key=lambda item: (item[1][0], item[0]))[0][1]
    image = urljoin(canonical, source)
    if image.startswith("http://"):
        image = "https://" + image[len("http://") :]
    return image


def recipe_jsonld(parser: RecipeHTMLParser, canonical: str) -> list[dict]:
    page_name = clean_text("".join(parser.h1_parts))
    description = parser.description or page_name
    records = parser.records or [parser.legacy]
    result: list[dict] = []

    for record in records:
        name = record.name or page_name
        image = best_image(record, parser.page_images, canonical)
        if not name or not image:
            continue
        recipe: dict = {
            "@type": "Recipe",
            "name": name,
            "image": [image],
            "author": {
                "@type": "Person",
                "name": "Sandra Mangas",
                "url": AUTHOR_URL,
            },
            "description": description,
            "url": canonical,
            "mainEntityOfPage": canonical,
        }
        ingredients = unique(record.ingredients)
        instructions = unique(record.instructions)
        if ingredients:
            recipe["recipeIngredient"] = ingredients
        if instructions:
            recipe["recipeInstructions"] = [
                {"@type": "HowToStep", "text": instruction}
                for instruction in instructions
            ]
        if record.recipe_yield:
            recipe["recipeYield"] = record.recipe_yield
        if record.prep_time:
            recipe["prepTime"] = record.prep_time
        if record.cook_time:
            recipe["cookTime"] = record.cook_time
        result.append(recipe)
    return result


def update_recipe_page(path: Path, site_root: Path) -> tuple[bool, int]:
    original = path.read_text(encoding="utf-8")
    document = JSONLD_RE.sub("", original)
    parser = RecipeHTMLParser()
    parser.feed(document)
    parser.close()
    if not parser.has_hrecipe:
        return False, 0

    canonical = parser.canonical or canonical_for(path, site_root)
    recipes = recipe_jsonld(parser, canonical)
    document = remove_hrecipe_class(document)

    additions: list[str] = []
    if not parser.canonical:
        additions.append(f'<link rel="canonical" href="{html.escape(canonical, quote=True)}">')
    if recipes:
        payload: dict
        if len(recipes) == 1:
            payload = {"@context": "https://schema.org", **recipes[0]}
        else:
            payload = {"@context": "https://schema.org", "@graph": recipes}
        json_text = json.dumps(payload, ensure_ascii=False, indent=2).replace("</", "<\\/")
        additions.append(
            f'{JSONLD_START}\n<script type="application/ld+json">\n{json_text}\n</script>\n{JSONLD_END}'
        )

    if additions:
        block = "\n" + "\n".join(additions) + "\n"
        document, replacements = re.subn(
            r"\s*</head>",
            block + "</head>",
            document,
            count=1,
            flags=re.IGNORECASE,
        )
        if replacements != 1:
            raise ValueError(f"No se encontró </head> en {path}")

    if document != original:
        path.write_text(document, encoding="utf-8", newline="\n")
        return True, len(recipes)
    return False, len(recipes)


def write_author_redirect(site_root: Path) -> Path:
    target = AUTHOR_URL
    redirect = f'''<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sandra Mangas · La Receta de la Felicidad</title>
<link rel="canonical" href="{target}">
<meta http-equiv="refresh" content="0; url={target}">
<script>window.location.replace({json.dumps(target)});</script>
</head>
<body>
<p>Esta página se ha trasladado a <a href="{target}">Sobre la autora</a>.</p>
</body>
</html>
'''
    path = site_root / "sandra-mangas" / "index.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(redirect, encoding="utf-8", newline="\n")
    return path


def main() -> int:
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("site_root", type=Path)
    args = argument_parser.parse_args()
    site_root = args.site_root.resolve()
    if not (site_root / "index.html").is_file():
        raise SystemExit(f"No parece un sitio válido: {site_root}")

    changed = 0
    recipe_items = 0
    for path in sorted(site_root.rglob("*.html")):
        was_changed, item_count = update_recipe_page(path, site_root)
        changed += int(was_changed)
        recipe_items += item_count
    redirect = write_author_redirect(site_root)
    print(
        f"SEO preparado: {changed} páginas actualizadas, "
        f"{recipe_items} recetas modernas y redirección {redirect.relative_to(site_root)}"
    )
    if recipe_items == 0:
        raise SystemExit("No se generó ningún dato estructurado de receta")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

