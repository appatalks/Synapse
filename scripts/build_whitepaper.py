#!/usr/bin/env python3
"""Build the evidence-backed SYNAPSE white paper without network access."""

import argparse
import datetime as dt
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

try:
    from reportlab import Version
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.platypus import (
        BaseDocTemplate, Flowable, Frame, PageBreak, PageTemplate,
        Paragraph, Preformatted, Spacer, Table, TableStyle,
    )
    from reportlab.platypus.tableofcontents import TableOfContents
except ModuleNotFoundError as error:
    raise SystemExit("White-paper rendering requires the optional dependencies: pip install -e '.[paper]'") from error


ROOT = Path(__file__).resolve().parent.parent
PAPER = ROOT / "docs/whitepaper"
NAVY = colors.HexColor("#102337")
INK = colors.HexColor("#203345")
MINT = colors.HexColor("#22C9A2")
LINK = colors.HexColor("#007E69")
MUTED = colors.HexColor("#586B7B")
PALE = colors.HexColor("#EFF5F6")
RULE = colors.HexColor("#DCE6EA")
RUST = colors.HexColor("#A34E32")
WARNING = colors.HexColor("#FBF0EA")
WIDTH, HEIGHT = A4
MARGIN = 52
CONTENT_WIDTH = WIDTH - 2*MARGIN


def load_evidence(path=PAPER / "evidence.json"):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or len(data.get("headline_models", [])) != 4:
        raise ValueError("The paper requires exactly four reviewed headline models")
    if len({row["model"] for row in data["headline_models"]}) != 4:
        raise ValueError("Headline model identities must be unique")
    if data.get("quality_qualified") is not False or data.get("peer_reviewed") is not False:
        raise ValueError("The evidence must retain its unqualified, project-reported status")
    expected = {
        "context": 16384, "generation_threads": 8, "prompt_threads": 16,
        "repetitions": 3, "output_tokens": 512, "temperature": 0, "seed": 42,
        "ignore_eos": True, "cache_prompt": False, "speculation": False,
    }
    if data["protocol"] != expected:
        raise ValueError("The paper protocol differs from the reviewed screen")
    for row in data["headline_models"]:
        if "Mistral" in row["model"]:
            raise ValueError("Mistral is not a qualified headline row")
        for key in ("control_tok_s", "accelerated_tok_s"):
            if type(row[key]) not in (int, float) or not math.isfinite(row[key]) or row[key] <= 0:
                raise ValueError("Invalid headline throughput")
        gain = 100*(row["accelerated_tok_s"]/row["control_tok_s"] - 1)
        if abs(gain - row["relative_gain_percent"]) > 1e-9 or round(gain) != row["display_gain_percent"]:
            raise ValueError("Headline gain is inconsistent with recorded medians")
        if type(row["cache_mib"]) is not int or not 0 < row["cache_mib"] <= 65536:
            raise ValueError("Invalid recorded residency budget")
    if (data["mistral_research_only"]["headline_eligible"] is not False or
            data["mistral_research_only"]["native_equivalence_passed"] is not False):
        raise ValueError("Experimental Mistral status must remain explicit")
    for item in [*data["headline_models"], data["mistral_research_only"], data["memory_path_control"]]:
        source = item["source"]
        if "local_record" in source:
            record = (ROOT / source["local_record"]).resolve()
            if not record.is_relative_to((ROOT / "docs/benchmarks").resolve()):
                raise ValueError("Evidence path is outside the reviewed benchmark directory")
            if hashlib.sha256(record.read_bytes()).hexdigest() != source["sha256"]:
                raise ValueError("Reviewed evidence changed; refresh and review the paper snapshot")
            recorded = json.loads(record.read_text(encoding="utf-8"))
            if "control_tok_s" in item:
                if (item["control_tok_s"] != recorded["headline"]["control_tok_s"] or
                        item["accelerated_tok_s"] != recorded["headline"]["synapse_tok_s"]):
                    raise ValueError("Snapshot medians differ from their reviewed source")
            elif "medians" in item:
                medians = {row["profile"]: row["median_tok_s"]
                           for row in recorded["latest_research_screen"]["profiles"]}
                if item["medians"] != medians or recorded["native_equivalence_passed"] is not False:
                    raise ValueError("Mistral snapshot differs from its failed-equivalence source")
            elif "mapped_lru_tok_s" in item:
                if (item["mapped_lru_tok_s"] != recorded["headline"]["cpu_cache10240_mmap_tok_s"] or
                        item["copied_lru_tok_s"] != recorded["headline"]["cpu_cache10240_copy_tok_s"]):
                    raise ValueError("Memory-path controls differ from their reviewed source")
    return data


def inline(text, citations=True):
    text = html.escape(text, quote=True)
    text = re.sub(r"`([^`]+)`", r'<font name="Courier" size="9">\1</font>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)

    def link(match):
        url = html.unescape(match[2])
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("White-paper external links must be credential-free HTTPS URLs")
        return f'<link href="{html.escape(url, quote=True)}" color="#007E69">{match[1]}</link>'

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, text)
    if citations:
        def citation(match):
            numbers = []
            for part in match[1].split(","):
                bounds = part.split("-")
                numbers.extend(range(int(bounds[0]), int(bounds[-1]) + 1))
            return "[" + ", ".join(f'<link href="#ref-{number}" color="#007E69">{number}</link>'
                                    for number in numbers) + "]"
        text = re.sub(r"\[([0-9]+(?:-[0-9]+)?(?:,[0-9]+(?:-[0-9]+)?)*)\]", citation, text)
    return text


def styles():
    base = getSampleStyleSheet()
    result = {
        "body": ParagraphStyle("PaperBody", fontName="Times-Roman", fontSize=10.6,
                               leading=14.7, textColor=INK, alignment=TA_JUSTIFY, spaceAfter=7),
        "h1": ParagraphStyle("PaperH1", fontName="Helvetica-Bold", fontSize=20, leading=25,
                             textColor=NAVY, spaceAfter=15, keepWithNext=True),
        "h2": ParagraphStyle("PaperH2", fontName="Helvetica-Bold", fontSize=11, leading=15,
                             textColor=LINK, spaceBefore=9, spaceAfter=7, keepWithNext=True),
        "caption": ParagraphStyle("PaperCaption", fontName="Helvetica", fontSize=8.4, leading=11.7,
                                  textColor=MUTED, spaceBefore=5, spaceAfter=12),
        "table": ParagraphStyle("PaperTable", fontName="Helvetica", fontSize=8.4, leading=11.5,
                                textColor=INK, alignment=TA_LEFT),
        "table_head": ParagraphStyle("PaperTableHead", fontName="Helvetica-Bold", fontSize=8.4,
                                     leading=11.5, textColor=colors.white),
        "warning": ParagraphStyle("PaperWarning", fontName="Helvetica", fontSize=9.1, leading=13.3,
                                  textColor=INK),
        "code": ParagraphStyle("PaperCode", fontName="Courier", fontSize=8.5, leading=12.5,
                               textColor=NAVY, spaceAfter=4),
        "reference": ParagraphStyle("PaperReference", fontName="Helvetica", fontSize=8.5, leading=11.8,
                                    textColor=INK, spaceAfter=6),
    }
    result["bullet"] = ParagraphStyle("PaperBullet", parent=result["body"], leftIndent=12,
                                      bulletIndent=1, spaceAfter=5)
    result["toc"] = ParagraphStyle("PaperTOC", parent=base["Normal"], fontName="Helvetica",
                                   fontSize=10.3, leading=18, textColor=INK, leftIndent=0,
                                   firstLineIndent=0, spaceBefore=1)
    return result


class Diagram(Flowable):
    def __init__(self, kind, evidence):
        super().__init__()
        self.kind, self.evidence = kind, evidence
        self.width = CONTENT_WIDTH
        self.height = {"constraints": 145, "architecture": 224, "headline": 204,
                       "precision": 157, "memory": 148}[kind]

    def text(self, x, y, text, size=9, color=INK, bold=False, center=False):
        self.canv.setFillColor(color)
        self.canv.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        if center:
            self.canv.drawCentredString(x, y, text)
        else:
            self.canv.drawString(x, y, text)

    def box(self, x, y, width, height, title, lines=(), fill=PALE):
        self.canv.setFillColor(fill)
        self.canv.setStrokeColor(RULE)
        self.canv.roundRect(x, y, width, height, 6, fill=1, stroke=1)
        self.text(x+12, y+height-20, title, 10, bold=True)
        for index, line in enumerate(lines):
            if stringWidth(line, "Helvetica", 8.5) > width-24:
                raise ValueError(f"Diagram label is wider than its box: {line}")
            self.text(x+12, y+height-38-12*index, line, 8.5, MUTED)

    def arrow(self, x1, y1, x2, y2, color=LINK):
        canvas = self.canv
        canvas.setStrokeColor(color)
        canvas.setFillColor(color)
        canvas.setLineWidth(1.25)
        canvas.line(x1, y1, x2, y2)
        angle = math.atan2(y2-y1, x2-x1)
        path = canvas.beginPath()
        path.moveTo(x2, y2)
        for offset in (2.65, -2.65):
            path.lineTo(x2+6*math.cos(angle+offset), y2+6*math.sin(angle+offset))
        path.close()
        canvas.drawPath(path, fill=1, stroke=0)

    def draw(self):
        c = self.canv
        w = self.width
        if self.kind == "constraints":
            gap = 12
            cell = (w-2*gap)/3
            self.box(0, 25, cell, 108, "GPU capacity",
                     ("Backbone + KV + compute", "Resident expert bank", "Fit is context-dependent"))
            self.box(cell+gap, 25, cell, 108, "Host execution",
                     ("Resident weight working set", "Memory reads + CPU kernels", "Capacity is not bandwidth"))
            self.box(2*(cell+gap), 25, cell, 108, "Transfers and ordering",
                     ("Admission and activation I/O", "Synchronization and reuse", "Misses need not upload"))
            self.text(0, 6, "Evaluate the whole token path, not one utilization counter.", 8.5, LINK, bold=True)
        elif self.kind == "architecture":
            self.box(0, 151, 143, 62, "Native router",
                     ("Original selection rules", "All k selected contributions"))
            self.box(174, 151, w-174, 62, "Descriptor + residency dispatch",
                     ("Tensor types, shapes and bank groups", "Placement is not expert selection"))
            self.arrow(143, 182, 174, 182)
            self.box(174, 57, 144, 67, "GPU resident branch",
                     ("Resident expert components", "Guarded device execution"))
            self.box(342, 57, w-342, 67, "CPU cold branch",
                     ("Selected cache misses", "Original expert contribution"))
            self.arrow(247, 151, 247, 124)
            self.arrow(416, 151, 416, 124)
            self.box(0, 57, 143, 67, "Admission control",
                     ("Observed history only", "Guards on migration/reuse"))
            c.setDash(3, 2)
            self.arrow(143, 90, 174, 90)
            c.setDash()
            self.arrow(247, 57, 247, 30)
            self.arrow(416, 57, 416, 30)
            c.setStrokeColor(LINK)
            c.line(247, 30, 416, 30)
            self.text(174, 9, "Reconcile weighted outputs -> aggregate -> next layer", 9, LINK, bold=True)
        elif self.kind == "headline":
            x0, plot_width = 176, w-204
            for tick in range(0, 91, 15):
                x = x0+plot_width*tick/90
                c.setStrokeColor(RULE)
                c.line(x, 22, x, 181)
                self.text(x, 10, str(tick), 7.5, MUTED, center=True)
            for index, row in enumerate(self.evidence["headline_models"]):
                name = re.sub(r" (?:MXFP4|IQ3_S|IQ4_XS|Q8_0)$", "", row["model"])
                y = 161-40*index
                self.text(0, y+2, name, 9, bold=True)
                for offset, key, color in ((0, "control_tok_s", MUTED), (-13, "accelerated_tok_s", MINT)):
                    value = row[key]
                    length = plot_width*value/90
                    c.setFillColor(color)
                    c.roundRect(x0, y+offset, length, 9, 2, fill=1, stroke=0)
                    self.text(x0+length+5, y+offset+1, f"{value:.2f}", 7.6, INK)
            self.text(x0, 192, "Control (profile varies)", 8, MUTED)
            self.text(x0+133, 192, "Accelerated", 8, LINK)
            c.setFont("Helvetica", 7.5)
            c.drawRightString(w, 10, "tok/s")
        elif self.kind == "precision":
            self.box(0, 73, 151, 72, "Required semantics",
                     ("FP32 activation range", "Quantized weight components", "Every selected contribution"))
            self.box(175, 73, w-175, 72, "Original capability boundary",
                     ("CUDA expert-ID matmul rejects protected source precision", "Recognized architecture is not enough"))
            self.arrow(151, 109, 175, 109, RUST)
            self.box(0, 0, w, 48, "Qualification gate, not a bypass",
                     ("Keep the precision guard; test supported operations and full-model behavior.",), WARNING)
        elif self.kind == "memory":
            self.box(0, 82, w, 57, "Host physical memory",
                     ("Occupied pages include overlapping model residency, file cache and shared/driver-mapped pages.",))
            cell = (w-18)/2
            self.box(0, 7, cell, 56, "Process view",
                     ("RSS / anonymous / file-backed / shared",))
            self.box(cell+18, 7, cell, 56, "OS pressure view",
                     ("Available includes reclaimable pages",))
            self.arrow(80, 82, 80, 63)
            self.arrow(w-80, 82, w-80, 63)


def make_table(lines, style):
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]
    if len(rows) < 2 or not all(re.fullmatch(r":?-+:?", cell) for cell in rows[1]):
        raise ValueError("Malformed Markdown table")
    rows.pop(1)
    count = len(rows[0])
    if any(len(row) != count for row in rows):
        raise ValueError("Inconsistent table columns")
    proportions = {2: (0.34, 0.66), 3: (0.26, 0.37, 0.37), 4: (0.43, 0.18, 0.24, 0.15)}
    if count not in proportions:
        raise ValueError("Unsupported white-paper table width")
    cells = [[Paragraph(inline(value), style["table_head"] if index == 0 else style["table"])
              for value in row] for index, row in enumerate(rows)]
    table = Table(cells, colWidths=[CONTENT_WIDTH*p for p in proportions[count]], repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [PALE, colors.white]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LINEBELOW", (0, 0), (-1, 0), 1, MINT),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, RULE),
    ]))
    return [table, Spacer(1, 11)]


class PaperDocument(BaseDocTemplate):
    def __init__(self, output, evidence, fingerprint):
        super().__init__(str(output), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                         topMargin=64, bottomMargin=48, pageCompression=1,
                         title=evidence["title"], author="SYNAPSE contributors", invariant=1)
        self.evidence, self.fingerprint = evidence, fingerprint
        frame = Frame(MARGIN, 48, CONTENT_WIDTH, HEIGHT-112, leftPadding=0, rightPadding=0,
                      topPadding=0, bottomPadding=0, id="paper")
        self.addPageTemplates(PageTemplate(id="paper", frames=frame, onPage=self.decorate))
        self.heading_index = 0

    def decorate(self, canvas, doc):
        canvas.setTitle(self.evidence["title"])
        canvas.setAuthor("SYNAPSE contributors")
        canvas.setCreator("SYNAPSE reproducible white-paper builder")
        canvas.setSubject("Research edition; not quality-qualified. Source SHA256: " + self.fingerprint)
        canvas.setKeywords("SYNAPSE, MoE, CPU, GPU, llama.cpp, experimental, technical white paper")
        if doc.page == 1:
            self.cover(canvas)
            return
        canvas.saveState()
        canvas.setStrokeColor(RULE)
        canvas.line(MARGIN, HEIGHT-40, WIDTH-MARGIN, HEIGHT-40)
        canvas.setFillColor(LINK)
        canvas.setFont("Helvetica-Bold", 7.8)
        canvas.drawString(MARGIN, HEIGHT-30, "SYNAPSE / ARCHITECTURE + EVIDENCE")
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 7.2)
        canvas.drawRightString(WIDTH-MARGIN, HEIGHT-30, "EXPERIMENTAL RESEARCH")
        canvas.line(MARGIN, 33, WIDTH-MARGIN, 33)
        canvas.drawString(MARGIN, 20, "RESEARCH EDITION 1.0  |  17 OCTOBER 2026")
        canvas.drawRightString(WIDTH-MARGIN, 20, f"{doc.page:02d}")
        canvas.restoreState()

    def cover(self, canvas):
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, 0, WIDTH, HEIGHT, fill=1, stroke=0)
        canvas.setFillColor(MINT)
        canvas.rect(MARGIN, HEIGHT-118, 56, 3, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 27)
        canvas.setFillColor(colors.white)
        canvas.drawString(MARGIN, HEIGHT-73, "SYNAPSE")
        canvas.setStrokeColor(MINT)
        canvas.setLineWidth(1.8)
        x, y = WIDTH-117, HEIGHT-63
        canvas.circle(x, y, 3, stroke=1, fill=0)
        path = canvas.beginPath()
        path.moveTo(x+4, y)
        for dx, dy in ((16, 0), (22, 8), (28, -7), (34, 0), (45, 0)):
            path.lineTo(x+dx, y+dy)
        canvas.drawPath(path)
        canvas.circle(x+50, y, 3, stroke=1, fill=0)
        canvas.setFillColor(colors.HexColor("#B9D0DB"))
        canvas.setFont("Helvetica", 9)
        canvas.drawString(MARGIN, HEIGHT-94, "TECHNICAL WHITE PAPER / RESEARCH EDITION")
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 35)
        canvas.drawString(MARGIN, HEIGHT-187, "Model-Agnostic")
        canvas.drawString(MARGIN, HEIGHT-231, "Hybrid MoE Inference")
        canvas.setFillColor(colors.HexColor("#C6D9E2"))
        canvas.setFont("Helvetica", 12.2)
        canvas.drawString(MARGIN, HEIGHT-270, "Architecture, benchmark evidence, and validation limits")
        canvas.setFont("Times-Italic", 13)
        canvas.drawString(MARGIN, HEIGHT-308, "A reproducible engineering study of expert residency")
        canvas.drawString(MARGIN, HEIGHT-327, "on commodity CPU/GPU hardware.")
        canvas.setFillColor(colors.HexColor("#1A354A"))
        canvas.roundRect(MARGIN, 306, CONTENT_WIDTH, 115, 8, fill=1, stroke=0)
        canvas.setFillColor(MINT)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawString(MARGIN+18, 393, "RESIDENT GPU EXPERTS")
        canvas.drawString(MARGIN+270, 393, "CPU COLD EXPERTS")
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica", 10)
        canvas.drawString(MARGIN+18, 367, "Placement from observed reuse")
        canvas.drawString(MARGIN+270, 367, "Misses remain in the computation")
        canvas.setStrokeColor(colors.HexColor("#477084"))
        canvas.line(MARGIN+18, 345, WIDTH-MARGIN-18, 345)
        canvas.setFont("Times-Roman", 11)
        canvas.drawString(MARGIN+18, 325, "All selected contributions retained; numerical equivalence still requires validation.")
        canvas.setFillColor(MINT)
        canvas.setFont("Helvetica-Bold", 9.5)
        canvas.drawString(MARGIN, 235, "EXPERIMENTAL. NOT BROADLY QUALITY-QUALIFIED.")
        canvas.setFillColor(colors.white)
        canvas.setFont("Times-Roman", 12)
        canvas.drawString(MARGIN, 212, "Speed measurements are not a model-quality certification.")
        canvas.setFillColor(colors.HexColor("#B9D0DB"))
        canvas.setFont("Helvetica", 9)
        canvas.drawString(MARGIN, 119, "Prepared for developers and technical evaluators")
        canvas.drawString(MARGIN, 101, "Evidence snapshot: 17 October 2026")
        canvas.setFont("Helvetica", 8)
        canvas.drawString(MARGIN, 65, "github.com/appatalks/Synapse")
        canvas.linkURL("https://github.com/appatalks/Synapse", (MARGIN, 60, MARGIN+180, 76))
        canvas.drawRightString(WIDTH-MARGIN, 65, "PROJECT-REPORTED / NOT PEER REVIEWED")
        canvas.restoreState()

    def afterFlowable(self, flowable):
        if getattr(flowable, "paper_heading", False):
            title = flowable.getPlainText()
            if title == "Contents":
                return
            key = "section-" + str(self.heading_index)
            self.heading_index += 1
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(title, key, level=0)
            self.notify("TOCEntry", (0, title, self.page, key))

    def beforeDocument(self):
        self.heading_index = 0


def story_from_markdown(source, evidence, style):
    lines = source.splitlines()
    story = [Spacer(1, HEIGHT-113), PageBreak()]
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line == "<!-- page -->":
            story.append(PageBreak())
            index += 1
        elif line == "<!-- contents -->":
            toc = TableOfContents()
            toc.levelStyles = [style["toc"]]
            toc.dotsMinLevel = 0
            toc.tableStyle = TableStyle([
                ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ])
            story += [toc, Spacer(1, 15)]
            index += 1
        elif line.startswith("<!-- figure: ") and line.endswith(" -->"):
            kind = line[len("<!-- figure: "):-len(" -->")]
            story.append(Diagram(kind, evidence))
            index += 1
        elif line.startswith("<!--"):
            raise ValueError("Unknown paper directive: " + line)
        elif line.startswith("# "):
            heading = Paragraph(inline(line[2:]), style["h1"])
            heading.paper_heading = True
            story.append(heading)
            index += 1
        elif line.startswith("## "):
            story.append(Paragraph(inline(line[3:]), style["h2"]))
            index += 1
        elif line.startswith("|"):
            table = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table.append(lines[index].strip())
                index += 1
            story.extend(make_table(table, style))
        elif line.startswith("```"):
            code = []
            index += 1
            while index < len(lines) and not lines[index].startswith("```"):
                code.append(lines[index])
                index += 1
            if index == len(lines):
                raise ValueError("Unclosed code block")
            for value in code:
                if stringWidth(value, "Courier", 8.5) > CONTENT_WIDTH-20:
                    raise ValueError("Code line exceeds the paper frame")
            block = Table([[Preformatted("\n".join(code), style["code"])]],
                          colWidths=[CONTENT_WIDTH], hAlign="LEFT")
            block.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PALE),
                                        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                                        ("LEFTPADDING", (0, 0), (-1, -1), 10),
                                        ("TOPPADDING", (0, 0), (-1, -1), 9),
                                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
            story += [block, Spacer(1, 9)]
            index += 1
        elif line.startswith("> "):
            text = Paragraph(inline(line[2:]), style["warning"])
            box = Table([[text]], colWidths=[CONTENT_WIDTH], hAlign="LEFT")
            box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), WARNING),
                                      ("LINEBEFORE", (0, 0), (0, -1), 3, RUST),
                                      ("LEFTPADDING", (0, 0), (-1, -1), 13),
                                      ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                                      ("TOPPADDING", (0, 0), (-1, -1), 10),
                                      ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
            story += [box, Spacer(1, 11)]
            index += 1
        elif re.match(r"^\[[0-9]+\] ", line):
            number = re.match(r"^\[([0-9]+)\]", line)[1]
            story.append(Paragraph(f'<a name="ref-{number}"/>' + inline(line, citations=False), style["reference"]))
            index += 1
        elif line.startswith("- ") or re.match(r"^[0-9]+\. ", line):
            marker = "-" if line.startswith("- ") else line.split(" ", 1)[0]
            text = line.split(" ", 1)[1]
            story.append(Paragraph(inline(text), style["bullet"], bulletText=marker))
            index += 1
        else:
            paragraph = [line]
            index += 1
            while index < len(lines) and lines[index].strip():
                following = lines[index].strip()
                if following.startswith(("#", "|", "<!--", ">", "```", "- ")):
                    break
                paragraph.append(following)
                index += 1
            text = " ".join(paragraph)
            kind = "caption" if text.startswith("Figure ") else "body"
            story.append(Paragraph(inline(text), style[kind]))
    return story


def validate_source(source, evidence):
    if source.count("<!-- page -->") != 15:
        raise ValueError("Expected sixteen source pages plus a cover")
    for row in evidence["headline_models"]:
        expected = f"| {row['model']} | {row['control_tok_s']:.2f} | {row['accelerated_tok_s']:.2f} | {row['display_gain_percent']}% |"
        if expected not in source:
            raise ValueError("The prose table differs from reviewed headline evidence: " + row["model"])
        family = re.sub(r" (?:MXFP4|IQ3_S|IQ4_XS|Q8_0)$", "", row["model"])
        budget_rows = [line for line in source.splitlines() if line.startswith("| " + family + " |")]
        if len(budget_rows) != 1 or f"{row['cache_mib']:,} MiB" not in budget_rows[0]:
            raise ValueError("The residency budget differs from the recorded profile: " + family)
    mistral_labels = {
        "native": "Native CPU experts / GPU backbone; new flags off",
        "standard-fp32": "Automatic placement; experimental kernels on",
        "hybrid": "Empty-causal 8 GiB hybrid; experimental kernels on",
    }
    for profile, label in mistral_labels.items():
        value = evidence["mistral_research_only"]["medians"][profile]
        if f"| {label} | {value:.2f} |" not in source:
            raise ValueError("Experimental Mistral table differs from reviewed evidence")
    if "independent native-reference equivalence fails" not in source:
        raise ValueError("The paper must retain the native-equivalence limitation")
    for marker in ("/home/", "/media/", ".copilot/", "Bearer ", "--api-key", "TODO", "TBD"):
        if marker in source:
            raise ValueError("Private data or a placeholder appears in paper source")


def build(output):
    evidence = load_evidence()
    source_path = PAPER / "synapse-whitepaper.md"
    source = source_path.read_text(encoding="utf-8")
    validate_source(source, evidence)
    fingerprint = hashlib.sha256(source_path.read_bytes() + (PAPER / "evidence.json").read_bytes()
                                 + Path(__file__).read_bytes()).hexdigest()
    date = dt.date.fromisoformat(evidence["publication_date"])
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".building")
    with temporary.open("xb"):
        pass
    previous_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = str(int(dt.datetime.combine(date, dt.time(12), dt.timezone.utc).timestamp()))
    try:
        document = PaperDocument(temporary, evidence, fingerprint)
        document.multiBuild(story_from_markdown(source, evidence, styles()))
        temporary.replace(output)
    finally:
        if previous_epoch is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = previous_epoch
        if temporary.exists():
            temporary.unlink()
    print(f"{output} | ReportLab {Version} | source {fingerprint}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PAPER / "synapse-whitepaper.pdf")
    args = parser.parse_args()
    build(args.output.resolve())


if __name__ == "__main__":
    main()
