"""Small Rich-based presentation helpers for the interactive client."""

from __future__ import annotations

from typing import Any, Iterable

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


def console(*, no_color: bool = False) -> Console:
    return Console(no_color=no_color, highlight=False)


def header(output: Console) -> None:
    output.print(
        Panel.fit(
            "[bold cyan]SysGap[/bold cyan]\n"
            "[dim]A calm, evidence-based hardware check[/dim]",
            border_style="cyan",
        )
    )


def phase(output: Console, number: int, total: int, title: str, detail: str = "") -> None:
    text = f"[bold]{number}/{total}[/bold]  {title}"
    if detail:
        text += f"\n[dim]{detail}[/dim]"
    output.print(Panel(text, border_style="blue"))


def result_table(output: Console, report: dict[str, Any]) -> None:
    assessment = report["assessment"]
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold")
    table.add_column()
    table.add_row("Status", str(assessment.get("overall_status", "unknown")))
    table.add_row("Purpose", str(report["questionnaire"].get("purpose_label", "Unknown")))
    table.add_row("Report", str(report.get("report_id", "unknown")))
    output.print(table)


def checklist(output: Console, items: Iterable[tuple[str, str]]) -> None:
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="green")
    table.add_column()
    for label, value in items:
        table.add_row("✓", f"{label}: {value}")
    output.print(table)


def concise_report(report: dict[str, Any]) -> str:
    """Return a short readable report; JSON retains the full detail."""
    assessment = report["assessment"]
    questionnaire = report["questionnaire"]
    lines = [
        "SYSGAP ASSESSMENT",
        "=================",
        f"Status: {assessment.get('overall_status', 'unknown')}",
        f"Purpose: {questionnaire.get('purpose_label', 'Unknown')}",
        f"Report ID: {report.get('report_id', 'unknown')}",
        "",
        assessment.get("summary", "No summary available."),
        "",
        "KEY FINDINGS",
        "------------",
    ]
    findings = assessment.get("findings") or []
    if findings:
        lines.extend(
            f"- {item.get('title', 'Finding')}: {item.get('status', 'unknown')}"
            for item in findings
        )
    else:
        lines.append("- No findings were produced.")
    selection = report.get("recommendation_selection") or {}
    if selection:
        lines.extend(["", "RECOMMENDATIONS", "---------------"])
        selected = selection.get("selected_components") or []
        lines.extend(
            f"- {item['component'].upper()}: {item['candidate_count']} option(s)"
            for item in selected
        )
        if not selected:
            lines.append("- No component shortlist selected.")
    lines.extend([
        "",
        "DETAILS",
        "-------",
        "The complete technical inventory and assessment are in the JSON report.",
        "No benchmark or stress test was run.",
    ])
    return "\n".join(lines) + "\n"
