#!/usr/bin/env python3
"""Minimal, dependency-free Excalidraw-as-code library.
Usage in a script:
    from excalidraw_lib import Diagram
    d = Diagram("Titulo")
    d.group("VPC", 80, 100, 600, 300)
    a = d.box("Cliente", 100, 160, color="blue")
    b = d.box("Gateway", 400, 160, color="violet")
    d.arrow(a, b, "HTTPS")
    d.note("atencao", 100, 400)
    d.save("arquivo.excalidraw")
Validate: python3 excalidraw_lib.py check arquivo.excalidraw
"""
import json, random, sys, time

PALETTE = {
    "blue": "#a5d8ff", "green": "#b2f2bb", "yellow": "#ffec99",
    "red": "#ffc9c9", "violet": "#d0bfff", "orange": "#ffd8a8",
    "gray": "#e9ecef", "teal": "#96f2d7", "none": "transparent",
}
FONT_VIRGIL = 1

def _snap(v, g=20):
    return int(round(v / g) * g)

class Diagram:
    def __init__(self, title=None, x=40, y=20):
        self.els = []
        self._n = 0
        if title:
            self.text(title, x, y, size=32)

    def _id(self, p):
        self._n += 1
        return f"{p}{self._n}"

    def _base(self, kind, x, y, w, h, **kw):
        e = {
            "id": self._id(kind[:3]), "type": kind, "x": x, "y": y,
            "width": w, "height": h, "angle": 0,
            "strokeColor": kw.get("stroke", "#1e1e1e"),
            "backgroundColor": kw.get("bg", "transparent"),
            "fillStyle": "solid", "strokeWidth": 2,
            "strokeStyle": kw.get("style", "solid"), "roughness": 1,
            "opacity": 100, "groupIds": [], "frameId": None,
            "roundness": kw.get("roundness"), "seed": random.randint(1, 2**31),
            "version": 1, "versionNonce": random.randint(1, 2**31),
            "isDeleted": False, "boundElements": [], "updated": int(time.time()*1000),
            "link": None, "locked": False,
        }
        self.els.append(e)
        return e

    def text(self, s, x, y, size=20, color="#1e1e1e", container=None, align="left"):
        lines = s.split("\n")
        w = max(len(l) for l in lines) * size * 0.55
        h = len(lines) * size * 1.25
        e = self._base("text", x, y, w, h, stroke=color)
        e.update({"text": s, "originalText": s, "fontSize": size,
                  "fontFamily": FONT_VIRGIL, "textAlign": align,
                  "verticalAlign": "middle" if container else "top",
                  "containerId": container["id"] if container else None,
                  "lineHeight": 1.25, "autoResize": True})
        if container:
            container["boundElements"].append({"type": "text", "id": e["id"]})
            e["x"] = container["x"] + (container["width"] - w) / 2
            e["y"] = container["y"] + (container["height"] - h) / 2
        return e

    def box(self, label, x, y, w=180, h=80, color="blue", shape="rectangle", size=18):
        e = self._base(shape, _snap(x), _snap(y), w, h, bg=PALETTE.get(color, color),
                       roundness={"type": 3} if shape == "rectangle" else {"type": 2})
        e["_box"] = True
        if label:
            self.text(label, 0, 0, size=size, container=e, align="center")
        return e

    def group(self, label, x, y, w, h, color="#868e96"):
        e = self._base("rectangle", _snap(x), _snap(y), w, h, stroke=color, style="dashed")
        self.text(label, e["x"] + 10, e["y"] + 8, size=16, color=color)
        return e

    def note(self, s, x, y, size=16):
        return self.text(s, x, y, size=size, color="#e03131")

    def arrow(self, a, b, label=None, dashed=False, via=None):
        def c(e): return (e["x"] + e["width"]/2, e["y"] + e["height"]/2)
        def edge(e, tx, ty):
            cx, cy = c(e); dx, dy = tx-cx, ty-cy
            if abs(dx)*e["height"] > abs(dy)*e["width"]:
                return (e["x"] + (e["width"] if dx > 0 else 0) + (8 if dx > 0 else -8), cy)
            return (cx, e["y"] + (e["height"] if dy > 0 else 0) + (8 if dy > 0 else -8))
        pts_abs = list(via or [])
        t1 = pts_abs[0] if pts_abs else c(b)
        t2 = pts_abs[-1] if pts_abs else c(a)
        s = edge(a, *t1); t = edge(b, *t2)
        pts_abs = [s] + pts_abs + [t]
        xs = [p[0] for p in pts_abs]; ys = [p[1] for p in pts_abs]
        e = self._base("arrow", s[0], s[1], max(xs)-min(xs), max(ys)-min(ys),
                       style="dashed" if dashed else "solid", roundness={"type": 2})
        e.update({"points": [[p[0]-s[0], p[1]-s[1]] for p in pts_abs],
                  "startBinding": {"elementId": a["id"], "focus": 0, "gap": 8},
                  "endBinding": {"elementId": b["id"], "focus": 0, "gap": 8},
                  "startArrowhead": None, "endArrowhead": "arrow",
                  "lastCommittedPoint": None})
        a["boundElements"].append({"type": "arrow", "id": e["id"]})
        b["boundElements"].append({"type": "arrow", "id": e["id"]})
        if label:
            mid = pts_abs[len(pts_abs)//2] if len(pts_abs) > 2 else ((s[0]+t[0])/2, (s[1]+t[1])/2)
            tx = self.text(label, 0, 0, size=16, container=e, align="center")
            tx["x"] = mid[0] - tx["width"]/2; tx["y"] = mid[1] - tx["height"]/2
        return e

    def save(self, path):
        els = [{k: v for k, v in e.items() if not k.startswith("_")} for e in self.els]
        doc = {"type": "excalidraw", "version": 2, "source": "excalidraw-as-code",
               "elements": els, "appState": {"viewBackgroundColor": "#ffffff", "gridSize": 20},
               "files": {}}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
        print(f"wrote {path} ({len(els)} elements)")
        return path

def check(path):
    errs = []
    doc = json.load(open(path, encoding="utf-8"))
    els = doc.get("elements", [])
    ids = [e["id"] for e in els]
    if len(ids) != len(set(ids)): errs.append("duplicate ids")
    by = {e["id"]: e for e in els}
    for e in els:
        for b in e.get("boundElements") or []:
            if b["id"] not in by: errs.append(f"{e['id']}: bound {b['id']} missing")
        if e.get("containerId") and e["containerId"] not in by:
            errs.append(f"{e['id']}: container missing")
        if e["type"] == "arrow":
            for k in ("startBinding", "endBinding"):
                bd = e.get(k)
                if bd and bd["elementId"] not in by: errs.append(f"{e['id']}: {k} missing")
    boxes = [e for e in els if e["type"] in ("rectangle", "ellipse", "diamond")
             and e.get("strokeStyle") != "dashed"]
    for i, a in enumerate(boxes):
        for b in boxes[i+1:]:
            if (a["x"] < b["x"]+b["width"] and b["x"] < a["x"]+a["width"] and
                a["y"] < b["y"]+b["height"] and b["y"] < a["y"]+a["height"]):
                errs.append(f"overlap {a['id']} / {b['id']}")
    for m in errs: print("ERROR:", m)
    print("OK" if not errs else f"{len(errs)} error(s)")
    return not errs

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "check":
        sys.exit(0 if check(sys.argv[2]) else 1)
    print(__doc__)
