# 2026-07-19 — триаж повторного red-team ревью

Провенанс триажа rereview (`staging/reviews/2026-07-19-concept-rereview-codex.md`, checkout 9201cfe): 1 BLOCKER, 21 MAJOR, 1 MINOR, 2 QUESTION. Первый прогон (66 находок) подтверждён корректно закрытым. План одобрен пользователем; 2 продуктовых развилки решены.

## Продуктовые решения (2 развилки)

1. **Safety-overlay (G-R1, BLOCKER):** safety (production-eligibility) **не пинится** — всегда проверяется по active policy при доставке; прошлое evaluation/replay детерминировано по pinned scoring. Ставший `avoid`/`obsolete`/вне-контекста item отменяется/заменяется append-only event с обеими версиями. Разрешает единственный BLOCKER.
2. **Trust model (C-R3):** MVP — агент **trusted reporter** raw_answer; допущение зафиксировано, границы через Tutor Compliance; untrusted-захват на adapter boundary — post-mvp.

Дефолт: **A-R3** — self_reported_level замещается **per-skill** после первого evidence навыка.

## Диспозиция 25 находок

| ID | Sev | Диспозиция |
|---|---|---|
| G-R1 | BLOCKER | resolved: safety-overlay [PD] → curriculum §5, lexical §3b, session; механизм OPEN-14 |
| A-R1 | MAJOR | fixed: AttemptAssessment vs terminal ReviewOutcome → glossary, session, learning §3; OPEN-10 |
| A-R2 | MAJOR | fixed: FINISHED требует пустой pending-set, ABANDONED преобразует → session |
| A-R3 | QUESTION | resolved: self-report per-skill [PD] → learning §5, placement, OPEN |
| C-R1 | MAJOR | fixed: observation ссылается на criterion+span → learning §3; расширен OPEN-7 |
| C-R2 | MAJOR | fixed: объяснение агента ≠ evidence, вход = только enrollment → lexical §3, glossary |
| C-R3 | QUESTION | resolved: trusted-reporter MVP [PD] → learning §3, OPEN |
| D-R1 | MAJOR | fixed: три оси (enrollment/knowledge/review_status), REVIEW_DUE устранён → glossary, learning §4 |
| D-R2 | MAJOR | fixed: AT_RISK только подтверждённый/overdue, синхронизирован → glossary, learning §4; порог OPEN-18 |
| D-R3 | MAJOR | fixed: placement `STARTED|IN_PROGRESS → ABANDONED` + команда + события → placement, OPEN-17 |
| E-R1 | MAJOR | fixed: Obsidian post-commit через outbox, не в ACID → session |
| E-R2 | MAJOR | fixed: candidate `validate`/`activate` API → curriculum §4/§6 |
| E-R3 | MAJOR | fixed: generic LexicalMasteryProfile → lexical §1, glossary; OPEN-13 |
| E-R4 | MAJOR | invariant→OPEN-8: ordinal/sublevel представление уровня → learning §5 |
| E-R5 | MAJOR | fixed: frequency_band только numeric+нейтральные bands → lexical §1, glossary |
| F-R1 | MINOR | fixed: confidence machine-enum + self_reported_level entry → glossary |
| G-R2 | MAJOR | fixed: причины отклонения finish (бизнес vs lifecycle/concurrency) → session; OPEN-11 |
| G-R3 | MAJOR | invariant→OPEN-12: practice_day day-attribution → learning §8 |
| H-R1 | MAJOR | fixed: production_eligible + obsolete + requires_usage_policy + cultural_context → lexical §3b, curriculum §5 |
| I-R1 | MAJOR | fixed: license-таблица разделена CEFR-J/Octanove + полные CC BY-SA obligations → curriculum §3; OPEN-15 блокирует publish |
| I-R2 | MAJOR | fixed: living layer без сторонних excerpts (canonical MUST NOT) → lexical, curriculum §5 |
| I-R3 | MAJOR | fixed: transformations в схеме + валидируется → curriculum §3/§5, lexical §1 |
| J-R1 | MAJOR | fixed: owner-матрица OPEN→контракт в OPEN.md; uniqueness outcome → 0.5, не kernel → continuation |
| J-R2 | MAJOR | fixed: `done-with-open` определён; П.3 закрывает OPEN-14/16, П.4 — OPEN-15 → roadmap |
| J-R3 | MAJOR | fixed: re-entry пороги → OPEN-18 (0.4 scheduler), не суженный OPEN-1 → session, learning §7 |

## Новое в реестре

- **OPEN-18** — scheduler-policy (re-entry trigger, overdue→AT_RISK порог) → 0.4 scheduler.
- **Owner-матрица** компонент→контракт в OPEN.md (kernel = envelopes/CAS/UoW; 0.4 = admissibility/transitions/lexical scoring; 0.5 = Session/Attempt lifecycle + uniqueness; assessments = placement; П.3 = bank/policy/safety-overlay).
- OPEN-7/8/9/10/12/13/14/15/17 расширены находками rereview.

## Итог

BLOCKER G-R1 снят precedence-решением (safety не пинится). FAIL повторно снят со всех шести спек: каждая находка либо исправлена текстом, либо закрыта несущим инвариантом + OPEN с явным владельцем. Практический gate: П.1 идёт; 0.4 и 0.2 можно проектировать параллельно; pinning contract в 0.2/0.3 теперь имеет разрешённый precedence (safety-overlay), можно закрывать.
