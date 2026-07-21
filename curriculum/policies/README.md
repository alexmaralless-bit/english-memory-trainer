# Curriculum policies

This directory stores curriculum-authored policy payloads before they are
registered in the kernel policy registry.

`generation-v1.yaml` is the proposed payload for `generation@1`: how lesson
exercises may be generated, rendered, admitted to the exercise bank, reused, and
revalidated against active lexical safety. It is data, not executable code.

Policy files here must remain deterministic and canon-compatible:

- no floats in policy values;
- no third-party excerpts or borrowed exercise text;
- active safety is checked at delivery and bank reuse;
- generated content becomes auditable only after it is persisted as an event.
