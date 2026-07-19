"""Standalone multi-agent HTML comparison report."""

from traderharness.metrics.comparison_report import render_comparison_html


def test_report_renders_ranked_agents_and_behavior():
    html = render_comparison_html(
        [
            {
                "Agent": "value-agent",
                "Rank": 1,
                "Total Return%": 12.3,
                "Sharpe": 1.2,
                "Alpha%": 3.1,
            },
            {
                "Agent": "momentum-agent",
                "Rank": 2,
                "Total Return%": 8.0,
                "Sharpe": 0.8,
                "Alpha%": -1.2,
            },
        ],
        {
            "value-agent": {"avg_tool_calls_per_day": 6.5, "empty_days_pct": 10.0},
        },
        title="Agent Arena",
    )

    assert "Agent Arena" in html
    assert "value-agent" in html
    assert "momentum-agent" in html
    assert "Behavior Diagnostics" in html
    assert "<!doctype html>" in html.lower()
