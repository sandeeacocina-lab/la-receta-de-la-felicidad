from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse


MONTHS_ES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def page_path(root: Path, permalink: str) -> Path:
    relative = urlparse(permalink).path.lstrip("/")
    if not relative.endswith(".html") or ".." in Path(relative).parts:
        raise ValueError(f"Permalink no vÃ¡lido: {permalink}")
    return root / relative


def relative_prefix(target: Path, root: Path) -> str:
    depth = len(target.relative_to(root).parts) - 1
    return "../" * depth


def rewrite_local_assets(article: str, prefix: str) -> str:
    article = re.sub(
        r'(?P<attr>href|src)=(?P<quote>["\'])wp-content/',
        lambda match: (
            f'{match.group("attr")}={match.group("quote")}'
            f'{prefix}wp-content/'
        ),
        article,
        flags=re.IGNORECASE,
    )
    return article


def text_excerpt(article: str, limit: int = 160) -> str:
    text = re.sub(r"<[^>]+>", " ", article)
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return text[:limit].rsplit(" ", 1)[0] if len(text) > limit else text


def spanish_date(value: str) -> str:
    year, month, day = (int(part) for part in value.split("-"))
    return f"{day} {MONTHS_ES[month - 1]} {year}"


def render_spanish_page(root: Path, recipe: dict) -> tuple[Path, bool]:
    permalink = recipe.get("permalink")
    side = recipe.get("es")
    if not permalink or not side:
        raise ValueError(f"Receta espaÃ±ola incompleta: {recipe.get('slug')}")

    target = page_path(root, permalink)
    if target.exists():
        return target, False

    prefix = relative_prefix(target, root)
    title = str(side.get("title") or recipe.get("slug") or "Receta")
    article = rewrite_local_assets(str(side.get("html") or ""), prefix)
    description = text_excerpt(article)
    categories = side.get("cats") or []
    categories_html = " &middot; ".join(html.escape(str(cat)) for cat in categories)
    english_url = recipe.get("permalinkEn")
    alternate_head = (
        f'<link rel="alternate" hreflang="en" href="{html.escape(english_url, quote=True)}">'
        if english_url
        else ""
    )
    alternate_body = (
        f'<div class="langlink"><a href="{html.escape(english_url, quote=True)}">'
        'Read this recipe in English &#8594;</a></div>'
        if english_url
        else ""
    )

    document = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} Â· La Receta de la Felicidad</title>
<meta name="description" content="{html.escape(description, quote=True)}">
<link rel="canonical" href="{html.escape(permalink, quote=True)}">
{alternate_head}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Josefin+Sans:wght@300;400;600&family=Cormorant+Garamond:ital,wght@0,400;0,500;1,400;1,500&family=Lato:wght@300;400;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{prefix}static.css">
</head>
<body>
<header class="masthead"><a href="/"><img src="{prefix}wp-content/uploads/2016/02/logo.png" alt="La Receta de la Felicidad"></a></header>
<nav class="chalk"><a href="/">Inicio</a><span style="color:#6b6a63">|</span><a href="/">Recetas</a><span style="color:#6b6a63">|</span><a href="/">Sobre mÃ­</a><span style="color:#6b6a63">|</span><a href="/">Mis libros</a><span style="color:#6b6a63">|</span><a href="/">Contacto</a></nav>
<main class="wrap">
<div class="dateline"><div class="rule"></div><div class="d">{spanish_date(recipe['date'])}</div><div class="rule"></div></div>
<h1>{html.escape(title)}</h1>
<div class="cats">{categories_html}</div>
{alternate_body}
<article class="rx">{article}</article>
</main>
<footer><div class="t">La Receta de la Felicidad</div><div class="s">Sandra Mangas Â· larecetadelafelicidad.com</div></footer>
</body>
</html>
"""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(document, encoding="utf-8", newline="\n")
    return target, True


def add_to_sitemap(root: Path, recipes: list[dict]) -> int:
    sitemap_path = root / "sitemap.xml"
    sitemap = sitemap_path.read_text(encoding="utf-8")
    additions: list[str] = []

    for recipe in recipes:
        permalink = recipe.get("permalink")
        if not permalink or f"<loc>{permalink}</loc>" in sitemap:
            continue
        english_url = recipe.get("permalinkEn")
        alternates = (
            f'<xhtml:link rel="alternate" hreflang="es" href="{html.escape(permalink, quote=True)}"/>'
            + (
                f'<xhtml:link rel="alternate" hreflang="en" href="{html.escape(english_url, quote=True)}"/>'
                if english_url
                else ""
            )
        )
        additions.append(
            f'<url><loc>{html.escape(permalink)}</loc>'
            f'<lastmod>{html.escape(str(recipe.get("date") or ""))}</lastmod>'
            f'{alternates}</url>'
        )

    if additions:
        sitemap = sitemap.replace("</urlset>", "".join(additions) + "</urlset>")
        sitemap_path.write_text(sitemap, encoding="utf-8", newline="\n")
    return len(additions)


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    recipes = json.loads((root / "recipes.json").read_text(encoding="utf-8"))
    generated: list[str] = []

    for recipe in recipes:
        target, created = render_spanish_page(root, recipe)
        if created:
            generated.append(target.relative_to(root).as_posix())

    sitemap_additions = add_to_sitemap(root, recipes)
    print(
        json.dumps(
            {
                "generated": generated,
                "generated_count": len(generated),
                "sitemap_additions": sitemap_additions,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
