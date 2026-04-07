import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape


TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


def render_report_html(report_doc: dict) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("report_detail.html")
    return template.render(report=report_doc)


def save_report_html(report_doc: dict, output_path: str) -> str:
    html = render_report_html(report_doc)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as file:
        file.write(html)
    return output_path
