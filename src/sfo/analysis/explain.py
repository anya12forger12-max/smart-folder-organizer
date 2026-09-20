"""Human-friendly explanations for analysis decisions.

Normal users must never see raw scores. Every explanation answers:
what was found, and why it matters — in plain language.
"""

from __future__ import annotations

from sfo.domain.analysis import Classification, ClassificationKind

_TEMPLATES = {
    (ClassificationKind.PROJECT, "VERY_HIGH"): "Almost certainly part of the {name} project: {evidence}",
    (ClassificationKind.PROJECT, "HIGH"): "Likely part of the {name} project because {evidence}",
    (ClassificationKind.PROJECT, "MEDIUM"): "Possibly part of the {name} project based on {evidence}",
    (ClassificationKind.TOPIC, "MEDIUM"): "Possibly related to {name} based on {evidence}",
    (ClassificationKind.TOPIC, "HIGH"): "Related to {name} based on {evidence}",
}


class ExplanationFormatter:
    def describe(self, classification: Classification) -> str:
        if classification.kind is ClassificationKind.UNCERTAIN or classification.name is None:
            return "Not enough evidence to classify safely."
        key = (classification.kind, classification.confidence.value)
        template = _TEMPLATES.get(
            key,
            "Related to {name} ({confidence} confidence)".format(
                name=classification.name, confidence=classification.confidence.value.lower()
            ),
        )
        summary = "; ".join(e.description for e in classification.evidence[:2]) or "related files nearby"
        return template.format(name=classification.name, evidence=summary)

    def group_summary(self, kind_label: str, name: str, count: int, destination=None) -> str:
        line = f"{kind_label}: {name} — {count} file{'s' if count != 1 else ''}"
        if destination is not None:
            line += f" → {destination}"
        return line
