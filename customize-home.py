from pathlib import Path
import re


page = Path("_site/index.html")
html = page.read_text(encoding="utf-8")

analytics_tag = '  <script defer src="/analytics.js"></script>\n'
if analytics_tag.strip() not in html:
    if "</head>" not in html:
        raise ValueError("No se encontró </head> en la portada")
    html = html.replace("</head>", analytics_tag + "</head>", 1)

other_sites = """          <div style="flex: 1; background: #c5bda9; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; padding: 13px 20px; text-align: center;">
            <span style="font-family: 'Josefin Sans', sans-serif; font-weight: 300; font-size: 14px; letter-spacing: 0.14em; text-transform: uppercase; color: #4a5a70;">{{ boxOther }}</span>
            <div style="display: flex; flex-wrap: wrap; align-items: center; justify-content: center; gap: 4px 12px; font-family: 'Cormorant Garamond', serif; font-style: italic; font-size: 15px; line-height: 1.25;">
              <a href="https://sandramangas.com/" target="_blank" rel="noopener noreferrer" style="color: #5d5548;">sandramangas.com</a>
              <a href="https://happycupcakes.lovable.app/" target="_blank" rel="noopener noreferrer" style="color: #5d5548;">Happy Cupcakes</a>
              <a href="https://polosyhelados.lovable.app/" target="_blank" rel="noopener noreferrer" style="color: #5d5548;">Polos y helados</a>
              <a href="https://conlacomidasisejuega.lovable.app/es" target="_blank" rel="noopener noreferrer" style="color: #5d5548;">Con la comida sí se juega</a>
            </div>
          </div>
"""

if "https://happycupcakes.lovable.app/" not in html:
    old_card = re.compile(
        r'          <a href="\{\{ madeMailto \}\}"[\s\S]*?          </a>\r?\n'
    )
    html, replacements = old_card.subn(other_sites, html, count=1)
    if replacements != 1:
        raise ValueError("No se encontró el bloque que debe convertirse en Mis otras webs")

html = html.replace(
    "      boxMade: es ? '\\u00bfHas hecho alguna receta mia?' : 'Have you made one of my recipes?',",
    "      boxOther: es ? 'Mis otras webs y libros interactivos' : 'My other websites and interactive books',",
    1,
)
html = re.sub(r"\n      madeMailto: .*?,", "", html, count=1)
html = re.sub(r"\n      boxMadeSub: .*?,", "", html, count=1)

page.write_text(html, encoding="utf-8")
