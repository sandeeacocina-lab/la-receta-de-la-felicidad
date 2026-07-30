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
MAX_RECIPE_INGREDIENT_LENGTH = 1000
DYNAMIC_LINK_MARKER = "data-dynamic-link-helper"
DYNAMIC_HREF_RE = re.compile(
    r'(?<![\w-])href=(?P<quote>["\'])(?P<value>\{\{\s*[^{}]+?\s*\}\})(?P=quote)',
    re.IGNORECASE,
)
CANONICAL_LINK_RE = re.compile(
    r"""<link\b(?=[^>]*\brel\s*=\s*["'][^"']*\bcanonical\b[^"']*["'])[^>]*>""",
    re.IGNORECASE,
)
LEGACY_REDIRECTS = {
    "en/2012/09/cheese-mini-donuts.html":
        "en/2012/05/cheese-donuts-breakfast-bars.html",
    "2009/06/charlotte-de-ensalada-de-canonigos-y.html":
        "2009/06/charlotte-de-ensalada-de-canonigos-y-gulas.html",
    "2013/10/tarta-de-chocolate-sencilla-sin-huevos-ni-lacteos.html":
        "2013/10/tarta-de-chocolate-sin-huevos-ni-lacteos.html",
    "2008/11/ny-cheesecake-de-frambuesa.html":
        "2008/11/new-york-cheesecake.html",
    "en/2012/10/chocolate-spoons.html":
        "en/2012/05/hot-chocolate-spoons.html",
    "en/2012/05/lattice-pie-crust-cookie.html":
        "en/2012/05/Lattice-Pie-Crust-Cookie.html",
    "2011/10/bizocho-chocolate-patata.html":
        "2011/10/bizcocho-chocolate-patata.html",
    "2011/04/gominolas-100-fruta.html":
        "2011/04/golosinas-fruta.html",
    "2013/09/mi-libro-las-recetas-de-la-felicidad.html":
        "mis-libros/",
    "2012/05/pinata-cupcakes.html":
        "2012/05/pinata-cupcakes-2.html",
    "en/2012/10/homemade-mikado-sticks.html":
        "en/2012/05/homemade-mikado-and-autumn-pizza.html",
    "2015/02/galletas-de-aceite-y-concurso-de-san-valentin.html":
        "2015/02/galletas-de-aceite.html",
    "2011/05/no-come-huevos-cookies-de-huevo-cocido.html":
        "2011/05/cookies-chips-chocolate-huevo-cocido.html",
}
DYNAMIC_LINK_HELPER = f"""<script {DYNAMIC_LINK_MARKER}>
(function () {{
  function syncDynamicLinks(root) {{
    var links = [];
    if (root.matches && root.matches('a[data-dynamic-href]')) links.push(root);
    if (root.querySelectorAll) {{
      links = links.concat(Array.prototype.slice.call(root.querySelectorAll('a[data-dynamic-href]')));
    }}
    links.forEach(function (link) {{
      var href = link.getAttribute('data-dynamic-href');
      if (href && href.indexOf('{{{{') === -1) link.setAttribute('href', href);
    }});
  }}

  syncDynamicLinks(document);
  new MutationObserver(function (records) {{
    records.forEach(function (record) {{
      if (record.type === 'attributes') syncDynamicLinks(record.target);
      Array.prototype.forEach.call(record.addedNodes || [], function (node) {{
        if (node.nodeType === 1) syncDynamicLinks(node);
      }});
    }});
  }}).observe(document.documentElement, {{
    subtree: true,
    childList: true,
    attributes: true,
    attributeFilter: ['data-dynamic-href']
  }});
}})();
</script>"""


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


def clean_recipe_ingredients(
    values: list[str],
    instructions: list[str],
) -> list[str]:
    """Remove preparation text captured by malformed legacy ingredient tags."""
    result: list[str] = []
    for value in unique(values):
        for instruction in instructions:
            instruction_index = value.find(instruction)
            if instruction_index <= 0:
                continue
            value = re.sub(
                r"\s*(?:Preparación|Preparation|Directions)\s*$",
                "",
                value[:instruction_index],
                flags=re.IGNORECASE,
            )
            value = clean_text(value)
            break
        if not value or value in result:
            continue
        if len(value) > MAX_RECIPE_INGREDIENT_LENGTH:
            raise ValueError(
                "Ingrediente demasiado largo después de limpiar el contenido: "
                f"{value[:120]!r}"
            )
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
        self.category_parts: list[str] = []
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
            if tag == "div" and "cats" in classes:
                self._capture(entry, self.category_parts)
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
    categories = unique(
        re.split(r"\s*[·|]\s*", clean_text("".join(parser.category_parts)))
    )
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
        instructions = unique(record.instructions)
        ingredients = clean_recipe_ingredients(record.ingredients, instructions)
        if ingredients:
            recipe["recipeIngredient"] = ingredients
        if instructions:
            recipe["recipeInstructions"] = instructions
        if categories:
            recipe["keywords"] = ", ".join(categories)
            recipe["recipeCategory"] = categories
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


def protect_dynamic_links(path: Path) -> tuple[bool, int]:
    original = path.read_text(encoding="utf-8")
    document, replacements = DYNAMIC_HREF_RE.subn(
        lambda match: (
            f'href="#" data-dynamic-href='
            f'{match.group("quote")}{match.group("value")}{match.group("quote")}'
        ),
        original,
    )
    has_dynamic_links = 'data-dynamic-href="' in document or "data-dynamic-href='" in document
    if has_dynamic_links and DYNAMIC_LINK_MARKER not in document:
        document, body_replacements = re.subn(
            r"\s*</body>",
            "\n" + DYNAMIC_LINK_HELPER + "\n</body>",
            document,
            count=1,
            flags=re.IGNORECASE,
        )
        if body_replacements != 1:
            raise ValueError(f"No se encontró </body> en {path}")

    if document != original:
        path.write_text(document, encoding="utf-8", newline="\n")
        return True, replacements
    return False, replacements


def ensure_page_canonical(path: Path, site_root: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    if CANONICAL_LINK_RE.search(original):
        return False

    canonical = canonical_for(path, site_root)
    addition = f'\n<link rel="canonical" href="{html.escape(canonical, quote=True)}">\n'
    document, replacements = re.subn(
        r"\s*</head>",
        addition + "</head>",
        original,
        count=1,
        flags=re.IGNORECASE,
    )
    if replacements != 1:
        raise ValueError(f"No se encontró </head> en {path}")
    path.write_text(document, encoding="utf-8", newline="\n")
    return True


def write_redirect_page(path: Path, target: str, language: str = "es") -> Path:
    redirect = f'''<!doctype html>
<html lang="{language}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Página trasladada · La Receta de la Felicidad</title>
<link rel="canonical" href="{html.escape(target, quote=True)}">
<meta http-equiv="refresh" content="0; url={html.escape(target, quote=True)}">
<script>window.location.replace({json.dumps(target)});</script>
</head>
<body>
<p>Esta página se ha trasladado a <a href="{html.escape(target, quote=True)}">su dirección actual</a>.</p>
</body>
</html>
'''
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(redirect, encoding="utf-8", newline="\n")
    return path


def write_author_redirect(site_root: Path) -> Path:
    target = AUTHOR_URL
    path = site_root / "sandra-mangas" / "index.html"
    return write_redirect_page(path, target)


def write_legacy_redirects(site_root: Path) -> list[Path]:
    written: list[Path] = []
    for old_relative, new_relative in LEGACY_REDIRECTS.items():
        target = urljoin(SITE_URL, new_relative)
        language = "en" if old_relative.startswith("en/") else "es"
        written.append(
            write_redirect_page(site_root.joinpath(*old_relative.split("/")), target, language)
        )
    return written


def main() -> int:
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("site_root", type=Path)
    args = argument_parser.parse_args()
    site_root = args.site_root.resolve()
    if not (site_root / "index.html").is_file():
        raise SystemExit(f"No parece un sitio válido: {site_root}")

    changed = 0
    dynamic_pages = 0
    dynamic_links = 0
    canonical_pages = 0
    recipe_items = 0
    for path in sorted(site_root.rglob("*.html")):
        dynamic_changed, dynamic_count = protect_dynamic_links(path)
        dynamic_pages += int(dynamic_changed)
        dynamic_links += dynamic_count
        was_changed, item_count = update_recipe_page(path, site_root)
        canonical_changed = ensure_page_canonical(path, site_root)
        canonical_pages += int(canonical_changed)
        changed += int(dynamic_changed or was_changed or canonical_changed)
        recipe_items += item_count
    redirect = write_author_redirect(site_root)
    legacy_redirects = write_legacy_redirects(site_root)
    print(
        f"SEO preparado: {changed} páginas actualizadas, "
        f"{recipe_items} recetas modernas, {canonical_pages} canónicas añadidas, "
        f"{dynamic_links} enlaces dinámicos protegidos en {dynamic_pages} páginas, "
        f"redirección {redirect.relative_to(site_root)} y "
        f"{len(legacy_redirects)} redirecciones históricas"
    )
    if recipe_items == 0:
        raise SystemExit("No se generó ningún dato estructurado de receta")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


