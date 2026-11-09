"""Build the editable native Power BI project from the validated CSV exports.

Run: .\\.venv\\Scripts\\python.exe -m src.build_powerbi_project
Open the resulting .pbip in Desktop, Refresh, then Save As .pbix.
This generator authors the report; Desktop performs the actual DAX evaluation.
"""

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .download_data import PROJECT_ROOT


NAME = "Credit_Risk_Repayment_Analytics"
OUTPUT = PROJECT_ROOT / "powerbi"
EXPORTS = PROJECT_ROOT / "data" / "exports"
REPORT = OUTPUT / f"{NAME}.Report"
MODEL = OUTPUT / f"{NAME}.SemanticModel"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/"
NAVY, BLUE, TEAL, GREY = "#162D47", "#2878B5", "#147D85", "#526578"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def schema(family, version):
    return SCHEMA + f"item/report/definition/{family}/{version}/schema.json"


def identifier(label):
    """Stable IDs make a regenerated project easy to review in Git."""
    return hashlib.sha256(label.encode()).hexdigest()[:20]


def literal(value):
    if isinstance(value, bool):
        text = str(value).lower()
    elif isinstance(value, (int, float)):
        text = f"{value}D"
    else:
        text = "'" + str(value).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": text}}}


def colour(value):
    return {"solid": {"color": literal(value)}}


def properties(**kwargs):
    return [{"properties": kwargs}]


def field(table, name, measure=False):
    return {"Measure" if measure else "Column": {
        "Expression": {"SourceRef": {"Entity": table}}, "Property": name}}


def projection(table, name, measure=False, label=None):
    result = {"field": field(table, name, measure), "queryRef": f"{table}.{name}",
              "nativeQueryRef": name}
    if label:
        result["displayName"] = label
    return result


def measures():
    """Use the learner-readable DAX file as the single source of measure logic."""
    dax = (OUTPUT / "measures.dax").read_text(encoding="utf-8")
    dax = re.sub(r"^//.*$", "", dax, flags=re.MULTILINE).strip()
    result = []
    for block in re.split(r"\n\s*\n", dax):
        if not block.strip():
            continue
        name, expression = block.strip().split("=", 1)
        name = name.strip()
        percent = "Rate" in name or "Share" in name
        result.append({"name": name, "expression": expression.strip().splitlines(),
                       "formatString": "0.00%" if percent else "#,0",
                       "displayFolder": "Report measures"})
    assert len(result) == 18, "Review parsing when adding or removing DAX measures"
    return result


def build_model():
    # Desktop can convert model.bim to TMDL when saving. Both formats cannot
    # coexist. Preserve that Desktop-generated folder before regenerating TMSL.
    converted = MODEL / "definition"
    if converted.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = PROJECT_ROOT / ".cache" / "powerbi_backups" / stamp / "definition"
        root = PROJECT_ROOT.resolve()
        if not converted.resolve().is_relative_to(root) or not backup.resolve().is_relative_to(root):
            raise ValueError("Power BI backup paths must stay inside the project")
        backup.parent.mkdir(parents=True, exist_ok=True)
        converted.rename(backup)
        print(f"Preserved Desktop's converted TMDL model at {backup}")
    tables = []
    labels = {"month", "month_label", "sex_label", "education_label", "marriage_label",
              "latest_status_group", "credit_limit_band", "age_band", "repayment_status_group"}
    sorts = {"credit_limit_band": "credit_limit_band_order", "age_band": "age_band_order",
             "latest_status_group": "latest_status_group_order", "month_label": "month_order"}
    for name in ("customers", "monthly_repayments", "default_outcomes", "calendar_months"):
        path = EXPORTS / f"{name}.csv"
        frame = pd.read_csv(path, nrows=10)
        columns, types = [], []
        for column in frame.columns:
            if column == "month_start":
                dtype, mtype = "dateTime", "type date"
            elif column in labels:
                dtype, mtype = "string", "type text"
            elif column == "latest_bill_to_limit":
                dtype, mtype = "double", "type number"
            else:
                dtype, mtype = "int64", "Int64.Type"
            item = {"name": column, "dataType": dtype, "sourceColumn": column, "summarizeBy": "none"}
            if column in sorts:
                item["sortByColumn"] = sorts[column]
            if column.endswith("_order") or column == "customer_id":
                item["isHidden"] = True
            if dtype == "dateTime":
                item["formatString"] = "MMM yyyy"
            elif dtype == "int64":
                item["formatString"] = "#,0"
            columns.append(item)
            types.append('{"' + column + '", ' + mtype + '}')
        # A named Power Query parameter keeps the CSV location editable in Desktop.
        expression = ["let", f'    Source = Csv.Document(File.Contents(DataFolder & "\\{name}.csv"),',
                      f'        [Delimiter=",", Columns={len(columns)}, Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
                      '    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),',
                      '    Typed = Table.TransformColumnTypes(Headers, {' + ', '.join(types) + '}, "en-US")',
                      "in", "    Typed"]
        table = {"name": name, "columns": columns, "partitions": [
            {"name": name, "mode": "import", "source": {"type": "m", "expression": expression}}]}
        if name == "customers":
            table["measures"] = measures()
        tables.append(table)
    relationships = []
    for fact, key, dimension, dim_key in (
        ("monthly_repayments", "customer_id", "customers", "customer_id"),
        ("default_outcomes", "customer_id", "customers", "customer_id"),
        ("monthly_repayments", "month_start", "calendar_months", "month_start"),
    ):
        relationships.append({"name": f"{fact}_{dimension}", "fromTable": fact, "fromColumn": key,
                              "toTable": dimension, "toColumn": dim_key, "fromCardinality": "many",
                              "toCardinality": "one", "crossFilteringBehavior": "oneDirection"})
    model = {"name": NAME, "compatibilityLevel": 1601, "model": {
        "culture": "en-US", "sourceQueryCulture": "en-US", "defaultPowerBIDataSourceVersion": "powerBI_V3",
        "expressions": [{"name": "DataFolder", "kind": "m", "expression":
                         '"' + str(EXPORTS) + '" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]'}],
        "tables": tables, "relationships": relationships,
        "annotations": [{"name": "PBI_QueryOrder", "value": json.dumps([t["name"] for t in tables])}]
    }}
    write_json(MODEL / "model.bim", model)
    write_json(MODEL / "definition.pbism", {
        "$schema": SCHEMA + "item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.0", "settings": {"qnaEnabled": False}})


class Page:
    def __init__(self, name, title, subtitle):
        self.name = identifier(name)
        self.directory = REPORT / "definition" / "pages" / self.name
        self.count = 0
        write_json(self.directory / "page.json", {
            "$schema": schema("page", "2.0.0"), "name": self.name, "displayName": name,
            "displayOption": "FitToPage", "width": 1280, "height": 800,
            "objects": {"background": properties(color=colour("#F3F6FA"), transparency=literal(0))}})
        self.text(title, 24, 12, 1232, 54, 28, NAVY)
        self.text(subtitle, 24, 66, 1232, 38, 14, GREY)
        self.text("UCI 350 | Taiwan, Apr-Sep 2005 | NTD | Historical sample; not Finnable data. Associations do not establish causation.",
                  24, 758, 1232, 30, 12, GREY)

    def add(self, visual, x, y, width, height):
        self.count += 1
        vid = identifier(f"{self.name}-{self.count}")
        write_json(self.directory / "visuals" / vid / "visual.json", {
            "$schema": schema("visualContainer", "2.4.0"), "name": vid,
            "position": {"x": x, "y": y, "z": self.count * 1000, "width": width,
                         "height": height, "tabOrder": self.count * 1000}, "visual": visual})

    def text(self, text, x, y, width, height, size=14, color=NAVY):
        self.add({"visualType": "textbox", "objects": {"general": properties(paragraphs=[{
            "textRuns": [{"value": text, "textStyle": {"fontFamily": "Segoe UI", "fontSize": f"{size}px", "color": color}}],
            "horizontalTextAlignment": "left"}])}, "visualContainerObjects": {
                "background": properties(show=literal(False)), "border": properties(show=literal(False)),
                "padding": properties(top=literal(0), bottom=literal(0), left=literal(0), right=literal(0))}},
                 x, y, width, height)

    def container(self, title):
        return {"title": properties(show=literal(True), text=literal(title), fontSize=literal(13),
                                     fontColor=colour(NAVY)),
                "background": properties(show=literal(True), color=colour("#FFFFFF"), transparency=literal(0)),
                "border": properties(show=literal(False))}

    def card(self, measure, label, x, y=120, width=296, height=112):
        container = self.container("")
        container["title"] = properties(show=literal(False))
        self.add({"visualType": "cardVisual", "query": {"queryState": {
            "Data": {"projections": [projection("customers", measure, True, label)]}}},
            "objects": {
                "value": [{"properties": {"fontSize": literal(20 if "NTD" in measure else 27),
                           "fontColor": colour(TEAL), "labelDisplayUnits": literal(1)}, "selector": {"id": "default"}}],
                "label": [{"properties": {"fontSize": literal(11)}, "selector": {"id": "default"}}],
                "outline": [{"properties": {"show": literal(False)}, "selector": {"id": "default"}}],
                "padding": [{"properties": {"paddingUniform": literal(8)}, "selector": {"id": "default"}}]},
            "visualContainerObjects": container}, x, y, width, height)

    def chart(self, kind, title, table, column, measure, x, y, width, height, series=None):
        query = {"Category": {"projections": [projection(table, column)]},
                 "Y": {"projections": [projection("customers", measure, True)]},
                 "Tooltips": {"projections": [projection("customers", "Customer Count" if table == "customers" else "Monthly Rows", True)]}}
        if series:
            query["Series"] = {"projections": [projection(*series)]}
        formatting = {"labels": properties(show=literal(True), fontSize=literal(10)),
                      "categoryAxis": properties(showAxisTitle=literal(False), fontSize=literal(10)),
                      "valueAxis": properties(showAxisTitle=literal(False), fontSize=literal(10))}
        if series:
            # Let the theme distinguish series; one default colour would hide the mix.
            formatting["legend"] = properties(showTitle=literal(False), position=literal("Bottom"), fontSize=literal(9))
        else:
            formatting["dataPoint"] = properties(defaultColor=colour(BLUE))
        self.add({"visualType": kind, "query": {"queryState": query, "sortDefinition": {
            "sort": [{"field": field(table, column), "direction": "Ascending"}]}},
            "objects": formatting,
            "visualContainerObjects": self.container(title)}, x, y, width, height)

    def slicer(self, title, table, column, x, y, width, height):
        self.add({"visualType": "slicer", "query": {"queryState": {
            "Values": {"projections": [projection(table, column)]}}, "sortDefinition": {
                "sort": [{"field": field(table, column), "direction": "Ascending"}]}},
            "objects": {"data": properties(mode=literal("Basic")),
                        "selection": properties(singleSelect=literal(False), selectAllCheckboxEnabled=literal(True)),
                        "header": properties(show=literal(False)), "items": properties(textSize=literal(11))},
            "visualContainerObjects": self.container(title)}, x, y, width, height)

    def table(self, title, projections, x, y, width, height):
        self.add({"visualType": "tableEx", "query": {"queryState": {"Values": {"projections": projections}}},
                  "objects": {"grid": properties(textSize=literal(11))},
                  "visualContainerObjects": self.container(title)}, x, y, width, height)


def build_report():
    for directory, kind in ((REPORT, "Report"), (MODEL, "SemanticModel")):
        write_json(directory / ".platform", {
            "$schema": SCHEMA + "gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": kind, "displayName": NAME},
            "config": {"version": "2.0", "logicalId": str(uuid.uuid5(uuid.NAMESPACE_URL, NAME + kind))}})
    write_json(OUTPUT / f"{NAME}.pbip", {"$schema": SCHEMA + "pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0", "artifacts": [{"report": {"path": REPORT.name}}], "settings": {"enableAutoRecovery": True}})
    write_json(REPORT / "definition.pbir", {"$schema": SCHEMA + "item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0", "datasetReference": {"byPath": {"path": "../" + MODEL.name}}})
    write_json(REPORT / "definition" / "version.json", {"$schema": schema("versionMetadata", "1.0.0"), "version": "2.0.0"})
    write_json(REPORT / "definition" / "report.json", {"$schema": schema("report", "3.0.0"),
        "themeCollection": {"baseTheme": {"name": "CY24SU06", "type": "SharedResources", "reportVersionAtImport": {
            "visual": "2.4.0", "page": "2.0.0", "report": "3.0.0"}}},
        "resourcePackages": [{"name": "SharedResources", "type": "SharedResources", "items": [
            {"name": "CY24SU06", "path": "BaseThemes/CY24SU06.json", "type": "BaseTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized",
                     "defaultFilterActionIsDataFilter": True}})

    portfolio = Page("01 Portfolio", "Credit risk & repayment behaviour", "01 / PORTFOLIO     Explore how observed default differs across customer segments.")
    for index, (measure, label) in enumerate([("Customer Count", "Customers"), ("Defaulting Customers", "Next-month defaults"),
                                            ("Default Rate", "Observed default rate"), ("Credit Limit NTD", "Credit limits (NTD)")]):
        portfolio.card(measure, label, 24 + index * 312)
    portfolio.chart("clusteredBarChart", "Default rate by September repayment status", "customers", "latest_status_group", "Default Rate", 24, 250, 756, 270)
    portfolio.slicer("Credit-limit band (NTD)", "customers", "credit_limit_band", 800, 250, 220, 270)
    portfolio.slicer("Customer age", "customers", "age_band", 1036, 250, 220, 270)
    portfolio.chart("clusteredColumnChart", "Default rate by number of documented-delay months", "customers", "delayed_months", "Default Rate", 24, 538, 756, 200)
    portfolio.text("HOW TO READ\nSelect a segment to inspect its rate and customer count.\n\nCodes -2 and 0 are undocumented. A higher observed rate is a signal to investigate, not proof of cause or a lending rule.", 800, 540, 456, 198, 16)

    history = Page("02 Repayment history", "Repayment history & data quality", "02 / HISTORY     Each row is one customer in one month. Month filters do not change the base outcome rate.")
    for index, (measure, label) in enumerate([("Monthly Rows", "Customer-month rows"), ("Monthly Customers", "Distinct customers"),
                                            ("Undocumented Status Share", "Undocumented status share"), ("Recorded Payments NTD", "Recorded payments (NTD)")]):
        history.card(measure, label, 24 + index * 312)
    history.slicer("History month", "calendar_months", "month_label", 24, 250, 220, 320)
    history.chart("hundredPercentStackedColumnChart", "Repayment-status mix by month", "calendar_months", "month_label", "Monthly Rows", 260, 250, 650, 300,
                  series=("monthly_repayments", "repayment_status_group"))
    history.card("Single Month Bill NTD", "Bills: select exactly one month", 930, 250, 326, 132)
    history.text("DATA QUALITY\nCodes -2 and 0 remain explicitly undocumented.\n\nCode 1: 28 rows in Aug versus 3,688 in Sep. Check coding and timing before calling this deterioration.", 930, 400, 326, 228, 16)
    history.chart("lineChart", "Share of rows with documented delay (codes 1+)", "calendar_months", "month_label", "Documented Delay Share", 260, 568, 650, 170)
    history.text("Bills are monthly statement amounts. The bill card stays blank with multiple months to prevent summing balances over time.", 24, 610, 220, 128, 14)

    cohort = Page("03 Cohort investigation", "Investigate a repayment cohort", "03 / COHORTS     History selections identify distinct customers; their future outcomes are counted once.")
    for index, (measure, label) in enumerate([("Selected History Customers", "Selected customers"), ("Defaults in Selected History Cohort", "Selected defaults"),
                                            ("Selected History Cohort Default Rate", "Cohort default rate"), ("Credit Limit in Selected History Cohort NTD", "Cohort credit limits (NTD)")]):
        cohort.card(measure, label, 24 + index * 312)
    cohort.slicer("History month", "calendar_months", "month_label", 24, 250, 220, 290)
    cohort.slicer("Repayment status", "monthly_repayments", "repayment_status_group", 260, 250, 280, 290)
    cohort.slicer("Credit-limit band (NTD)", "customers", "credit_limit_band", 556, 250, 220, 290)
    cohort.card("Default Rate", "Base customer-segment rate", 800, 250, 456, 120)
    cohort.text("INTERVIEW CHECK\nSelect Sep 2005 and 2+ months delay:\n3,130 customers | 2,177 defaults | 69.55%\n\nThe base rate stays 22.12% until a customer attribute is filtered. Multi-month cohorts use distinct customer IDs.", 800, 388, 456, 160, 15)
    cohort.table("Cohort outcomes by credit-limit band", [projection("customers", "credit_limit_band", label="Credit band"),
                 projection("customers", "Selected History Customers", True, "Customers"),
                 projection("customers", "Defaults in Selected History Cohort", True, "Defaults"),
                 projection("customers", "Selected History Cohort Default Rate", True, "Default rate")], 24, 558, 752, 180)
    cohort.text("BUSINESS NEXT STEP\nTest supportive outreach with a control group. This historical association cannot estimate collections uplift, recovery ROI, or policy effectiveness.", 800, 568, 456, 170, 16)

    pages = [portfolio.name, history.name, cohort.name]
    write_json(REPORT / "definition" / "pages" / "pages.json", {
        "$schema": schema("pagesMetadata", "1.1.0"), "pageOrder": pages, "activePageName": pages[0]})
    return sum(page.count for page in (portfolio, history, cohort))


def run():
    build_model()
    count = build_report()
    print(f"Created native Power BI project: {OUTPUT / (NAME + '.pbip')}")
    print(f"4 tables, 3 one-direction relationships, 18 measures, 3 pages, {count} visuals.")
    print("Open in Desktop and Refresh to load the CSV data. Save As .pbix after checking visuals.")


if __name__ == "__main__":
    run()
