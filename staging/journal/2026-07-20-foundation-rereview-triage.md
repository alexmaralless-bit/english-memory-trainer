# 2026-07-20 — триаж foundation-rereview (0.2 kernel)

Провенанс: `staging/reviews/2026-07-20-foundation-rereview-codex.md` (checkout d7b974a). Вердикт **PASS-with-findings**: BLOCKER A-1/E-1 подтверждён закрытым, новых BLOCKER нет. 4 MAJOR + 2 MINOR — все триаж-формулировки, продуктовых форков нет. Разделы D/G/J — ЧИСТО.

## Диспозиция (всё fix-now в тексте)

| ID | Sev | Диспозиция |
|---|---|---|
| E-1 | MAJOR | fixed: JSONL post-commit lag ≠ integrity error; `database check` сверяет до acknowledged export offset/high-water mark; ошибка только при divergence после catch-up → foundation §2.1 |
| A-1 | MAJOR | fixed: `prior_steady_state` — явное поле проекции (не «производно»); `self_reported_level` влияет на provisional working estimate/briefing/рекомендации, не только briefing → §2.2 |
| C-1 | MAJOR | fixed: safety-correction несёт `original_pinned_versions`+`active_safety_version` — инвариант «с обеими версиями» восстановлен → §3.6; OPEN-11 |
| B-1 | MAJOR | fixed: replay-тест разделён на (1) order-independence чтения при фиксированном `sequence` и (2) детерминированный записанный append-order → §5 |
| H-1 | MINOR | fixed: «фиксированы в kernel» → «должны быть зафиксированы в 1.2 по OPEN-11/20» → §3.4 |
| I-1 | MINOR | fixed: `sequence` добавлен в glossary-определение конверта + история |

## Регрессия

Раздел K ревью отметил A-1/C-1/E-1 как межспековые регрессии моего первого foundation-триажа — все сняты этим проходом. Прочее (six specs, owner-матрица, OPEN-19/20/21) — подтверждено чистым.

## Итог

0.2 подтверждён как **done-with-open** без остаточных дефектов уровня спеки; все механизмы корректно вынесены в OPEN-9/10/11/19/20/21 с владельцем 0.2 kernel / 1.2-1.3. Новых OPEN не потребовалось. Три прогона ревью по kernel-контракту сошлись. Next → 0.4.
