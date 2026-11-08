# cl-bench-revisited — memory modes experiment

Ветка `memory-modes-2026-11`. Парное сравнение четырёх способов переноса опыта между вопросами
в последовательности из 26 SQL‑задач к одной SQLite‑базе (синтетическая платёжная платформа **PayOps**):

| режим | что переносится |
|---|---|
| `stateless` | ничего — новая беседа на каждый вопрос |
| `icl` | одна беседа на всю последовательность; история, результаты инструментов, фидбэк и **нативный reasoning** (Anthropic thinking blocks, Codex encrypted reasoning items, OpenRouter `reasoning_details`); prompt caching |
| `memory` | новая беседа на вопрос + инструмент `bash` в персистентной директории; промпт нейтральный («сохраняется только рабочая директория; как пользоваться — решать вам») |
| `memory_guided` | то же + одна фраза‑подсказка («в начале посмотрите, что оставили прошлые сессии, в конце — оставьте заметки») |

После 18‑го вопроса база **молча** подменяется на мигрированную схему (переименования таблиц/колонок, разбиение журнала, новая версия словаря кодов).
Модели: `gpt-6-luna` (Codex endpoint), `claude-haiku-5-5` (Anthropic), `z-ai/glm-5.3-flash` (OpenRouter/Relace).

**Итоговый отчёт: [`reports/REPORT.md`](reports/REPORT.md)** (на русском). Спецификация — `SPEC.md`, порядок работ — `RUNBOOK.md`,
описание датасета и посаженных историй — `data/STORIES.md` (моделям не показывается).

Коротко о результатах: Haiku и GLM решают 25–26/26 во всех режимах (датасет для них у потолка — различия только в затратах);
у Luna ICL даёт 26/26 и 25/26 против 19–22/26 в stateless, причём в memory‑режимах Luna ни разу не вызвала `bash`.
Без подсказки ни одна модель не писала заметки; с подсказкой Haiku и GLM вели файл заметок. ICL у Haiku дешевле stateless
(кэш), у GLM — в 4.4 раза дороже (кэшированные токены почти не дешевле). Подробности, кейсы с цитатами SQL и заметок,
структура затрат, утечка песочницы и ограничения — в отчёте.

## Воспроизведение

```bash
pip install -r requirements.txt            # anthropic, requests (Python 3.12)
export ANTHROPIC_API_KEY=... OPENROUTER_API_KEY=...
# Codex: secrets/openai-tokens.json с refresh_token (см. SPEC.md, раздел Models)

# 1. датасет (детерминированный, seed 20261108): data/payops.db, data/payops_v2.db,
#    data/questions.json, data/questions_v2.json, data/STORIES.md, data/schema_v*.sql
python -m clrev.dataset.build --out data/

# 2. прогон одной ячейки (модель × режим); memory_guided = --mode memory --memory-prompt guided
python -m clrev.runner run --model haiku --mode icl \
  --questions data/questions_v2.json --db data/payops.db --db-v2 data/payops_v2.db --drift-after 18 \
  --out runs/haiku_icl_r1
./run_matrix.sh haiku stateless icl memory memory_guided      # все режимы подряд

# 3. реплей одного вопроса со снапшота (ICL: состояние беседы; memory: директория) или с нуля
python -m clrev.runner replay --run runs/luna_icl_r1 --question q26 --from-snapshot --repeats 3

# 4. анализ и просмотр
python -m clrev.analyze --runs runs/haiku_* --out reports/analysis_haiku.md
python -m clrev.quick_table haiku
python -m clrev.inspect_ep runs/luna_icl_r1/episodes/q15.json.gz [--sql-only|--full]
pytest -q                                                    # оффлайн‑тесты раннера (fake provider)
```

Инструмент `bash` запускается как непривилегированный пользователь `memuser` (`runuser`), требует root в контейнере;
`/tmp` закрывается для него (`chmod 1770`), `TMPDIR` приватный. Без root команда выполняется от текущего пользователя (не песочница).

## Структура

```
SPEC.md RUNBOOK.md            спецификация и порядок работ
clrev/runner.py               режимы, промпты, инструменты run_sql/submit_answer/bash, грейдинг, снапшоты, replay, цены
clrev/tools.py                read-only SQLite (authorizer, cap строк/символов, таймаут) и bash-песочница
clrev/providers/              anthropic_p.py, openai_codex.py, openrouter_p.py (+ base.py — общий интерфейс)
clrev/dataset/                генератор PayOps, миграция v2, вопросы (questions.py / questions_v2.py), валидация, STORIES.md
clrev/analyze.py              парные таблицы по прогонам → reports/analysis_*.md|json
clrev/quick_table.py          сводка «вопрос × режим» по summary.json
clrev/inspect_ep.py           компактный дамп траектории эпизода
data/                         questions*.json, STORIES.md, schema_v1/v2.sql (БД — gitignored, пересобираются)
runs/<run_id>/                config.json, summary.json, episodes/qNN.json.gz, snapshots/, replays/, replay_memory/ (raw/ — gitignored)
runs/_calib_*/                калибровочные прогоны (explicit‑каталог; v2 с комментариями в DDL)
reports/REPORT.md             итоговый отчёт; reports/analysis_{haiku,glm,luna}.md — таблицы по моделям
/workspace/memdirs/<run_id>/  директории памяти (notes.txt у haiku_memory_guided_r1, notes.md у glm_memory_guided_r1)
tests/                        test_runner_fake.py (оффлайн), test_providers_live.py (живые API)
```
