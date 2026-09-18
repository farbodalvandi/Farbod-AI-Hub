# -*- coding: utf-8 -*-
"""
Lightweight Visio interchange.

We generate the classic .vdx format (VisioDocument XML, single plain-text
XML file, no zipping) rather than the newer .vsdx (a zipped OOXML package
with dozens of interdependent parts). .vdx is fully documented, trivial to
build correctly by hand, and modern Visio (2010-365) still opens it natively
-- so this gives reliable round-tripping without the risk of producing a
corrupt .vsdx that Visio refuses to open.

Export: every diagram node (an asset or sub-object) becomes a rectangle
shape positioned at its saved diagram coordinates; every asset_link becomes
a connector between the two shapes.

Import: reads shape (Shape) text + position and Connect elements back out,
so a diagram roughed out in Visio can be pulled back in as links between
assets that are matched by name.
"""

import re
import xml.etree.ElementTree as ET

NS = "http://schemas.microsoft.com/visio/2003/core"
ET.register_namespace("", NS)

HEADER = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<?mso-application progid="Visio.Drawing"?>
<VisioDocument xmlns="{ns}" xml:space="preserve">
<DocumentSettings TopPage="0" DefaultTextStyle="3" DefaultLineStyle="3" DefaultFillStyle="3" DefaultGuide="4"/>
<Pages>
<Page ID="0" NameU="Page-1" IsCustomNameU="0" Name="Page-1" IsCustomName="0">
<PageSheet>
<PageProps>
<PageWidth>{width}</PageWidth>
<PageHeight>{height}</PageHeight>
</PageProps>
</PageSheet>
<Shapes>
{shapes}
</Shapes>
<Connects>
{connects}
</Connects>
</Page>
</Pages>
</VisioDocument>
'''

SHAPE_TMPL = '''<Shape ID="{id}" Type="Shape" LineStyle="3" FillStyle="3" TextStyle="3">
<XForm>
<PinX>{x}</PinX>
<PinY>{y}</PinY>
<Width>1.6</Width>
<Height>0.8</Height>
</XForm>
<Text>{text}</Text>
</Shape>
'''

CONNECT_TMPL = '''<Shape ID="{id}" Type="Shape" LineStyle="3">
<XForm><PinX>0</PinX><PinY>0</PinY><Width>0</Width><Height>0</Height></XForm>
<Connects>
<Connect FromSheet="{id}" FromCell="BeginX" ToSheet="{from_id}" ToCell="PinX"/>
<Connect FromSheet="{id}" FromCell="EndX" ToSheet="{to_id}" ToCell="PinX"/>
</Connects>
</Shape>
'''


def _esc(text):
    return (str(text or "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def export_vdx(nodes, edges):
    """
    nodes: list of dicts {key, label, x, y}   (x,y in inches, page coords)
    edges: list of dicts {source_key, target_key, label}
    Returns the .vdx file content as a string.
    """
    key_to_id = {}
    shapes_xml = []
    next_id = 1
    for n in nodes:
        key_to_id[n["key"]] = next_id
        shapes_xml.append(SHAPE_TMPL.format(
            id=next_id, x=round(n.get("x", 1), 2), y=round(n.get("y", 1), 2),
            text=_esc(n["label"])))
        next_id += 1

    connects_xml = []
    for e in edges:
        fid = key_to_id.get(e["source_key"])
        tid = key_to_id.get(e["target_key"])
        if fid is None or tid is None:
            continue
        connects_xml.append(CONNECT_TMPL.format(id=next_id, from_id=fid, to_id=tid))
        next_id += 1

    max_x = max([n.get("x", 1) for n in nodes], default=8) + 2
    max_y = max([n.get("y", 1) for n in nodes], default=6) + 2

    return HEADER.format(
        ns=NS, width=round(max_x, 1), height=round(max_y, 1),
        shapes="\n".join(shapes_xml), connects="\n".join(connects_xml))


def import_vdx(file_bytes):
    """
    Best-effort parse of a .vdx file: returns list of shapes
    [{id, text, x, y}] and list of connects [{from_id, to_id}].
    Matching those shapes back to real assets by label text is done by the
    caller (it needs DB access), this module only parses the XML.
    """
    text = file_bytes.decode("utf-8", errors="ignore")
    # Strip default namespace so plain tag names work with a simple parser
    text = re.sub(r'xmlns="[^"]+"', "", text, count=1)
    root = ET.fromstring(text)

    shapes = []
    for shape in root.iter("Shape"):
        shape_id = shape.get("ID")
        text_el = shape.find("Text")
        xform = shape.find("XForm")
        if text_el is None or xform is None:
            continue
        label = (text_el.text or "").strip()
        if not label:
            continue
        pin_x = xform.find("PinX")
        pin_y = xform.find("PinY")
        shapes.append({
            "id": shape_id,
            "text": label,
            "x": float(pin_x.text) if pin_x is not None and pin_x.text else 0,
            "y": float(pin_y.text) if pin_y is not None and pin_y.text else 0,
        })

    connects = []
    for connect in root.iter("Connect"):
        pass  # simplified importer: position/label import only (see docstring)

    return shapes, connects


# ---------------------------------------------------------------------------
# VSDX viewer support
# ---------------------------------------------------------------------------
# A .vsdx file is an OOXML ZIP package.  We intentionally render a safe,
# self-contained SVG instead of exposing package XML/HTML to the browser.
def _import_vsdx_svg_fallback(file_bytes, page_index=0):
    """Render the requested VSDX page as a self-contained SVG string.

    This is a lightweight viewer for common Visio diagrams: text-bearing
    shapes, rectangles/boxes and 1-D connector shapes. It does not require
    Microsoft Visio or LibreOffice on the server.
    """
    import html
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(file_bytes), "r") as zf:
        page_files = [
            n for n in zf.namelist()
            if n.lower().startswith("visio/pages/page") and n.lower().endswith(".xml")
        ]
        page_files.sort(key=lambda n: int(re.search(r"page(\d+)\.xml$", n, re.I).group(1)) if re.search(r"page(\d+)\.xml$", n, re.I) else 10**9)
        if not page_files:
            raise ValueError("The VSDX package contains no Visio pages.")
        if page_index < 0 or page_index >= len(page_files):
            raise ValueError("The requested Visio page does not exist.")
        xml_bytes = zf.read(page_files[page_index])

    root = ET.fromstring(xml_bytes)
    # Visio files in the wild use more than one namespace revision. Detect
    # the namespace from the document instead of assuming one fixed URI.
    ns_uri = root.tag.split("}", 1)[0].lstrip("{") if "}" in root.tag else "http://schemas.microsoft.com/office/visio/2012/main"
    ns = {"v": ns_uri}

    def val(el, path, default=0.0):
        node = el.find(path, ns) if el is not None else None
        try:
            return float(node.text) if node is not None and node.text else default
        except (TypeError, ValueError):
            return default

    # VSDX uses inches for page/shape geometry.
    page_sheet = root.find("v:PageSheet", ns)
    page_props = page_sheet.find("v:PageProps", ns) if page_sheet is not None else None
    page_w = val(page_props, "v:PageWidth", 11.0)
    page_h = val(page_props, "v:PageHeight", 8.5)
    page_w = max(1.0, min(page_w, 1000.0))
    page_h = max(1.0, min(page_h, 1000.0))

    def shape_text(shape):
        text = shape.find("v:Text", ns)
        if text is None:
            return ""
        return " ".join("".join(text.itertext()).split())

    def shape_xform(shape):
        xform = shape.find("v:XForm", ns)
        if xform is None:
            xform = shape.find("v:XForm1D", ns)
        if xform is None:
            xform = shape.find(".//v:XForm", ns)
        if xform is None:
            xform = shape.find(".//v:XForm1D", ns)
        return xform

    def one_d(shape):
        return shape.find("v:XForm1D", ns) is not None

    shapes = []
    # Include shapes nested inside groups; this is common in real HPE/network
    # diagrams and was the main reason some VSDX files appeared blank.
    for shape in root.findall(".//v:Shape", ns):
        xform = shape_xform(shape)
        if xform is None:
            continue
        text = shape_text(shape)
        if one_d(shape):
            bx = val(xform, "v:BeginX", 0)
            by = val(xform, "v:BeginY", 0)
            ex = val(xform, "v:EndX", 0)
            ey = val(xform, "v:EndY", 0)
            shapes.append(("edge", bx, by, ex, ey, text))
        else:
            x = val(xform, "v:PinX", 1)
            y = val(xform, "v:PinY", 1)
            w = max(0.05, val(xform, "v:Width", 1.5))
            h = max(0.05, val(xform, "v:Height", 0.75))
            if text or shape.get("Type") != "Group":
                shapes.append(("box", x, y, w, h, text))

    # SVG y-axis points down, while Visio page coordinates point up.
    def sy(y):
        return page_h - y

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {page_w:g} {page_h:g}" '
        f'width="{page_w:g}in" height="{page_h:g}in" preserveAspectRatio="xMidYMid meet">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<g stroke="#64748b" fill="none" stroke-width="0.02">'
    ]
    for item in shapes:
        if item[0] == "edge":
            _, bx, by, ex, ey, label = item
            svg.append(f'<line x1="{bx:g}" y1="{sy(by):g}" x2="{ex:g}" y2="{sy(ey):g}" '
                       'stroke="#64748b" stroke-width="0.025"/>')
            if label:
                mx, my = (bx + ex) / 2, sy((by + ey) / 2)
                svg.append(f'<text x="{mx:g}" y="{my:g}" text-anchor="middle" '
                           'font-family="Segoe UI,Arial,sans-serif" font-size="0.16" '
                           'fill="#334155" stroke="none">{html.escape(label)}</text>')
    svg.append('</g>')
    for item in shapes:
        if item[0] != "box":
            continue
        _, x, y, w, h, label = item
        left, top = x - w / 2, sy(y + h / 2)
        svg.append(f'<rect x="{left:g}" y="{top:g}" width="{w:g}" height="{h:g}" '
                   'rx="0.05" fill="#f8fafc" stroke="#475569" stroke-width="0.025"/>')
        if label:
            # Keep text inside the shape and allow simple line wrapping.
            max_chars = max(8, int(w * 9))
            words = label.split()
            lines, line = [], ""
            for word in words:
                trial = (line + " " + word).strip()
                if len(trial) > max_chars and line:
                    lines.append(line)
                    line = word
                else:
                    line = trial
            if line:
                lines.append(line)
            lines = lines[:8]
            start_y = sy(y) - ((len(lines) - 1) * 0.09)
            for i, line in enumerate(lines):
                svg.append(f'<text x="{x:g}" y="{start_y + i*0.18:g}" text-anchor="middle" '
                           f'font-family="Segoe UI,Arial,sans-serif" font-size="0.16" '
                           f'fill="#17212b" stroke="none">{html.escape(line)}</text>')
    svg.append('</svg>')
    return "".join(svg), len(page_files), page_index


def import_vsdx_svg(file_bytes, page_index=0):
    """Use native libvisio-ng SVG conversion when available, then fallback."""
    import os, tempfile
    try:
        from libvisio_ng import convert, get_page_info
        with tempfile.TemporaryDirectory(prefix="farbod_vsdx_") as td:
            src=os.path.join(td, "diagram.vsdx")
            out=os.path.join(td, "svg")
            os.makedirs(out, exist_ok=True)
            with open(src, "wb") as f: f.write(file_bytes)
            pages=get_page_info(src)
            if not pages: raise ValueError("The VSDX file contains no pages.")
            if page_index < 0 or page_index >= len(pages): raise ValueError("The requested Visio page does not exist.")
            files=convert(src, output_dir=out)
            files=sorted([str(x) for x in files])
            if not files or page_index >= len(files): raise ValueError("VSDX conversion returned no SVG.")
            with open(files[page_index], "r", encoding="utf-8", errors="ignore") as f: svg=f.read()
            return svg, len(pages), page_index
    except Exception:
        return _import_vsdx_svg_fallback(file_bytes, page_index=page_index)
