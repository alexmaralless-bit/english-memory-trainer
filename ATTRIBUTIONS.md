# Attributions

Внешние источники, из которых выведены данные в этом репозитории.

**Текущий статус — репозиторий публичный (2026-09-24).** Код и авторский контент распространяются под MIT (`LICENSE`). Производные данные в `curriculum/lexicon/` (`frequency_score`/`frequency_band` из wordfreq; `source_refs` на членство в NGSL/BSL), выведенные из источников CC BY-SA 4.0, распространяются под CC BY-SA 4.0 — обязательства attribution, license/notices, indication of changes и ShareAlike на Adapted Material для этих полей действуют начиная с публикации ([[wiki/modules/curriculum]] §3.1).

Сырые датасеты в репозиторий не коммитятся. Машинная версия записей с точными версиями, sha256 и notices — `curriculum/lexicon/_provenance.yaml`.

## wordfreq 3.1.1

- Название: wordfreq.
- Автор(ы): Robyn Speer et al.
- Источник: https://github.com/rspeer/wordfreq
- Роль: численная корпусная частота (агрегированный Zipf score) для `frequency_score`/`frequency_band`.
- Лицензия: код Apache-2.0; входящие частотные данные **CC BY-SA 4.0** — https://creativecommons.org/licenses/by-sa/4.0/
- Изменения (indication of changes): значения не копировались таблицей; для каждой отобранной единицы вычислено одно число (Zipf, округление до 2 знаков ROUND_HALF_EVEN), для лексем — сумма вероятностей поверхностных форм. Присвоение band выполнено по нашим собственным versioned thresholds.
- Notices: snapshot данных ~2021 — не подтверждает актуальность неформальной лексики; частоты агрегированы по доменам (включая Reddit/Twitter), per-domain разбивка не запрашивалась; пакет архивирован upstream, 3.1.1 — последний релиз.
- ShareAlike: `frequency_score`/`frequency_band` — производные (Adapted Material) от CC BY-SA 4.0 частотных данных wordfreq и распространяются под теми же условиями CC BY-SA 4.0.

## New General Service List (NGSL) 1.2

- Название: New General Service List (NGSL) 1.2.
- Автор(ы): Browne, C., Culligan, B., Phillips, J.
- Источник: https://www.newgeneralservicelist.com
- Роль: проверка принадлежности к ядру общего английского (валидация `curriculum_priority_band`).
- Лицензия: **CC BY-SA 4.0** — https://creativecommons.org/licenses/by-sa/4.0/
- Изменения (indication of changes): таблица не воспроизводится. Используется только факт членства единицы в lemma-family; результат записан как `source_refs: [ngsl@1.2]`.
- ShareAlike: значение `source_refs: [ngsl@1.2]` — производное (Adapted Material) от NGSL 1.2 и распространяется под теми же условиями CC BY-SA 4.0.

## Business Service List (BSL) 1.2

- Название: Business Service List (BSL) 1.2.
- Автор(ы): Browne, C., Culligan, B. (без Phillips, в отличие от NGSL).
- Источник: https://www.newgeneralservicelist.com
- Роль: проверка принадлежности к ядру делового английского.
- Лицензия: **CC BY-SA 4.0** — https://creativecommons.org/licenses/by-sa/4.0/
- Изменения (indication of changes): таблица не воспроизводится; используется только факт членства, записанный как `source_refs: [bsl@1.2]`.
- ShareAlike: значение `source_refs: [bsl@1.2]` — производное (Adapted Material) от BSL 1.2 и распространяется под теми же условиями CC BY-SA 4.0.

## Не импортировалось

- **CEFR-SP** — лицензия не указана.
- **OpenVLT** — лицензия данных не заявлена; использовался только как архитектурный reference.
- **CEFR-J Vocabulary Profile** и **Octanove C1/C2** — в контракте разрешены, но в П.4b не импортировались: CEFR-разметка текущего лексикона авторская. При импорте добавить сюда записи с цитированием и disclaimer (CEFR-J) и полным набором CC BY-SA notices (Octanove).

## Публикация

Репозиторий опубликован 2026-09-24. Ревизия перед публикацией ([[wiki/modules/curriculum]] §3.1) проведена: добавлен `LICENSE` (MIT на код и авторский контент, с explicit carve-out под CC BY-SA 4.0 на выведенные лексиконные поля); per-source записи выше дополнены полным набором элементов CC BY-SA notice (название, авторы, ссылка на источник, ссылка на лицензию, indication of changes, ShareAlike statement); `pyproject.toml` и README.md синхронизированы. Автор — не юрист; позиция задокументирована как продуктовое решение.
