import json
import posixpath
import re
import string
import unicodedata
from contextlib import closing
from tempfile import SpooledTemporaryFile
from types import SimpleNamespace
from urllib.parse import quote
from zipfile import ZIP_DEFLATED, ZipFile

from markdown_it import MarkdownIt
from mdformat.plugins import PARSER_EXTENSIONS
from mdformat.renderer import DEFAULT_RENDERERS, MDRenderer

from backend.app.repositories.docs import ATTACHMENT, INTERNAL, VIEW_REFERENCE, attachment_targets, parse_markdown, view_references


def filename_stem(title):
    clean = "".join(
        "-" if character in '/\\:*?"<>|' or unicodedata.category(character).startswith("C") else character
        for character in unicodedata.normalize("NFC", title)
    )
    clean = re.sub(r"[\s-]+", "-", clean).strip(".-")
    return clean.encode("utf-8")[:80].decode("utf-8", errors="ignore").rstrip(".-") or "page"


def page_paths(pages):
    siblings = {}
    prefixes = {}
    for page in pages:
        siblings.setdefault(page["parent_id"], []).append(page)
        prefix = page["id"][:8]
        prefixes[prefix] = prefixes.get(prefix, 0) + 1

    paths = {}
    pending = [(None, "")]
    while pending:
        parent, directory = pending.pop()
        for page in siblings.get(parent, ()):
            identifier = page["id"]
            prefix = identifier[:8]
            suffix = prefix if prefixes[prefix] == 1 else identifier
            stem = filename_stem(page["title"])
            child_directory = posixpath.join(directory, f"{stem}-{suffix}")
            paths[identifier] = child_directory + ".md"
            pending.append((identifier, child_directory))
    return paths


def markdown_label(title):
    # Escaping ASCII punctuation also prevents an automatic title from becoming inline Markdown.
    return "".join("\\" + character if character in string.punctuation else character for character in title)


def plain_label(node):
    if node.type in {"text", "code_inline"}:
        return node.content
    if node.type in {"softbreak", "hardbreak"}:
        return " "
    return "".join(plain_label(child) for child in node.children)


def export_markdown(page, paths, titles, assets, view_paths):
    markdown = page["markdown"]
    if not parse_markdown(markdown)[1] and not attachment_targets(markdown) and not view_references(markdown):
        return markdown

    def asset_destination(node, context, kind):
        attribute = "src" if kind == "image" else "href"
        match = ATTACHMENT.fullmatch(node.attrs[attribute])
        if match is None:
            return DEFAULT_RENDERERS[kind](node, context)
        identifier = match[1].lower()
        if identifier not in assets:
            return markdown_label(plain_label(node) or "Pièce jointe") + " (pièce jointe indisponible)"
        relative = posixpath.relpath(assets[identifier], posixpath.dirname(paths[page["id"]]) or ".")
        node.attrs[attribute] = quote(relative, safe="/")
        node.meta.pop("label", None)
        return DEFAULT_RENDERERS[kind](node, context)

    def render_link(node, context):
        view = VIEW_REFERENCE.fullmatch(node.attrs["href"])
        if view:
            target_view = (view[1].lower(), view[2].lower())
            if target_view not in view_paths:
                return "Vue indisponible"
            destination, collection, name = view_paths[target_view]
            relative = posixpath.relpath(destination, posixpath.dirname(paths[page["id"]]) or ".")
            return f"[{markdown_label(collection + ' · ' + name + ' (collection exportée)')}]({quote(relative, safe='/')})"
        match = INTERNAL.fullmatch(node.attrs["href"])
        if match is None:
            return asset_destination(node, context, "link")
        target = match[1].lower()
        label = "".join(child.render(context) for child in node.children).replace("\n", " ")
        if target not in paths:
            return markdown_label(plain_label(node) or "Page liée") + " (page indisponible)"
        if not label:
            label = markdown_label(titles[target])
        relative = posixpath.relpath(paths[target], posixpath.dirname(paths[page["id"]]) or ".")
        return f"[{label}]({quote(relative, safe='/')})"

    gfm = PARSER_EXTENSIONS["gfm"]
    links = SimpleNamespace(RENDERERS={
        "link": render_link, "image": lambda node, context: asset_destination(node, context, "image"),
    })
    parser = MarkdownIt("commonmark", {
        "mdformat": {"wrap": "keep"},
        "parser_extension": [gfm, links],
        "store_labels": True,
    }, renderer_cls=MDRenderer)
    gfm.update_mdit(parser)
    return parser.render(markdown)


def write_collection_indexes(output, pages, collections, paths):
    referenced = set().union(*(view_references(page["markdown"]) for page in pages))
    destinations = {}
    for collection in collections:
        collection_id = collection["id"]
        views = [view for view in collection["views"] if (collection_id, view["id"]) in referenced]
        if not views:
            continue
        index_path = "collections/" + collection_id + ".md"
        for view in views:
            destinations[(collection_id, view["id"])] = (index_path, collection["title"], view["name"])
        rows = sorted((page for page in pages if page["collection_id"] == collection_id),
                      key=lambda page: (page["title"].casefold(), page["id"]))
        lines = ["# " + markdown_label(collection["title"]), "",
                 "Pages de la collection présentes dans cette archive. Les réglages des vues figurent dans collections.json.", ""]
        for row in rows:
            relative = posixpath.relpath(paths[row["id"]], posixpath.dirname(index_path))
            lines.append(f"- [{markdown_label(row['title'])}]({quote(relative, safe='/')})")
        if not rows:
            lines.append("Cette collection est vide.")
        output.writestr(index_path, ("\n".join(lines) + "\n").encode("utf-8"))
    return destinations


def build_zip(pages, collections, assets=()):
    paths = page_paths(pages)
    titles = {page["id"]: page["title"] for page in pages}
    archive = SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
    try:
        with ZipFile(archive, "w", compression=ZIP_DEFLATED) as output:
            asset_paths = {}
            for asset in assets:
                stem, extension = posixpath.splitext(asset["name"])
                path = f"assets/{filename_stem(stem)}-{asset['id']}{extension.lower()}"
                output.writestr(path, bytes(asset["content"]))
                asset_paths[asset["id"]] = path
            view_paths = write_collection_indexes(output, pages, collections, paths)
            for page in pages:
                markdown = export_markdown(page, paths, titles, asset_paths, view_paths)
                output.writestr(paths[page["id"]], markdown.encode("utf-8"))
            if collections:
                relation_fields = {
                    (collection["id"], field["id"])
                    for collection in collections for field in collection["fields"] if field["kind"] == "relation"
                }
                properties = {
                    paths[page["id"]]: {"collectionId": page["collection_id"], "values": {
                        identifier: [paths[target] for target in value if target in paths] if (page["collection_id"], identifier) in relation_fields else value
                        for identifier, value in page["properties"].items()
                    }}
                    for page in pages if page["collection_id"]
                }
                schema = [{key: item[key] for key in ("id", "title", "fields", "views")} for item in collections]
                output.writestr("collections.json", json.dumps(
                    {"collections": schema, "pages": properties}, ensure_ascii=False, indent=2
                ).encode("utf-8"))
        archive.seek(0)
        return archive
    except BaseException:
        archive.close()
        raise


def zip_chunks(archive):
    with closing(archive):
        while chunk := archive.read(64 * 1024):
            yield chunk
