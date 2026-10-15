#!/usr/bin/env python3
"""Normalize raw events into the canonical schema using a mapping config.

This is the only place that knows raw field names. To use a different dataset (for example the
reference JSON), write a new mapping file; nothing downstream changes.

Input may be JSON Lines or a JSON array. Output is JSON Lines plus a report of problems:
unmatched sources, unmapped values, and schema violations. Unmapped values are kept and flagged,
never dropped silently.

Usage:
  python pipeline/normalize.py --mapping pipeline/mapping_synthetic.json \
      --input data/synthetic/events_raw.jsonl --out data/synthetic/canonical_events.jsonl
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from schema import validate_event

UTC = timezone.utc


def get_path(obj, path: str):
    for part in path.split("."):
        if not isinstance(obj, dict) or part not in obj:
            return None
        obj = obj[part]
    return obj


def iso_ms(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def t_epoch_ms(v):
    return iso_ms(datetime.fromtimestamp(v / 1000, tz=UTC))


def t_iso8601(v):
    dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    return iso_ms(dt if dt.tzinfo else dt.replace(tzinfo=UTC))


def t_pct_to_ratio(v):
    return round(v / 100, 4)


TRANSFORMS = {"epoch_ms": t_epoch_ms, "iso8601": t_iso8601, "pct_to_ratio": t_pct_to_ratio}


def read_records(path: Path):
    with open(path, encoding="utf-8") as f:
        head = f.read(1)
        f.seek(0)
        if head == "[":
            yield from json.load(f)
        else:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)


def detect_source(mapping: dict, rec: dict):
    for name, rule in mapping["detect"].items():
        if get_path(rec, rule["path"]) == rule["equals"]:
            return name
    return None


def unknown_props(mapping: dict, source: str, rec: dict):
    """Raw properties the mapping does not list (`known_props`, optional). Yields "prop:<raw path>"."""
    for prefix, keys in mapping.get("known_props", {}).get(source, {}).items():
        node = get_path(rec, prefix) if prefix else rec
        if isinstance(node, dict):
            for k in node:
                if k not in keys:
                    yield f"prop:{prefix + '.' if prefix else ''}{k}"


def normalize_record(mapping: dict, source: str, rec: dict, unmapped: dict):
    event, flagged = {}, []
    for field, spec in mapping["sources"][source].items():
        if isinstance(spec, str):
            value = get_path(rec, spec)
        elif "const" in spec:
            value = spec["const"]
        else:
            value = get_path(rec, spec["path"])
            if value is not None and "transform" in spec:
                try:
                    value = TRANSFORMS[spec["transform"]](value)
                except (ValueError, TypeError):
                    unmapped[f"{field}:bad_{spec['transform']}"][str(value)] += 1
                    value = None
            if value is not None and "map" in spec:
                mapped = mapping["maps"][spec["map"]].get(value)
                if mapped is None:
                    unmapped[field][str(value)] += 1
                    flagged.append(field)
                    value = "unknown" if field == "event_type" else None
                else:
                    value = mapped
        if value is not None:
            event[field] = value
    for prop in unknown_props(mapping, source, rec):
        unmapped[prop][str(get_path(rec, prop[5:]))] += 1
        flagged.append(prop)
    if flagged:
        event["unmapped"] = sorted(set(flagged))
    if mapping.get("keep_raw", True):
        event["raw"] = rec
    return event


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mapping", required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", help="defaults to <out>.report.json")
    args = ap.parse_args()

    mapping = json.loads(Path(args.mapping).read_text(encoding="utf-8"))
    unmapped: dict = defaultdict(Counter)
    totals, by_source, schema_problems = 0, Counter(), Counter()
    no_source = 0

    with open(args.out, "w", encoding="utf-8") as out:
        for rec in read_records(Path(args.input)):
            totals += 1
            source = detect_source(mapping, rec)
            if source is None:
                no_source += 1
                continue
            by_source[source] += 1
            event = normalize_record(mapping, source, rec, unmapped)
            for p in validate_event(event):
                schema_problems[p] += 1
            out.write(json.dumps(event, separators=(",", ":")) + "\n")

    report = {
        "dataset": mapping.get("dataset"),
        "records_read": totals,
        "records_written": sum(by_source.values()),
        "by_source": dict(by_source),
        "no_matching_source": no_source,
        "unmapped_values": {k: dict(v) for k, v in unmapped.items()},
        "schema_problems": dict(schema_problems),
    }
    report_path = Path(args.report or f"{args.out}.report.json")
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
