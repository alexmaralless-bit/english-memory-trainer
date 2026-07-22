# Curriculum policies

This directory stores curriculum-authored policy payloads before they are
registered in the kernel policy registry.

Each YAML document is the immutable payload of one registry version. Alongside
generation/rubric/control/scoring/scheduler, the catalogue includes lifecycle
decisions (`lessons@1`, `assessments@1`), multi-target evidence allocation
(`evidence@1`), Tutor Compliance matching (`obligations@1`) and the metadata-only
calibration catalogue (`tunables@1`). Active values remain in their owner policy;
the tunables catalogue never duplicates them.

Policy files here must remain deterministic and canon-compatible:

- no floats in policy values;
- no third-party excerpts or borrowed exercise text;
- active safety is checked at delivery and bank reuse;
- generated content becomes auditable only after it is persisted as an event.
