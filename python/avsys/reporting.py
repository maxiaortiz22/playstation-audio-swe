"""Self-contained, autoescaped HTML diagnostics for the DEMO-3 workflow."""

from __future__ import annotations

from typing import Any

from jinja2 import Environment, StrictUndefined, select_autoescape


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>avsys report — {{ result.test_id }}</title>
  <style>
    :root { color-scheme: light dark; font-family: system-ui, sans-serif; }
    body { max-width: 1080px; margin: 0 auto; padding: 2rem; line-height: 1.45; }
    h1, h2 { line-height: 1.15; }
    .status { display: inline-block; border: 2px solid currentColor; border-radius: .35rem; padding: .25rem .55rem; font-weight: 750; text-transform: uppercase; }
    .pass { color: #19733c; } .fail, .invalid, .internal_error { color: #b42318; }
    .warning { color: #8a4b08; }
    .card { border: 1px solid #8888; border-radius: .5rem; padding: 1rem; margin: 1rem 0; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border-bottom: 1px solid #8886; padding: .5rem; text-align: left; vertical-align: top; }
    code, pre { font-family: ui-monospace, monospace; }
    pre { white-space: pre-wrap; overflow-wrap: anywhere; background: #8881; padding: .75rem; border-radius: .35rem; }
    .raw { border-left: .35rem solid #2767b0; }
    .compensated { border-left: .35rem solid #7a4ba0; }
    .label { font-weight: 700; }
  </style>
</head>
<body>
  <header>
    <h1>Audio validation result</h1>
    <p><span class="status {{ result.run_status }}">{{ result.run_status }}</span></p>
    <p><span class="label">Test:</span> {{ result.test_id }}<br>
       <span class="label">Validation:</span> {{ result.validation_status }}<br>
       <span class="label">Baseline:</span> deterministic generated stimulus<br>
       <span class="label">Candidate:</span> native_passthrough{% if result.faults %} + {{ result.faults[0].type }}{% endif %}</p>
  </header>

  <section class="card">
    <h2>Reproduce</h2>
    <pre><code>{{ result.reproduction.display_command }}</code></pre>
  </section>

  <section class="card">
    <h2>Policy findings</h2>
    <table>
      <thead><tr><th>Status</th><th>Severity</th><th>Policy</th><th>Actual</th><th>Expected</th><th>Requirements</th></tr></thead>
      <tbody>
      {% for item in result.policy_evaluations %}
        <tr>
          <td><span class="status {{ item.status }}">{{ item.status }}</span></td>
          <td>{{ item.severity }}</td>
          <td>{{ item.policy_id }}<br><small>{{ item.rationale }}</small></td>
          <td>{{ item.actual_value }} {{ item.unit }}</td>
          <td>{{ item.expected_condition.operator }} {{ item.expected_condition.threshold }} {{ item.unit }}</td>
          <td>{{ item.requirement_ids | join(', ') }}</td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
  </section>

  <section class="card raw">
    <h2>Raw observations (before compensation)</h2>
    <p><span class="label">Latency:</span>
      {% if result.analysis.alignment.lag_frames is not none %}
        {{ result.analysis.alignment.lag_frames }} frames / {{ result.analysis.alignment.latency_ms }} ms
      {% else %}
        unavailable ({{ result.analysis.alignment.status }}: {{ result.analysis.alignment.reason }})
      {% endif %}
    </p>
    <p><span class="label">Correlation:</span> {{ result.analysis.alignment.signed_primary_correlation }};
       <span class="label">search:</span> [{{ result.analysis.alignment.search_min_lag_frames }}, {{ result.analysis.alignment.search_max_lag_frames }}] frames</p>
  </section>

  <section class="card compensated">
    <h2>Compensated/aligned observations</h2>
    <p><span class="label">Measurement view:</span> {{ result.analysis.measurement_view }}</p>
    {% if result.compensations %}
      <p><span class="label">Applied compensation:</span> {{ result.compensations | tojson }}</p>
    {% else %}
      <p>No compensation was applied.</p>
    {% endif %}
    <p><span class="label">Residual:</span> {{ result.analysis.residual | tojson }}</p>
    <p><span class="label">Gain delta:</span> {{ result.analysis.gain | tojson }}</p>
    <p><span class="label">Polarity:</span> {{ result.analysis.polarity | tojson }}</p>
    <p><span class="label">Observed-to-expected channel mapping:</span> {{ result.analysis.channel_mapping.observed_to_expected_indices }};
       margin {{ result.analysis.channel_mapping.mapping_margin }} (minimum {{ result.analysis.channel_mapping.minimum_mapping_margin }})</p>
  </section>

  <section class="card">
    <h2>Localized events</h2>
    {% if result.events %}
    <table>
      <thead><tr><th>Type</th><th>Channels</th><th>Frames [start, end)</th><th>Seconds [start, end)</th><th>Classification</th></tr></thead>
      <tbody>{% for event in result.events %}<tr>
        <td>{{ event.type }}</td><td>{{ event.channels | join(', ') }}</td>
        <td>[{{ event.start_frame }}, {{ event.end_frame }})</td>
        <td>[{{ event.start_seconds }}, {{ event.end_seconds }})</td>
        <td>{{ event.classification }}</td>
      </tr>{% endfor %}</tbody>
    </table>
    {% else %}<p>No dropout events.</p>{% endif %}
  </section>

  <section class="card">
    <h2>Provenance</h2>
    <p>The timestamp below is a logical deterministic fixture timestamp, not wall-clock timing.</p>
    <pre>{{ result.provenance | tojson(indent=2) }}</pre>
    <p><span class="label">Manifest SHA-256:</span> <code>{{ result.manifest_digest }}</code><br>
       <span class="label">Source revision:</span> <code>{{ result.source_revision }}</code><br>
       <span class="label">Dirty worktree:</span> {{ result.dirty_state }}</p>
  </section>
</body>
</html>
"""


def render_report(result: dict[str, Any]) -> bytes:
    """Render one deterministic UTF-8 HTML document without external assets."""

    environment = Environment(
        autoescape=select_autoescape(default_for_string=True, default=True),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    rendered = environment.from_string(_TEMPLATE).render(result=result)
    return (rendered.rstrip() + "\n").encode("utf-8")

__all__ = ["render_report"]
