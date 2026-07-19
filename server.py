from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote, quote
from pathlib import Path
from datetime import datetime
import html
import json
import mimetypes
import os
import re
import socket
import threading
import uuid
import webbrowser

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
PAGES = DATA / "pages"
UPLOADS = DATA / "uploads"
STATIC = BASE / "static"
CATEGORIES_FILE = DATA / "categories.json"
FAVORITES_FILE = DATA / "favorites.json"
RECENTS_FILE = DATA / "recents.json"
APP_VERSION = "12.0-lanzador-python"
DEFAULT_CATEGORIES = ["General", "Documentación", "Splunk"]

for folder in (DATA, PAGES, UPLOADS, STATIC):
    folder.mkdir(parents=True, exist_ok=True)


def slugify(text: str) -> str:
    text = str(text).strip().lower()
    for a, b in {"á":"a","é":"e","í":"i","ó":"o","ú":"u","ü":"u","ñ":"n"}.items():
        text = text.replace(a, b)
    return re.sub(r"[^a-z0-9_-]+", "-", text).strip("-") or "pagina"


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, value) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def page_file(slug: str) -> Path:
    return PAGES / f"{slugify(slug)}.json"


def load_page(slug: str):
    data = read_json(page_file(slug), None)
    return data if isinstance(data, dict) else None


def all_pages():
    pages = []
    for path in PAGES.glob("*.json"):
        page = load_page(path.stem)
        if page:
            pages.append(page)
    return sorted(pages, key=lambda p: p.get("title", "").casefold())


def save_page(title: str, category: str, content: str, tags: str = "", template: str = ""):
    title = title.strip()
    slug = slugify(title)
    old = load_page(slug) or {}
    now = datetime.now().isoformat(timespec="seconds")
    tag_list = sorted({x.strip() for x in tags.split(",") if x.strip()}, key=str.casefold)
    data = {
        "slug": slug,
        "title": title,
        "category": category.strip() or "General",
        "tags": tag_list,
        "template": template.strip(),
        "content": content.replace("\r\n", "\n"),
        "created": old.get("created", now),
        "updated": now,
        "views": int(old.get("views", 0)),
    }
    write_json(page_file(slug), data)
    ensure_category(data["category"])
    return data


def load_categories():
    categories = read_json(CATEGORIES_FILE, [])
    values = {str(x).strip() for x in categories if str(x).strip()} if isinstance(categories, list) else set()
    values.update(DEFAULT_CATEGORIES)
    values.update(p.get("category", "").strip() for p in all_pages() if p.get("category", "").strip())
    clean = sorted(values, key=str.casefold)
    write_json(CATEGORIES_FILE, clean)
    return clean


def save_categories(values):
    clean = sorted({str(x).strip() for x in values if str(x).strip()}, key=str.casefold)
    write_json(CATEGORIES_FILE, clean)


def ensure_category(category: str):
    category = category.strip()
    if not category:
        return
    categories = load_categories()
    if category.casefold() not in {x.casefold() for x in categories}:
        categories.append(category)
        save_categories(categories)


def load_favorites():
    values = read_json(FAVORITES_FILE, [])
    return [slugify(x) for x in values] if isinstance(values, list) else []


def save_favorites(values):
    write_json(FAVORITES_FILE, sorted(set(values)))


def add_recent(slug: str):
    values = read_json(RECENTS_FILE, [])
    if not isinstance(values, list):
        values = []
    slug = slugify(slug)
    values = [x for x in values if x != slug]
    values.insert(0, slug)
    write_json(RECENTS_FILE, values[:12])


def recent_pages(limit=6):
    slugs = read_json(RECENTS_FILE, [])
    result = []
    for slug in slugs if isinstance(slugs, list) else []:
        page = load_page(slug)
        if page:
            result.append(page)
        if len(result) >= limit:
            break
    return result


def escape_inline(text: str) -> str:
    text = html.escape(text)
    text = re.sub(
        r"\[\[imagen:([^\]|]+)(?:\|([^\]]+))?\]\]",
        lambda m: (
            f'<figure class="wiki-image"><img src="/uploads/{html.escape(Path(m.group(1).strip()).name, quote=True)}" '
            f'alt="{html.escape((m.group(2) or m.group(1)).strip(), quote=True)}" loading="lazy">'
            f'<figcaption>{html.escape((m.group(2) or "").strip())}</figcaption></figure>'
        ), text, flags=re.I,
    )
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"''(.+?)''", r"<em>\1</em>", text)
    text = re.sub(r"~~(.+?)~~", r"<del>\1</del>", text)
    text = re.sub(r"`([^`]+)`", r"<code class=\"inline-code\">\1</code>", text)
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", lambda m: f'<a href="/wiki/{slugify(html.unescape(m.group(1)))}">{m.group(2)}</a>', text)
    text = re.sub(r"\[\[([^\]]+)\]\]", lambda m: f'<a href="/wiki/{slugify(html.unescape(m.group(1)))}">{m.group(1)}</a>', text)
    text = re.sub(r"\[(https?://[^\s\]]+)\s+([^\]]+)\]", r'<a href="\1" target="_blank" rel="noopener">\2</a>', text)
    return text


def highlight_code(source: str, language: str) -> str:
    lang = (language or "text").lower()
    escaped = html.escape(source)
    tokens = []

    def protect(pattern, css_class, text, flags=0):
        def repl(match):
            token = chr(0xE000 + len(tokens))
            tokens.append(f'<span class="tok-{css_class}">{match.group(0)}</span>')
            return token
        return re.sub(pattern, repl, text, flags=flags)

    if lang == "json":
        escaped = protect(r'&quot;(?:\\.|[^&])*?&quot;(?=\s*:)', "key", escaped)
        escaped = protect(r'&quot;(?:\\.|[^&])*?&quot;', "string", escaped)
        escaped = protect(r'\b(?:true|false|null)\b', "keyword", escaped, re.I)
        escaped = protect(r'(?<![\w])[-+]?\d+(?:\.\d+)?', "number", escaped)
    elif lang in ("python", "py"):
        escaped = protect(r'&quot;(?:\\.|[^&])*?&quot;|&#x27;(?:\\.|[^&])*?&#x27;', "string", escaped)
        escaped = protect(r'(?m)#.*$', "comment", escaped)
        escaped = protect(r'\b(?:False|None|True|and|as|assert|async|await|break|class|continue|def|del|elif|else|except|finally|for|from|global|if|import|in|is|lambda|nonlocal|not|or|pass|raise|return|try|while|with|yield)\b', "keyword", escaped)
        escaped = protect(r'\b(?:print|len|range|str|int|float|list|dict|set|tuple|open|super|self)\b', "builtin", escaped)
        escaped = protect(r'(?<![\w])\d+(?:\.\d+)?', "number", escaped)
    elif lang in ("spl", "splunk"):
        escaped = protect(r'(?m)#.*$', "comment", escaped)
        escaped = protect(r'&quot;.*?&quot;|&#x27;.*?&#x27;', "string", escaped)
        escaped = protect(r'\|', "pipe", escaped)
        escaped = protect(r'\b(?:search|where|eval|stats|chart|timechart|table|fields|rename|sort|dedup|rex|regex|spath|lookup|inputlookup|outputlookup|eventstats|streamstats|transaction|bin|bucket|makeresults|append|appendcols|join|fillnull|addtotals|xyseries|mvexpand|mvjoin|mvcount|coalesce|count|sum|avg|min|max|dc|values|list|by|as|from)\b', "keyword", escaped, re.I)
        escaped = protect(r'\b(?:AND|OR|NOT|IN)\b', "operator", escaped)
        escaped = protect(r'(?<![\w])\d+(?:\.\d+)?', "number", escaped)
    elif lang == "sql":
        escaped = protect(r'--.*$', "comment", escaped, re.M)
        escaped = protect(r'&quot;.*?&quot;|&#x27;.*?&#x27;', "string", escaped)
        escaped = protect(r'\b(?:SELECT|FROM|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|ON|GROUP|BY|ORDER|HAVING|INSERT|INTO|UPDATE|DELETE|CREATE|ALTER|DROP|TABLE|VIEW|AS|AND|OR|NOT|NULL|IS|IN|LIKE|DISTINCT|COUNT|SUM|AVG|MIN|MAX|CASE|WHEN|THEN|ELSE|END|LIMIT)\b', "keyword", escaped, re.I)
        escaped = protect(r'(?<![\w])\d+(?:\.\d+)?', "number", escaped)
    elif lang in ("powershell", "ps1"):
        escaped = protect(r'(?m)#.*$', "comment", escaped)
        escaped = protect(r'&quot;.*?&quot;|&#x27;.*?&#x27;', "string", escaped)
        escaped = protect(r'\$[A-Za-z_][\w:]*', "variable", escaped)
        escaped = protect(r'\b(?:function|param|if|elseif|else|foreach|for|while|switch|return|try|catch|finally|throw|class|filter|begin|process|end)\b', "keyword", escaped, re.I)
        escaped = protect(r'\b[A-Za-z]+-[A-Za-z]+\b', "builtin", escaped)
    elif lang in ("html", "xml"):
        escaped = protect(r'&lt;!--.*?--&gt;', "comment", escaped, re.S)
        escaped = protect(r'&lt;/?[A-Za-z][^&]*?&gt;', "tag", escaped)
    elif lang in ("bash", "shell", "sh"):
        escaped = protect(r'(?m)#.*$', "comment", escaped)
        escaped = protect(r'&quot;.*?&quot;|&#x27;.*?&#x27;', "string", escaped)
        escaped = protect(r'\$\{?\w+\}?', "variable", escaped)
        escaped = protect(r'\b(?:if|then|else|elif|fi|for|while|do|done|case|esac|function|in|echo|export|source|cd|pwd|read)\b', "keyword", escaped)

    for i, value in enumerate(tokens):
        escaped = escaped.replace(chr(0xE000 + i), value)
    return escaped


def render(src: str) -> str:
    out, para, code = [], [], []
    in_code, language, list_tag = False, "", None

    def flush_para():
        nonlocal para
        if para:
            out.append("<p>" + escape_inline(" ".join(x.strip() for x in para)) + "</p>")
            para = []

    def close_list():
        nonlocal list_tag
        if list_tag:
            out.append(f"</{list_tag}>")
            list_tag = None

    for line in src.splitlines():
        if in_code:
            if line.strip() == "```":
                highlighted = highlight_code("\n".join(code), language)
                raw = html.escape("\n".join(code), quote=True)
                out.append(
                    f'<div class="code-wrap"><div class="code-head"><span>{html.escape(language or "código")}</span>'
                    f'<button type="button" class="copy-code" data-code="{raw}">Copiar</button></div>'
                    f'<pre class="code-box language-{html.escape(language or "text")}"><code>{highlighted}</code></pre></div>'
                )
                in_code, language, code = False, "", []
            else:
                code.append(line)
            continue

        stripped = line.strip()
        if stripped.startswith("```"):
            flush_para(); close_list(); in_code = True; language = stripped[3:].strip(); continue
        heading = re.match(r"^(={2,6})\s*(.*?)\s*\1$", stripped)
        if heading:
            flush_para(); close_list(); level = min(len(heading.group(1)), 6); title = heading.group(2)
            out.append(f'<h{level} id="{slugify(title)}">{escape_inline(title)}</h{level}>'); continue
        if stripped.startswith("!!! "):
            flush_para(); close_list(); parts = stripped[4:].split(" ", 1); kind = slugify(parts[0]); title = parts[1] if len(parts) > 1 else parts[0]
            out.append(f'<div class="admonition {kind}"><strong>{escape_inline(title)}</strong></div>'); continue
        if re.match(r"^\s*[-*]\s+", line):
            flush_para()
            if list_tag != "ul": close_list(); list_tag = "ul"; out.append("<ul>")
            out.append("<li>" + escape_inline(re.sub(r"^\s*[-*]\s+", "", line)) + "</li>"); continue
        if re.match(r"^\s*\d+\.\s+", line):
            flush_para()
            if list_tag != "ol": close_list(); list_tag = "ol"; out.append("<ol>")
            out.append("<li>" + escape_inline(re.sub(r"^\s*\d+\.\s+", "", line)) + "</li>"); continue
        if stripped.startswith(">"):
            flush_para(); close_list(); out.append("<blockquote>" + escape_inline(stripped[1:].strip()) + "</blockquote>"); continue
        if stripped == "----":
            flush_para(); close_list(); out.append("<hr>"); continue
        if not stripped:
            flush_para(); close_list(); continue
        para.append(line)

    flush_para(); close_list()
    if in_code:
        highlighted = highlight_code("\n".join(code), language)
        out.append(f'<pre class="code-box"><code>{highlighted}</code></pre>')
    return "\n".join(out)


def template_content(name: str) -> str:
    templates = {
        "procedimiento": """== Objetivo ==\n\nDescribe qué se quiere conseguir.\n\n== Requisitos ==\n\n- Acceso necesario\n- Permisos necesarios\n\n== Pasos ==\n\n1. Primer paso\n2. Segundo paso\n\n== Código o comandos ==\n\n```text\nComando o consulta\n```\n\n== Resultado esperado ==\n\nDescribe el resultado correcto.\n\n== Errores frecuentes ==\n\n!!! advertencia Precaución\nAñade aquí los riesgos o errores conocidos.\n\n== Rollback ==\n\nExplica cómo deshacer el cambio.\n""",
        "splunk": """== Objetivo de la búsqueda ==\n\n== Origen de datos ==\n\n- Índice:\n- Sourcetype:\n\n== Consulta SPL ==\n\n```spl\nindex=ejemplo\n| stats count by host\n| sort - count\n```\n\n== Campos de salida ==\n\n== Interpretación ==\n""",
        "incidencia": """== Resumen ==\n\n== Impacto ==\n\n== Línea temporal ==\n\n== Diagnóstico ==\n\n== Acciones realizadas ==\n\n== Solución ==\n\n== Prevención ==\n""",
    }
    return templates.get(name, "")


def sidebar(active=""):
    categories = load_categories()
    favorites = [load_page(x) for x in load_favorites()]
    favorites = [x for x in favorites if x]
    recents = recent_pages(5)
    cat_links = "".join(f'<a class="category-link" href="/category/{quote(c)}">{html.escape(c)}</a>' for c in categories)
    fav_links = "".join(f'<a href="/wiki/{p["slug"]}">★ {html.escape(p["title"])}</a>' for p in favorites) or '<span class="empty-menu">Sin favoritos</span>'
    recent_links = "".join(f'<a href="/wiki/{p["slug"]}">{html.escape(p["title"])}</a>' for p in recents) or '<span class="empty-menu">Sin páginas recientes</span>'
    return f'''<aside><nav>
<a class="home-link" href="/">⌂ Panel principal</a>
<a href="/new">＋ Nueva página</a>
<a href="/help">? Ayuda</a>
<div class="menu-title">Categorías</div><div class="category-menu">{cat_links}</div>
<a class="manage-link" href="/manage-categories">⚙ Gestionar categorías</a>
<div class="menu-title">Favoritos</div>{fav_links}
<div class="menu-title">Recientes</div>{recent_links}
</nav></aside>'''


def layout(title: str, body: str, active=""):
    return f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} · Wiki Procedimientos</title><link rel="stylesheet" href="/static/style.css?v={APP_VERSION}"></head>
<body><header><a class="brand" href="/">Wiki Procedimientos</a><form action="/search" method="get"><input name="q" placeholder="Buscar en títulos, contenido, categorías y etiquetas" required><button>Buscar</button></form></header>
<div class="shell">{sidebar(active)}<main>{body}</main></div><footer>Wiki local · Versión {APP_VERSION} · Python sin dependencias externas</footer>
<script src="/static/editor.js?v={APP_VERSION}"></script><script src="/static/preview.js?v={APP_VERSION}"></script></body></html>'''


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{datetime.now():%H:%M:%S}] {fmt % args}")

    def send_html(self, content, status=200):
        data = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers(); self.wfile.write(data)

    def send_json(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers(); self.wfile.write(data)

    def redirect(self, path):
        self.send_response(303); self.send_header("Location", path); self.end_headers()

    def read_form(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        return {k: v[-1] for k, v in parse_qs(raw, keep_blank_values=True).items()}

    def serve_file(self, path: Path):
        if not path.is_file():
            return self.send_error(404)
        data = path.read_bytes(); mime, _ = mimetypes.guess_type(str(path))
        self.send_response(200); self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff"); self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path); path = unquote(parsed.path); query = parse_qs(parsed.query)
        if path.startswith("/static/"):
            return self.serve_file(STATIC / Path(path[8:]).name)
        if path.startswith("/uploads/"):
            return self.serve_file(UPLOADS / Path(path[9:]).name)
        if path == "/": return self.dashboard()
        if path == "/new": return self.editor(None, query.get("template", [""])[0])
        if path == "/help": return self.help_page()
        if path == "/search": return self.search(query.get("q", [""])[0])
        if path == "/manage-categories": return self.manage_categories()
        if path.startswith("/category/"): return self.category_page(path.split("/category/",1)[1])
        if path.startswith("/wiki/"): return self.show_page(path.split("/wiki/",1)[1])
        if path.startswith("/edit/"): return self.editor(load_page(path.split("/edit/",1)[1]))
        self.send_html(layout("No encontrado", "<h1>Página no encontrada</h1>"), 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/upload-image": return self.handle_image_upload()
        if path == "/preview": return self.handle_preview()
        form = self.read_form()
        if path == "/save":
            page = save_page(form.get("title", ""), form.get("category", "General"), form.get("content", ""), form.get("tags", ""), form.get("template", ""))
            return self.redirect(f'/wiki/{page["slug"]}')
        if path == "/toggle-favorite":
            slug = slugify(form.get("slug", "")); values = load_favorites()
            values = [x for x in values if x != slug] if slug in values else values + [slug]
            save_favorites(values); return self.redirect(f"/wiki/{slug}")
        if path == "/add-category":
            ensure_category(form.get("name", "")); return self.redirect("/manage-categories")
        if path == "/rename-category":
            old, new = form.get("old", "").strip(), form.get("new", "").strip()
            if old and new:
                cats = [new if x.casefold() == old.casefold() else x for x in load_categories()]
                save_categories(cats)
                for page in all_pages():
                    if page.get("category", "").casefold() == old.casefold():
                        save_page(page["title"], new, page.get("content", ""), ",".join(page.get("tags", [])), page.get("template", ""))
            return self.redirect("/manage-categories")
        if path == "/delete-category":
            name, target = form.get("name", "").strip(), form.get("target", "General").strip() or "General"
            for page in all_pages():
                if page.get("category", "").casefold() == name.casefold():
                    save_page(page["title"], target, page.get("content", ""), ",".join(page.get("tags", [])), page.get("template", ""))
            save_categories([x for x in load_categories() if x.casefold() != name.casefold()]); ensure_category(target)
            return self.redirect("/manage-categories")
        self.send_error(404)

    def handle_preview(self):
        form = self.read_form()
        title = form.get("title", "").strip() or "Vista previa del documento"
        category = form.get("category", "").strip()
        tags = form.get("tags", "").strip()
        content = form.get("content", "")

        meta = []
        if category:
            meta.append(f'<span><strong>Categoría:</strong> {html.escape(category)}</span>')
        if tags:
            meta.append(f'<span><strong>Etiquetas:</strong> {html.escape(tags)}</span>')

        document = (
            '<article class="document-preview">'
            f'<h1>{html.escape(title)}</h1>'
            f'<div class="preview-meta">{"".join(meta)}</div>'
            f'<div class="wiki-content">{render(content)}</div>'
            '</article>'
        )

        preview_html = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vista previa</title>
<link rel="stylesheet" href="/static/style.css?v={APP_VERSION}">
<style>
html, body {{
  margin: 0;
  padding: 0;
  background: #fff;
}}
body {{
  min-height: 100vh;
}}
</style>
</head>
<body>
{document}
</body>
</html>"""
        self.send_html(preview_html)

    def dashboard(self):
        pages = all_pages(); categories = load_categories(); favorites = load_favorites()
        updated = sorted(pages, key=lambda p: p.get("updated", ""), reverse=True)[:8]
        cards = f'''<div class="stats"><div><strong>{len(pages)}</strong><span>Procedimientos</span></div><div><strong>{len(categories)}</strong><span>Categorías</span></div><div><strong>{len(favorites)}</strong><span>Favoritos</span></div><div><strong>{sum(int(p.get("views",0)) for p in pages)}</strong><span>Consultas</span></div></div>'''
        templates = '''<section><h2>Crear desde plantilla</h2><div class="template-grid"><a href="/new?template=procedimiento">📋 Procedimiento técnico</a><a href="/new?template=splunk">🔎 Búsqueda Splunk</a><a href="/new?template=incidencia">🚨 Informe de incidencia</a><a href="/new">📄 Página en blanco</a></div></section>'''
        recent = "".join(f'<li><a href="/wiki/{p["slug"]}">{html.escape(p["title"])}</a><small>{html.escape(p.get("category",""))} · {html.escape(p.get("updated","").replace("T"," "))}</small></li>' for p in updated) or "<li>No hay páginas todavía.</li>"
        body = f'<h1>Panel principal</h1>{cards}{templates}<section><h2>Últimas modificaciones</h2><ul class="dashboard-list">{recent}</ul></section>'
        self.send_html(layout("Panel principal", body))

    def show_page(self, slug):
        page = load_page(slug)
        if not page: return self.send_html(layout("No encontrado", "<h1>Página no encontrada</h1>"), 404)
        page["views"] = int(page.get("views", 0)) + 1; write_json(page_file(page["slug"]), page); add_recent(page["slug"])
        favorite = page["slug"] in load_favorites()
        tags = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in page.get("tags", []))
        related = [p for p in all_pages() if p["slug"] != page["slug"] and (p.get("category") == page.get("category") or set(p.get("tags", [])) & set(page.get("tags", [])))][:5]
        related_html = "".join(f'<li><a href="/wiki/{p["slug"]}">{html.escape(p["title"])}</a></li>' for p in related)
        body = f'''<div class="page-actions"><a href="/edit/{page['slug']}">Editar</a><form method="post" action="/toggle-favorite"><input type="hidden" name="slug" value="{page['slug']}"><button>{'★ Quitar favorito' if favorite else '☆ Añadir favorito'}</button></form></div>
<h1>{html.escape(page['title'])}</h1><div class="meta">Categoría: <a href="/category/{quote(page.get('category','General'))}">{html.escape(page.get('category','General'))}</a> · Actualizado: {html.escape(page.get('updated','').replace('T',' '))} · Visitas: {page['views']}</div><div class="tags">{tags}</div>
<article>{render(page.get('content',''))}</article><div class="category">Categoría: {html.escape(page.get('category','General'))}</div>
{f'<section class="related"><h2>También puede interesarte</h2><ul>{related_html}</ul></section>' if related_html else ''}'''
        self.send_html(layout(page["title"], body))

    def editor(self, page=None, template=""):
        if page is None:
            page = {"title":"", "category":"General", "content":template_content(template), "tags":[], "template":template}
        options = "".join(
            f'<option value="{html.escape(c, quote=True)}" {"selected" if c == page.get("category") else ""}>{html.escape(c)}</option>'
            for c in load_categories()
        )
        tags = ", ".join(page.get("tags", []))
        body = f"""<h1>{'Editar página' if page.get('title') else 'Crear página'}</h1>
<form class="editor" method="post" action="/save">
<input type="hidden" name="template" value="{html.escape(page.get('template',''), quote=True)}">

<div class="editor-meta-row">
<label class="editor-title-field">Título
<input id="editor-title" name="title" value="{html.escape(page.get('title',''), quote=True)}" required>
</label>
<label class="editor-category-field">Categoría
<select id="editor-category" name="category">{options}</select>
</label>
<label class="editor-tags-field">Etiquetas
<input id="editor-tags" name="tags" value="{html.escape(tags, quote=True)}" placeholder="splunk, correo, producción">
</label>
</div>

<div class="github-editor">
<div class="github-editor-tabs" role="tablist" aria-label="Modo del editor">
<button type="button" id="edit-tab" class="github-tab active" role="tab" aria-selected="true">Editar</button>
<button type="button" id="preview-tab" class="github-tab" role="tab" aria-selected="false">Vista previa</button>
</div>

<div id="edit-view" class="editor-tab-content active">
<div class="editor-toolbar" role="toolbar">
<button type="button" data-insert="== Título ==\n">Título</button>
<button type="button" data-wrap="**">Negrita</button>
<button type="button" data-wrap="''">Cursiva</button>
<button type="button" data-insert="- ">Lista</button>
<button type="button" data-insert="!!! nota Nota importante\n">Nota</button>
<button type="button" data-code="spl">Código SPL</button>
<button type="button" data-code="python">Código Python</button>
<button type="button" id="insert-image-button">🖼 Imagen</button>
<input id="image-file" type="file" accept=".png,.jpg,.jpeg,.gif,.webp,image/*" hidden>
<span id="image-upload-status" class="upload-status"></span>
</div>
<textarea id="content-editor" name="content" required>{html.escape(page.get('content',''))}</textarea>
</div>

<div id="preview-view" class="editor-tab-content" hidden>
<div id="preview-loading" class="preview-loading" hidden>Actualizando vista previa…</div>
<iframe id="preview-frame" title="Vista previa del documento"></iframe>
</div>
</div>

<div class="editor-footer">
<button class="primary">Guardar página</button>
<a href="/help" target="_blank">Ver ayuda de formato</a>
</div>
</form>"""
        self.send_html(layout("Editor", body))

    def search(self, query):
        q = query.strip().casefold(); results = []
        for p in all_pages():
            haystack = " ".join([p.get("title",""), p.get("category",""), p.get("content",""), " ".join(p.get("tags",[]))]).casefold()
            if q and q in haystack: results.append(p)
        items = "".join(f'<li><a href="/wiki/{p["slug"]}">{html.escape(p["title"])}</a><small>{html.escape(p.get("category",""))}</small><p>{html.escape(re.sub(r"\s+", " ", p.get("content", ""))[:180])}…</p></li>' for p in results)
        self.send_html(layout("Búsqueda", f'<h1>Resultados para “{html.escape(query)}”</h1><p>{len(results)} resultado(s).</p><ul class="search-results">{items or "<li>No se encontraron coincidencias.</li>"}</ul>'))

    def category_page(self, category):
        pages = [p for p in all_pages() if p.get("category", "").casefold() == category.casefold()]
        items = "".join(f'<li><a href="/wiki/{p["slug"]}">{html.escape(p["title"])}</a><small>{html.escape(p.get("updated","").replace("T"," "))}</small></li>' for p in pages)
        self.send_html(layout(category, f'<h1>Categoría: {html.escape(category)}</h1><ul class="page-list">{items or "<li>No hay páginas en esta categoría.</li>"}</ul>'))

    def manage_categories(self):
        categories = load_categories(); rows = []
        for c in categories:
            count = sum(1 for p in all_pages() if p.get("category","").casefold() == c.casefold())
            options = "".join(f'<option value="{html.escape(x, quote=True)}">{html.escape(x)}</option>' for x in categories if x.casefold() != c.casefold())
            rows.append(f'''<tr><td><strong>{html.escape(c)}</strong><br><small>{count} página(s)</small></td><td><form class="inline-form" method="post" action="/rename-category"><input type="hidden" name="old" value="{html.escape(c, quote=True)}"><input name="new" value="{html.escape(c, quote=True)}"><button>Renombrar</button></form></td><td><form class="inline-form" method="post" action="/delete-category"><input type="hidden" name="name" value="{html.escape(c, quote=True)}"><select name="target">{options or '<option value="General">General</option>'}</select><button class="danger">Eliminar y mover</button></form></td></tr>''')
        body = f'''<h1>Gestionar categorías</h1><form class="add-category" method="post" action="/add-category"><input name="name" placeholder="Nueva categoría" required><button>Crear categoría</button></form><table class="category-table"><thead><tr><th>Categoría</th><th>Renombrar</th><th>Eliminar</th></tr></thead><tbody>{''.join(rows)}</tbody></table>'''
        self.send_html(layout("Categorías", body))

    def help_page(self):
        body = '''<h1>Ayuda de edición</h1><h2>Títulos</h2><pre class="help-example"><code>== Título ==\n=== Subtítulo ===</code></pre><h2>Texto</h2><pre class="help-example"><code>**Negrita**\n''Cursiva''\n`código corto`</code></pre><h2>Código coloreado</h2><pre class="help-example"><code>```spl\nindex=correo\n| stats count by sender\n```</code></pre><p>Lenguajes: spl, python, powershell, sql, json, html, xml y bash.</p><h2>Imágenes dentro del cuerpo</h2><p>Coloque el cursor en el editor y pulse <strong>Imagen</strong>. También puede pegar una captura con Ctrl+V o arrastrarla sobre el editor.</p><pre class="help-example"><code>[[imagen:captura.png|Descripción]]</code></pre><h2>Avisos</h2><pre class="help-example"><code>!!! nota Información importante\n!!! advertencia Precaución</code></pre><h2>Enlaces</h2><pre class="help-example"><code>[[Otra página]]\n[[Otra página|Texto visible]]\n[https://ejemplo.com Sitio externo]</code></pre>'''
        self.send_html(layout("Ayuda", body))

    def handle_image_upload(self):
        content_type = self.headers.get("Content-Type", "")
        match = re.search(r'boundary="?([^";]+)', content_type)
        try: length = int(self.headers.get("Content-Length", "0"))
        except ValueError: length = 0
        if not match or length <= 0 or length > 9 * 1024 * 1024:
            return self.send_json({"ok":False,"error":"Carga no válida o demasiado grande."}, 400)
        raw = self.rfile.read(length); boundary = ("--" + match.group(1)).encode(); filename = ""; data = b""
        for part in raw.split(boundary):
            if b"\r\n\r\n" not in part: continue
            head, body = part.split(b"\r\n\r\n", 1)
            found = re.search(br'filename="([^"]*)"', head)
            if found:
                filename = Path(found.group(1).decode("utf-8", "replace")).name; data = body.rstrip(b"\r\n-"); break
        ext = Path(filename).suffix.lower(); allowed = {".png",".jpg",".jpeg",".gif",".webp"}
        if not filename or ext not in allowed or not data or len(data) > 8 * 1024 * 1024:
            return self.send_json({"ok":False,"error":"Use PNG, JPG, GIF o WEBP de hasta 8 MB."}, 400)
        signatures = {".png":b"\x89PNG", ".jpg":b"\xff\xd8\xff", ".jpeg":b"\xff\xd8\xff", ".gif":b"GIF8", ".webp":b"RIFF"}
        if not data.startswith(signatures[ext]):
            return self.send_json({"ok":False,"error":"El archivo no parece una imagen válida."}, 400)
        stored = f"{slugify(Path(filename).stem)[:60]}-{uuid.uuid4().hex[:8]}{ext}"; (UPLOADS / stored).write_bytes(data)
        self.send_json({"ok":True,"filename":stored})


def seed_examples():
    if not any(PAGES.glob("*.json")):
        save_page("Bienvenida", "General", "== Bienvenido ==\n\nEsta wiki funciona de forma local sin instalar librerías.\n\n- Cree categorías.\n- Use plantillas.\n- Inserte imágenes y código coloreado.", "inicio, ayuda")
        save_page("Ejemplo de consulta Splunk", "Splunk", "== Consulta ==\n\n```spl\nindex=correo action_final!=incomplete\n| stats count by suborg\n| sort - count\n```", "splunk, ejemplo")


def find_port(start=8080, end=8099):
    for port in range(start, end + 1):
        with socket.socket() as sock:
            try: sock.bind(("127.0.0.1", port)); return port
            except OSError: continue
    raise RuntimeError("No hay puertos libres entre 8080 y 8099")


if __name__ == "__main__":
    seed_examples(); load_categories(); port = find_port(); url = f"http://127.0.0.1:{port}"
    print("=" * 60); print(f"Wiki Procedimientos {APP_VERSION}"); print(f"Abrir: {url}"); print("Para detener: Ctrl+C"); print("=" * 60)
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
