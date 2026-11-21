"""Slide primitives for the deck (§17.4): native, editable PowerPoint (python-pptx). Every number goes through `n()`
or a chart, so it lands in the numbers manifest; every slide carries the made-up label; slides with numbers carry
the source line with the engine run."""
from collections.abc import Sequence
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_TICK_LABEL_POSITION
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

from txg.deck.facts import Fact
from txg.deck.manifest import Entry, Manifest

# The prototype's light-mode tokens (globals.css), so the deck and the product look like one thing.
INK, MUTED, PAPER, SERIES, ACT, RULE = (RGBColor.from_string(c) for c in
                                         ("14213D", "5B6475", "F7F8FA", "2A78D6", "B42318", "D9DDE5"))
FONT = "Arial"
LABEL = "Example Holding — made-up data"
W, H = Inches(13.333), Inches(7.5)
MARGIN = Inches(0.6)


def chart_value(fact: Fact) -> float:
    """What a chart plots for a fact: SAR in millions, ratios in percent, everything else as is."""
    v = fact.number()
    if v is None:
        raise ValueError(f"fact {fact.fact_id} is not a number")
    return round(v / 1e6 if fact.unit == "sar_m" else v * 100 if fact.unit in ("pct", "pts") else v, 6)


class DeckWriter:
    def __init__(self, run_id: str, label: bool = True):
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = W, H
        self.manifest = Manifest(run_id)
        self.label = label
        self.screens = Path(".")  # where the prototype's screens were captured
        self._pending: list[Fact] = []
        self._numbered: set[int] = set()

    # --- numbers -------------------------------------------------------------------------------------------------
    def n(self, fact: Fact) -> str:
        """The text of a fact, recorded for the slide that next receives content."""
        self._pending.append(fact)
        return fact.text()

    def _claim(self, index: int) -> None:
        for fact in self._pending:
            self.manifest.add(Entry(index, fact.fact_id, fact.text(), str(fact.value)))
            self._numbered.add(index)
        self._pending = []

    # --- slides --------------------------------------------------------------------------------------------------
    def slide(self, title: str, txg: bool = False, kicker: str = ""):
        s = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        s.background.fill.solid()
        s.background.fill.fore_color.rgb = PAPER
        index = len(self.prs.slides)
        self._claim(index)
        if kicker:
            self._box(s, kicker, MARGIN, Inches(0.35), W - 2 * MARGIN, Inches(0.35), 12, MUTED)
        self._box(s, title, MARGIN, Inches(0.6), W - 2 * MARGIN, Inches(1.1), 28, INK, bold=True, name="title")
        if txg:
            self._box(s, "Prepared for TXG Group", MARGIN, H - Inches(1.2), Inches(6), Inches(0.4), 14, MUTED)
        if self.label:
            self._box(s, LABEL, W - Inches(4.1), Inches(0.12), Inches(3.5), Inches(0.3), 10, ACT,
                      align=PP_ALIGN.RIGHT, name="made_up_label")
        return s

    def _box(self, s, text: str, x, y, w, h, size: int, color, bold: bool = False, align=PP_ALIGN.LEFT,
             name: str = ""):
        box = s.shapes.add_textbox(x, y, w, h)
        if name:
            box.name = name
        frame = box.text_frame
        frame.word_wrap = True
        for i, line in enumerate(text.split("\n")):
            p = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
            p.alignment = align
            run = p.add_run()
            run.text = line
            run.font.size, run.font.bold, run.font.name = Pt(size), bold, FONT
            run.font.color.rgb = color
        return box

    def text(self, s, text: str, x=None, y=None, w=None, h=None, size: int = 16, color=INK):
        self._claim(self._index(s))
        return self._box(s, text, x or MARGIN, y or Inches(1.8), w or W - 2 * MARGIN, h or Inches(4.6), size, color)

    def bullets(self, s, lines: Sequence[str], **kw):
        return self.text(s, "\n".join(f"•  {ln}" for ln in lines), **kw)

    def _index(self, s) -> int:
        return next(i for i, x in enumerate(self.prs.slides, start=1) if x.slide_id == s.slide_id)

    def bar_chart(self, s, title: str, categories: Sequence[str], facts: Sequence[Fact], x=None, y=None, w=None,
                  h=None, horizontal: bool = False):
        index = self._index(s)
        self._claim(index)
        data = CategoryChartData()
        data.categories = list(categories)
        data.add_series(title, [chart_value(f) for f in facts])
        kind = XL_CHART_TYPE.BAR_CLUSTERED if horizontal else XL_CHART_TYPE.COLUMN_CLUSTERED
        frame = s.shapes.add_chart(kind, x or MARGIN, y or Inches(1.9), w or Inches(7.4), h or Inches(4.6), data)
        chart = frame.chart
        chart.has_legend = False
        chart.has_title = True
        chart.chart_title.text_frame.text = title
        chart.chart_title.text_frame.paragraphs[0].runs[0].font.size = Pt(13)
        chart.plots[0].series[0].format.fill.solid()
        chart.plots[0].series[0].format.fill.fore_color.rgb = SERIES
        chart.plots[0].series[0].invert_if_negative = False  # else negative bars render above zero or hollow
        values = [chart_value(f) for f in facts]
        if min(values) >= 0:
            chart.value_axis.minimum_scale = 0  # never a truncated axis
        chart.plots[0].has_data_labels = True
        chart.plots[0].data_labels.font.size = Pt(11)
        units = {f.unit for f in facts}
        chart.plots[0].data_labels.number_format = "0" if units == {"count"} else "0.00" if units == {"pts"} else "0.0"
        chart.plots[0].data_labels.number_format_is_linked = False
        chart.value_axis.has_major_gridlines = False
        chart.value_axis.tick_labels.font.size = Pt(10)
        chart.category_axis.tick_labels.font.size = Pt(10)
        chart.category_axis.tick_label_position = XL_TICK_LABEL_POSITION.LOW  # clear of negative bars
        if horizontal:
            chart.category_axis.reverse_order = True  # first category on top, as read
        for f in facts:
            self.manifest.add(Entry(index, f.fact_id, f.text(), str(f.value), where="chart"))
        self._numbered.add(index)
        return chart

    def table(self, s, header: Sequence[str], rows: Sequence[Sequence[str]], x=None, y=None, w=None, size: int = 12,
              widths: Sequence[float] | None = None):
        self._claim(self._index(s))
        width = w or W - 2 * MARGIN
        row_h = Emu(int(Pt(size) * 2.1))
        shape = s.shapes.add_table(len(rows) + 1, len(header), x or MARGIN, y or Inches(1.8), width,
                                   row_h * (len(rows) + 1))
        for row in shape.table.rows:
            row.height = row_h
        if widths:  # fractions of the table width
            for col, share in zip(shape.table.columns, widths):
                col.width = Emu(int(width * share))
        for c, head in enumerate(header):
            self._cell(shape.table.cell(0, c), head, size, bold=True)
        for r, row in enumerate(rows, start=1):
            for c, value in enumerate(row):
                self._cell(shape.table.cell(r, c), value, size)
        return shape

    @staticmethod
    def _cell(cell, text: str, size: int, bold: bool = False) -> None:
        cell.text = text
        run = cell.text_frame.paragraphs[0].runs[0]
        run.font.size, run.font.bold, run.font.name = Pt(size), bold, FONT
        run.font.color.rgb = INK
        cell.margin_top = cell.margin_bottom = Pt(2)

    def image(self, s, path: Path, x=None, y=None, w=None, h=None):
        if not path.is_file():
            return self._box(s, f"Screen not captured: {path.name}", x or MARGIN, y or Inches(1.9),
                             w or Inches(6), Inches(0.5), 12, ACT)
        return s.shapes.add_picture(str(path), x or MARGIN, y or Inches(1.9), w, h)

    def save(self, path: Path) -> None:
        for i, s in enumerate(self.prs.slides, start=1):
            if i in self._numbered:
                self._box(s, f"Example Holding, made-up data; engine run {self.manifest.run_id}", MARGIN,
                          H - Inches(0.5), Inches(8), Inches(0.3), 9, MUTED, name="source_line")
            self._box(s, str(i), W - Inches(1.0), H - Inches(0.5), Inches(0.5), Inches(0.3), 9, MUTED,
                      align=PP_ALIGN.RIGHT, name="slide_number")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.prs.save(str(path))


__all__ = ["DeckWriter", "Emu", "Inches", "chart_value"]
