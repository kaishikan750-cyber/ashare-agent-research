"""Build the Chinese study guide with ReportLab; render separately for visual QA."""
from __future__ import annotations

from html import escape
from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
    Flowable, KeepTogether,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs' / 'agent_learning_guide.md'
OUTPUT = ROOT / 'output' / 'pdf' / 'Agent项目实战学习手册_LangGraph_FastAPI_MCP.pdf'
FONT_ROOT = Path('C:/Windows/Fonts')
pdfmetrics.registerFont(TTFont('ZH', str(FONT_ROOT / 'msyh.ttc'), subfontIndex=0))
pdfmetrics.registerFont(TTFont('ZHB', str(FONT_ROOT / 'msyhbd.ttc'), subfontIndex=0))
pdfmetrics.registerFont(TTFont('Mono', str(FONT_ROOT / 'consola.ttf')))
INK = colors.HexColor('#193436')
MUTED = colors.HexColor('#667E7B')
TEAL = colors.HexColor('#08796D')
PALE = colors.HexColor('#F1F6F2')
LINE = colors.HexColor('#D9E4DF')
PAGE_W, PAGE_H = A4
WIDTH = PAGE_W - 104

STYLES = {
    'body': ParagraphStyle('Body', fontName='ZH', fontSize=10.1, leading=16.7,
        textColor=INK, wordWrap='CJK', spaceAfter=9.0),
    'h3': ParagraphStyle('Section', fontName='ZHB', fontSize=11.7, leading=18,
        textColor=TEAL, spaceBefore=9, spaceAfter=6, keepWithNext=True),
    'title': ParagraphStyle('Chapter', fontName='ZHB', fontSize=22, leading=31,
        textColor=INK, spaceAfter=16, wordWrap='CJK'),
    'table': ParagraphStyle('Cell', fontName='ZH', fontSize=8.9, leading=13.6,
        textColor=INK, wordWrap='CJK'),
    'th': ParagraphStyle('HeaderCell', fontName='ZHB', fontSize=8.9, leading=13.6,
        textColor=TEAL, wordWrap='CJK'),
    'toc': ParagraphStyle('Contents', fontName='ZH', fontSize=9.3, leading=16,
        textColor=INK, wordWrap='CJK'),
}


def markup(text):
    text = escape(text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<font name="ZHB">\1</font>', text)
    return text


class CodeBlock(Flowable):
    """Embedded monospace Latin with Chinese fallback, no missing glyphs."""
    def __init__(self, source, language=''):
        super().__init__()
        self.source, self.language = source, language
        self.fontsize = 8.8
        self.leading = 12.9

    def text_width(self, text):
        return sum(pdfmetrics.stringWidth(ch, 'Mono' if ord(ch) < 256 else 'ZH', self.fontsize) for ch in text)

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        self.lines = []
        for line in self.source.splitlines():
            buf = ''
            for ch in line:
                if self.text_width(buf + ch) > availWidth - 28 and buf:
                    self.lines.append(buf)
                    buf = '    ' + ch
                else:
                    buf += ch
            self.lines.append(buf)
        self.height = 35 + max(1, len(self.lines)) * self.leading
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setFillColor(PALE)
        c.roundRect(0, 0, self.width, self.height, 7, fill=1, stroke=0)
        c.setFillColor(TEAL)
        c.setFont('Mono', 7.5)
        c.drawString(13, self.height - 17, self.language.upper() or 'CODE')
        for i, line in enumerate(self.lines):
            x, y = 13, self.height - 34 - i * self.leading
            runs = re.findall(r'[\x00-\xff]+|[^\x00-\xff]+', line)
            for run in runs:
                font = 'Mono' if ord(run[0]) < 256 else 'ZH'
                c.setFont(font, self.fontsize)
                c.setFillColor(INK)
                c.drawString(x, y, run)
                x += pdfmetrics.stringWidth(run, font, self.fontsize)


class Cover(Flowable):
    def wrap(self, w, h):
        self.width, self.height = w, 700
        return w, 700

    def draw(self):
        c = self.canv
        def text(x, y, s, font='ZH', size=12, color=INK):
            c.setFont(font, size); c.setFillColor(color); c.drawString(x, y, s)
        text(0, 654, 'BUILD / UNDERSTAND / EXPLAIN', 'Mono', 11, TEAL)
        text(0, 592, '从 Python 研究脚本', 'ZHB', 29)
        text(0, 547, '到 Agent 服务', 'ZHB', 36)
        text(0, 504, 'LangGraph、LangChain、FastAPI 与 MCP', 'ZH', 15, MUTED)
        text(0, 478, '基于你的 A 股隔夜反转项目，逐层拆解真实代码。', 'ZH', 12, MUTED)
        c.setStrokeColor(LINE); c.line(0, 448, self.width, 448)
        layers = [
            ('01', '确定性研究核心', '数据校验 / 因子 / T+1 回测'),
            ('02', '工具与流程', '输入契约 / LangGraph / 模型工具循环'),
            ('03', '服务与协议', 'FastAPI / 后台实验 / MCP / 浏览器'),
        ]
        for i, (num, label, desc) in enumerate(layers):
            y = 371 - i * 75
            c.setFillColor(PALE); c.roundRect(0, y - 13, self.width, 60, 7, fill=1, stroke=0)
            text(15, y + 5, num, 'Mono', 20, TEAL)
            text(65, y + 15, label, 'ZHB', 13)
            text(65, y - 5, desc, 'ZH', 10, MUTED)
        text(0, 108, '30 节 / 代码拆解 / 动手练习 / 面试追问', 'ZHB', 13)
        text(0, 78, '适合：会基础 Python，刚开始学习 Agent 的实习求职者。', 'ZH', 11, MUTED)
        text(0, 32, '2026.10.09  |  PROJECT EDITION 0.2', 'Mono', 9, MUTED)
        text(0, 11, '依据本地源码制作；能力与限制均按实际实现说明。', 'ZH', 9, MUTED)


def table_flow(lines):
    rows = []
    for line in lines:
        cells = [v.strip() for v in line.strip().strip('|').split('|')]
        if all(re.fullmatch(r'[:\- ]+', v) for v in cells):
            continue
        rows.append(cells)
    n = len(rows[0])
    if n == 3:
        widths = [WIDTH * 0.21, WIDTH * 0.33, WIDTH * 0.46]
    else:
        widths = [WIDTH * 0.37, WIDTH * 0.63]
    values = [[Paragraph(markup(cell), STYLES['th' if i == 0 else 'table']) for cell in row] for i, row in enumerate(rows)]
    t = Table(values, colWidths=widths, hAlign='LEFT', repeatRows=1)
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (-1, 0), PALE),
        ('LINEBELOW', (0, 0), (-1, 0), .7, LINE),
        ('LINEBELOW', (0, 1), (-1, -1), .35, LINE),
        ('LEFTPADDING', (0, 0), (-1, -1), 9),
        ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    return [t, Spacer(1, 10)]


def parse_body(text):
    lines = text.strip().splitlines()
    flow, i = [], 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1; continue
        if line.startswith('```'):
            language = line[3:]
            block = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                block.append(lines[i]); i += 1
            flow.extend([CodeBlock('\n'.join(block), language), Spacer(1, 10)])
            i += 1; continue
        if line.startswith('|'):
            block = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                block.append(lines[i]); i += 1
            flow.extend(table_flow(block)); continue
        if line.startswith('### '):
            flow.append(Paragraph(markup(line[4:]), STYLES['h3']))
            i += 1; continue
        block = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith(('###', '```', '|')):
            block.append(lines[i].strip()); i += 1
        flow.append(Paragraph(markup(' '.join(block)), STYLES['body']))
    return flow


class BookDoc(SimpleDocTemplate):
    def afterFlowable(self, flowable):
        if getattr(flowable, 'chapter_id', None):
            self.canv.bookmarkPage(flowable.chapter_id)
            self.canv.addOutlineEntry(flowable.getPlainText(), flowable.chapter_id, 0)


def page_decoration(canvas, doc):
    canvas.saveState()
    if doc.page == 1:
        canvas.setFillColor(TEAL)
        canvas.rect(0, PAGE_H - 13, PAGE_W, 13, fill=1, stroke=0)
    else:
        canvas.setFont('ZH', 8.4)
        canvas.setFillColor(MUTED)
        canvas.drawString(52, PAGE_H - 30, 'Agent 项目实战学习手册')
        canvas.setFont('Mono', 7.5)
        canvas.drawRightString(PAGE_W - 52, PAGE_H - 30, 'PROJECT 0.2 / LEARNING EDITION')
        canvas.setStrokeColor(LINE)
        canvas.line(52, PAGE_H - 40, PAGE_W - 52, PAGE_H - 40)
    canvas.setStrokeColor(LINE)
    canvas.line(52, 44, PAGE_W - 52, 44)
    canvas.setFont('ZH', 8.1)
    canvas.setFillColor(MUTED)
    canvas.drawString(52, 28, '先验证工具证据，再解释模型结论。')
    canvas.setFont('Mono', 9)
    canvas.drawRightString(PAGE_W - 52, 28, f'{doc.page:02d}')
    canvas.restoreState()


def build():
    text = SOURCE.read_text(encoding='utf-8')
    sections = []
    for match in re.finditer(r'^## (.+)\n([\s\S]*?)(?=^## |\Z)', text, re.M):
        sections.append((match.group(1), match.group(2)))
    assert len(sections) == 30
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    story = [Cover(), PageBreak()]
    toc_title = Paragraph('阅读导航', STYLES['title'])
    toc_title.chapter_id = 'contents'
    story += [toc_title, Paragraph('按编号学习；PDF 侧栏书签可直接跳到章节。', STYLES['body']), Spacer(1, 7)]
    toc_rows = []
    for i, (title, _) in enumerate(sections):
        label = escape(title)
        toc_rows.append([Paragraph(f'<link href="#chapter-{i + 1}" color="#193436">{label}</link>', STYLES['toc']),
                         Paragraph(str(i + 3), STYLES['toc'])])
    toc = Table(toc_rows, colWidths=[WIDTH - 27, 27], hAlign='LEFT')
    toc.setStyle(TableStyle([('LEFTPADDING', (0,0), (-1,-1), 0), ('RIGHTPADDING',(0,0),(-1,-1),0),
                            ('TOPPADDING',(0,0),(-1,-1),1.2), ('BOTTOMPADDING',(0,0),(-1,-1),1.2),
                            ('VALIGN',(0,0),(-1,-1),'TOP')]))
    story += [toc, PageBreak()]
    for i, (title, body) in enumerate(sections):
        num, rest = title.split(' ', 1)
        story += [Paragraph(f'LESSON {num} / BUILD IT STEP BY STEP', ParagraphStyle('Kicker',fontName='Mono',fontSize=8.5,leading=12,textColor=TEAL,spaceAfter=9))]
        heading = Paragraph(markup(rest), STYLES['title'])
        heading.chapter_id = f'chapter-{i + 1}'
        story.append(heading)
        story.extend(parse_body(body))
        if i < len(sections) - 1:
            story.append(PageBreak())
    doc = BookDoc(str(OUTPUT), pagesize=A4, rightMargin=52, leftMargin=52,
        topMargin=61, bottomMargin=56, title='从 Python 研究脚本到 Agent 服务',
        author='项目学习手册', subject='LangGraph / LangChain / FastAPI / MCP 实战',
        pageCompression=1)
    doc.build(story, onFirstPage=page_decoration, onLaterPages=page_decoration)
    print(OUTPUT)


if __name__ == '__main__':
    build()
