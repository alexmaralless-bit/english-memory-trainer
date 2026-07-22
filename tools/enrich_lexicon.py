"""Build-time corpus enrichment for the stable core lexicon (P.4b).

Derives ``frequency_score`` / ``frequency_band`` / ``source_refs`` for the units
that a pinned corpus actually covers, and refuses to invent them for the units
it does not. Raw datasets are never written into the repository: they are
fetched into a cache directory outside it and verified against the sha256
recorded in ``curriculum/lexicon/_provenance.yaml``.

    python tools/enrich_lexicon.py --cache <dir> --apply
    python tools/enrich_lexicon.py --cache <dir> --check

``--check`` re-derives every value and exits non-zero on drift, so the
committed lexicon stays reproducible from the pinned artifacts alone.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import re
import sys
import urllib.request
from collections.abc import Iterable
from decimal import ROUND_HALF_EVEN, Decimal
from math import log10
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
LEXICON_DIR = REPO_ROOT / "curriculum" / "lexicon"
PROVENANCE = LEXICON_DIR / "_provenance.yaml"

ITEM_RE = re.compile(r"^(?P<indent>\s*)- \{(?P<body>.*)\}\s*$")


class Artifact:
    """One pinned external file, verified by digest before use."""

    def __init__(self, spec: dict) -> None:
        self.id = spec["id"]
        self.url = spec["url"]
        self.sha256 = spec["sha256"]

    def fetch(self, cache: Path) -> bytes:
        target = cache / self.id.replace("/", "_").replace("@", "-")
        if target.exists():
            data = target.read_bytes()
        else:
            with urllib.request.urlopen(self.url, timeout=120) as response:
                data = response.read()
            cache.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        if digest != self.sha256:
            raise SystemExit(
                f"{self.id}: sha256 mismatch\n  pinned:   {self.sha256}\n  fetched:  {digest}\n"
                "The pinned artifact changed upstream. Do not enrich against an unverified source."
            )
        return data


def load_lemma_families(data: bytes) -> set[str]:
    """Read an NGSL/BSL lemma-family file into a flat set of every listed form.

    Membership must be tested across inflections: on headwords alone, `completed`
    and `meeting` would read as absent because the lists carry `complete` and `meet`.
    """
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        # NAWL 1.2's teaching CSV is Windows-1252, unlike the UTF-8 NGSL and
        # BSL artifacts. The digest is verified before decoding, so this is a
        # pinned format difference rather than a permissive input fallback.
        text = data.decode("cp1252")
    rows = csv.reader(io.StringIO(text))
    forms: set[str] = set()
    for row in rows:
        if not row or row[0].lstrip().startswith("#"):
            continue
        forms.update(cell.strip().lower() for cell in row if cell.strip())
    return forms


def band_for(zipf: float, thresholds: list[dict]) -> str:
    for entry in thresholds:
        floor = entry["min_zipf"]
        if floor is None or zipf >= floor:
            return entry["band"]
    return thresholds[-1]["band"]


def round_half_even(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


def parse_flow_item(body: str) -> dict[str, str]:
    """Split a flow-style mapping into key -> raw value, respecting nesting."""
    fields: dict[str, str] = {}
    depth = 0
    in_quote = False
    token = ""
    parts: list[str] = []
    for char in body:
        if char == '"':
            in_quote = not in_quote
        if not in_quote:
            if char in "[{":
                depth += 1
            elif char in "]}":
                depth -= 1
            elif char == "," and depth == 0:
                parts.append(token)
                token = ""
                continue
        token += char
    parts.append(token)
    for part in parts:
        key, _, value = part.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def surface_forms(raw_forms: str) -> list[str]:
    """Flatten a lexeme ``forms`` mapping, where a slot may hold a list."""
    parsed = yaml.safe_load(raw_forms)
    out: list[str] = []
    for value in parsed.values():
        out.extend(value if isinstance(value, list) else [value])
    return [str(v).lower() for v in out]


def enrich_line(
    line: str,
    *,
    zipf_of,
    freq_of,
    thresholds: list[dict],
    ngsl: set[str],
    bsl: set[str],
    nawl: set[str],
    covered_types: set[str],
    stats: dict,
) -> str:
    match = ITEM_RE.match(line)
    if not match:
        return line
    fields = parse_flow_item(match.group("body"))
    item_type = fields.get("type", "")
    title = fields.get("title", "").strip('"').strip()

    # Strip any previous enrichment so the pass is idempotent.
    body = match.group("body")
    body = re.sub(r", frequency_score: [^,}]+", "", body)
    body = re.sub(r", frequency_band: [^,}]+", "", body)
    body = re.sub(r", source_refs: \[[^\]]*\]", "", body)
    body = re.sub(
        r"(transformations: \[)([^\]]*)\]",
        lambda m: (
            m.group(1)
            + ", ".join(
                t
                for t in (x.strip() for x in m.group(2).split(","))
                if t not in {"corpus-enriched", "lemma-form-sum"}
            )
            + "]"
        ),
        body,
    )

    lemma = title.lower()
    covered = item_type in covered_types and " " not in lemma and ";" not in lemma

    if not covered:
        stats.setdefault("uncovered", []).append(fields.get("id", "?"))
        return f"{match.group('indent')}- {{{body}}}"

    extra_transformations = ["corpus-enriched"]
    if item_type == "lexeme" and "forms" in fields:
        total = sum(freq_of(form) for form in set(surface_forms(fields["forms"])))
        zipf = log10(total * 1e9) if total > 0 else 0.0
        extra_transformations.append("lemma-form-sum")
    else:
        zipf = zipf_of(lemma)

    if zipf <= 0:
        stats.setdefault("absent_from_corpus", []).append(fields.get("id", "?"))
        return f"{match.group('indent')}- {{{body}}}"

    score = round_half_even(zipf)
    band = band_for(float(score), thresholds)

    refs = ["wordfreq@3.1.1"]
    if lemma in ngsl:
        refs.append("ngsl@1.2")
    if lemma in bsl:
        refs.append("bsl@1.2")
    if lemma in nawl:
        refs.append("nawl@1.2")

    stats.setdefault("enriched", []).append((fields.get("id", "?"), float(score), band, refs))

    body = re.sub(
        r"(cefr: [^,}]+)",
        lambda m: f"{m.group(1)}, frequency_score: {score}, frequency_band: {band}",
        body,
        count=1,
    )
    body = re.sub(
        r"(transformations: \[)([^\]]*)\]",
        lambda m: (
            f"source_refs: [{', '.join(refs)}], {m.group(1)}{m.group(2)}, {', '.join(extra_transformations)}]"
        ),
        body,
        count=1,
    )
    return f"{match.group('indent')}- {{{body}}}"


def lexicon_files() -> Iterable[Path]:
    return sorted(p for p in LEXICON_DIR.glob("*.yaml") if not p.name.startswith("_"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", required=True, type=Path, help="download cache, must be outside the repo")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true", help="rewrite the lexicon in place")
    mode.add_argument(
        "--check", action="store_true", help="fail if committed values differ from a fresh derivation"
    )
    args = parser.parse_args()

    if REPO_ROOT in args.cache.resolve().parents or args.cache.resolve() == REPO_ROOT:
        raise SystemExit("--cache must live outside the repository: raw datasets are not committed.")

    try:
        from wordfreq import word_frequency, zipf_frequency
    except ImportError as err:
        raise SystemExit(
            "wordfreq is not installed. Install the pinned extra: pip install -e '.[corpus]'"
        ) from err

    manifest = yaml.safe_load(PROVENANCE.read_text(encoding="utf-8"))
    artifacts = {spec["id"]: Artifact(spec) for spec in manifest["source_artifacts"]}
    thresholds = manifest["frequency_thresholds"]["bands"]
    covered_types = set(manifest["coverage_policy"]["covered_types"])

    ngsl = load_lemma_families(artifacts["ngsl@1.2"].fetch(args.cache))
    bsl = load_lemma_families(artifacts["bsl@1.2"].fetch(args.cache))
    nawl = load_lemma_families(artifacts["nawl@1.2"].fetch(args.cache))

    stats: dict = {}
    drift: list[str] = []
    for path in lexicon_files():
        original = path.read_text(encoding="utf-8")
        rewritten = "\n".join(
            enrich_line(
                line,
                zipf_of=lambda w: zipf_frequency(w, "en"),
                freq_of=lambda w: word_frequency(w, "en"),
                thresholds=thresholds,
                ngsl=ngsl,
                bsl=bsl,
                nawl=nawl,
                covered_types=covered_types,
                stats=stats,
            )
            for line in original.split("\n")
        )
        if args.apply:
            path.write_text(rewritten, encoding="utf-8")
        elif rewritten != original:
            drift.append(path.name)

    enriched = stats.get("enriched", [])
    print(f"enriched:            {len(enriched)}")
    print(f"uncovered by policy: {len(stats.get('uncovered', []))}")
    print(f"absent from corpus:  {len(stats.get('absent_from_corpus', []))}")
    for item_id in stats.get("absent_from_corpus", []):
        print(f"  - {item_id}")

    if args.check and drift:
        print("\nDRIFT: committed values do not match a fresh derivation in " + ", ".join(drift))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
