# Аудит затрат SQL-memory study

Срез: **2026-11-08T16:03:42.196845+00:00**. Аудит полностью локальный: **API-вызовов нет**.

## Краткие численные результаты

- **GLM, основные пять задач:** stateless $0.011418, ICL $0.033824, managed $0.023730. На T1–T3: $0.007067 / $0.024206 / $0.015853. Это observed cost, не стоимость достижения одинаковой точности.
- **Haiku:** ICL $0.038271, managed $0.049706. Исходный stateless с неуспешным T1 $0.030448; продолжение T2/T3 $0.019095. Их бухгалтерская сумма $0.049543 не превращает T1 в успешное решение; диагностический T1 оплачивается отдельно.
- **Первый T1 input, Haiku:** ICL 30,101 против stateless 2,296; cached соответственно 23,888 и 0. Это полный input, не выделенная цена inherited history.
- **Первый T1 input, GLM:** ICL 14,154 против stateless 1,407; cached соответственно 9,216 и 0. Это полный input, не выделенная цена inherited history.
- **Первый T1 input, Codex:** ICL 10,209 против stateless 1,379; cached соответственно 0 и 0. Это полный input, не выделенная цена inherited history.
- **Структура известных Haiku USD:** output 63.0%, cache write 24.1%, cache read 12.9%. Reasoning уже внутри output.

## 1. Область и воспроизводимость
`python analysis/cost_audit.py` заново создаёт `public_results/cost_summary.json`, `public_results/action_categories.json`, `public_results/action_categories.csv` и этот документ. Скрипт не запускает команды агентов, grading или runner; не читает credentials; сеть в процессе заблокирована. Исходные providers.py, run_study.py, analyze.py и файлы других аналитиков не изменяются.

Включено 17 jobs. `pilot-luna-*` v1 исключены из сравнений из-за описанной в amendments контаминации; их расходы остаются в полном subtotal ledger. Диагностики отобраны после наблюдений и показаны отдельно. `main-haiku-stateless-cont` — отдельное продолжение, а не замена неуспешного T1.

**Живой срез:** файлы читаются последовательно, ledger — под краткой shared-lock. Межфайловой транзакции нет. Хеши/размеры источников и изменения в процессе чтения сохранены в JSON. Не завершённые задачи имеют только наблюдённый lower bound. Отсутствующая запись не означает нулевые затраты; ещё выполняющийся API-вызов в ledger не виден.

Не завершены на момент manifest: нет.
Изменились при захвате: 0 файлов; после захвата до конца анализа: 0. Предупреждений чтения: 0.

## 2. Деньги: ledger, успешные ответы и оплаченные ошибки
USD берутся из ledger, не пересуммируются только из успешных traces. «Успешный turn» означает принятый adapter ответ, а не правильное решение задачи: он может вызвать SQL-ошибку. Неполный модельный ответ отдельно может быть оплачен. **Codex: USD неизвестны, не $0.** `known_usd_subtotal` — лишь сумма известных цен; `total_usd=null` при неизвестной стоимости.

| Provider | Ledger entries, все | Все USD | Успешные USD | Failed USD | Выбранные jobs USD | USD неизвестно, entries |
| --- | --- | --- | --- | --- | --- | --- |
| anthropic | 154 | 0.149116 | 0.143555 | 0.005561 | 0.149116 | 0 |
| openrouter | 169 | 0.096286 | 0.096286 | 0.000000 | 0.096286 | 0 |
| codex | 246 | неизв. | неизв. | неизв. | неизв. | 246 |

OpenRouter `usage.cost` — авторитетный источник (включая возможный 0). Haiku — **оценка по настроенным тарифам**, не внешний invoice: $0.10 input, $0.50 output, $0.01 cache read, $0.125 cache write 5m, $0.20 cache write 1h за миллион; runner умножает все компоненты на 5 при полном input >100 000. Reasoning входит в output и не тарифицируется повторно.
Сверено 323 цен; расхождений: 0. Haiku вызовов с tier ×5: 0.

Компоненты всех записей Haiku в ledger: `input_uncached_usd` $0.000034, `output_usd` $0.093895, `cache_read_usd` $0.019222, `cache_write_5m_usd` $0.035965, `cache_write_1h_usd` $0.000000.

- `main-haiku-stateless/T1`, ledger turn 12 (0-based): **$0.005561**, stop=`max_tokens`, input 33,447, output 8,192, thinking 143. Usage совпадает с error checkpoint: True; подозрение на повтор last_response предыдущего успешного turn: False.

Сверка выбранных jobs: 500 successful ledger entries совпали с usage/ценой trace; расхождений 0; ledger entries ещё без trace turn 0; trace turns без ledger 0; повторных ключей ledger 0. Разрыв ledger→trace возможен во время shell-вызова: запись денег предшествует сохранению turn.

### Затраты по job и фазе
В таблице **все ledger responses, включая failed**. Cache — read / весь input; write отдельно от uncached. Детальные успешные turns, failed usage, timing и статусы каждого task доступны в JSON. W1/W2 включены в затраты подготовки, но это не стоимость исключительно «создания памяти»: warmup задачи решаются во всех режимах.

| Job | Фаза | Группа | Calls | Input | Cache read | Cache write | Uncached без write | Output | Reasoning ⊂ output | Hit токены | Success USD | Failed USD | Все USD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| diag-glm-t2-history-r1 | W1/W2 | diagnostic | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | 0.000000 | 0.000000 | 0.000000 |
| diag-glm-t2-history-r1 | T1/T2/T3 | diagnostic | 5 | 130273 | 115200 | 0 | 15073 | 4190 | 134 | 88.4% | 0.006097 | 0.000000 | 0.006097 |
| diag-glm-t2-history-r2 | W1/W2 | diagnostic | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | 0.000000 | 0.000000 | 0.000000 |
| diag-glm-t2-history-r2 | T1/T2/T3 | diagnostic | 9 | 254432 | 225792 | 0 | 28640 | 6704 | 955 | 88.7% | 0.011101 | 0.000000 | 0.011101 |
| diag-glm-t2-reset-r1 | W1/W2 | diagnostic | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | 0.000000 | 0.000000 | 0.000000 |
| diag-glm-t2-reset-r1 | T1/T2/T3 | diagnostic | 11 | 72984 | 59445 | 0 | 13539 | 7831 | 2130 | 81.4% | 0.004475 | 0.000000 | 0.004475 |
| diag-glm-t2-reset-r2 | W1/W2 | diagnostic | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | 0.000000 | 0.000000 | 0.000000 |
| diag-glm-t2-reset-r2 | T1/T2/T3 | diagnostic | 15 | 114513 | 107392 | 0 | 7121 | 9272 | 1330 | 93.8% | 0.005641 | 0.000000 | 0.005641 |
| diag-haiku-stateless-t1-outputguard | W1/W2 | diagnostic | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | 0.000000 | 0.000000 | 0.000000 |
| diag-haiku-stateless-t1-outputguard | T1/T2/T3 | diagnostic | 12 | 136336 | 118052 | 18258 | 26 | 16262 | 4502 | 86.6% | 0.011596 | 0.000000 | 0.011596 |
| diag-luna-managed-lifecycle | W1/W2 | diagnostic | 15 | 48449 | 6272 | 0 | 42177 | 5252 | 0 | 12.9% | неизв. | неизв. | неизв. |
| diag-luna-managed-lifecycle | T1/T2/T3 | diagnostic | 25 | 92012 | 10240 | 0 | 81772 | 8730 | 655 | 11.1% | неизв. | неизв. | неизв. |
| diag-luna-managed-maintain | W1/W2 | diagnostic | 14 | 47866 | 1024 | 0 | 46842 | 4985 | 118 | 2.1% | неизв. | неизв. | неизв. |
| diag-luna-managed-maintain | T1/T2/T3 | diagnostic | 23 | 86658 | 1024 | 0 | 85634 | 6969 | 157 | 1.2% | неизв. | неизв. | неизв. |
| main-glm-icl | W1/W2 | primary | 16 | 91125 | 37824 | 0 | 53301 | 7533 | 571 | 41.5% | 0.009617 | 0.000000 | 0.009617 |
| main-glm-icl | T1/T2/T3 | primary | 19 | 485472 | 423936 | 0 | 61536 | 17685 | 2303 | 87.3% | 0.024206 | 0.000000 | 0.024206 |
| main-glm-managed | W1/W2 | primary | 17 | 68759 | 40192 | 0 | 28567 | 9131 | 934 | 58.5% | 0.007877 | 0.000000 | 0.007877 |
| main-glm-managed | T1/T2/T3 | primary | 31 | 154858 | 88323 | 0 | 66535 | 16765 | 2867 | 57.0% | 0.015853 | 0.000000 | 0.015853 |
| main-glm-stateless | W1/W2 | primary | 17 | 69384 | 56076 | 0 | 13308 | 9842 | 2720 | 80.8% | 0.004351 | 0.000000 | 0.004351 |
| main-glm-stateless | T1/T2/T3 | primary | 29 | 126533 | 98614 | 0 | 27919 | 18571 | 3458 | 77.9% | 0.007067 | 0.000000 | 0.007067 |
| main-haiku-icl | W1/W2 | primary | 15 | 190883 | 168450 | 22399 | 34 | 16280 | 4368 | 88.2% | 0.012628 | 0.000000 | 0.012628 |
| main-haiku-icl | T1/T2/T3 | primary | 16 | 743873 | 704230 | 39605 | 38 | 27294 | 5864 | 94.7% | 0.025644 | 0.000000 | 0.025644 |
| main-haiku-managed | W1/W2 | primary | 21 | 191602 | 157346 | 34210 | 46 | 23004 | 5983 | 82.1% | 0.017356 | 0.000000 | 0.017356 |
| main-haiku-managed | T1/T2/T3 | primary | 35 | 403133 | 334986 | 68071 | 76 | 40966 | 10087 | 83.1% | 0.032349 | 0.000000 | 0.032349 |
| main-haiku-stateless | W1/W2 | primary | 21 | 187625 | 156292 | 31287 | 46 | 18845 | 6073 | 83.3% | 0.014901 | 0.000000 | 0.014901 |
| main-haiku-stateless | T1/T2/T3 | primary | 13 | 169857 | 136384 | 33445 | 28 | 19999 | 4927 | 80.3% | 0.009986 | 0.005561 | 0.015547 |
| main-haiku-stateless-cont | W1/W2 | continuation | 0 | 0 | 0 | 0 | 0 | 0 | 0 | — | 0.000000 | 0.000000 | 0.000000 |
| main-haiku-stateless-cont | T1/T2/T3 | continuation | 21 | 186967 | 146477 | 40444 | 46 | 25140 | 7142 | 78.3% | 0.019095 | 0.000000 | 0.019095 |
| pilot2-luna-icl | W1/W2 | primary | 12 | 51852 | 11648 | 0 | 40204 | 4082 | 0 | 22.5% | неизв. | неизв. | неизв. |
| pilot2-luna-icl | T1/T2/T3 | primary | 18 | 289039 | 104064 | 0 | 184975 | 8927 | 71 | 36.0% | неизв. | неизв. | неизв. |
| pilot2-luna-managed | W1/W2 | primary | 11 | 33077 | 0 | 0 | 33077 | 4139 | 34 | 0.0% | неизв. | неизв. | неизв. |
| pilot2-luna-managed | T1/T2/T3 | primary | 18 | 53433 | 7168 | 0 | 46265 | 9145 | 158 | 13.4% | неизв. | неизв. | неизв. |
| pilot2-luna-stateless | W1/W2 | primary | 14 | 40947 | 3456 | 0 | 37491 | 3845 | 34 | 8.4% | неизв. | неизв. | неизв. |
| pilot2-luna-stateless | T1/T2/T3 | primary | 28 | 86322 | 7424 | 0 | 78898 | 10378 | 204 | 8.6% | неизв. | неизв. | неизв. |

### Состояние покрытия задач
| Job | Manifest завершён | Task statuses |
| --- | --- | --- |
| diag-glm-t2-history-r1 | True | T2:completed |
| diag-glm-t2-history-r2 | True | T2:completed |
| diag-glm-t2-reset-r1 | True | T2:completed |
| diag-glm-t2-reset-r2 | True | T2:completed |
| diag-haiku-stateless-t1-outputguard | True | T1:completed |
| diag-luna-managed-lifecycle | True | W1:completed, W2:completed, T1:completed, T2:completed, T3:completed |
| diag-luna-managed-maintain | True | W1:completed, W2:completed, T1:completed, T2:completed, T3:completed |
| main-glm-icl | True | W1:completed, W2:completed, T1:completed, T2:completed, T3:completed |
| main-glm-managed | True | W1:completed, W2:completed, T1:completed, T2:completed, T3:completed |
| main-glm-stateless | True | W1:completed, W2:completed, T1:completed, T2:completed, T3:completed |
| main-haiku-icl | True | W1:completed, W2:completed, T1:completed, T2:completed, T3:completed |
| main-haiku-managed | True | W1:completed, W2:completed, T1:completed, T2:completed, T3:completed |
| main-haiku-stateless | True | W1:completed, W2:completed, T1:provider_error, T2:not_observed, T3:not_observed |
| main-haiku-stateless-cont | True | T2:completed, T3:completed |
| pilot2-luna-icl | True | W1:completed, W2:completed, T1:completed, T2:completed, T3:completed |
| pilot2-luna-managed | True | W1:completed, W2:completed, T1:completed, T2:completed, T3:completed |
| pilot2-luna-stateless | True | W1:completed, W2:completed, T1:completed, T2:completed, T3:completed |

## 3. Reasoning и фактический кэш
**Баг подтверждён:** `providers._tokens()` для Anthropic оставляет reasoning=0, а `analyze.py` суммирует это поле. Аудит читает native `usage.output_tokens_details.thinking_tokens`: исправлено 117 successful turns, восстановлено **48,803 thinking tokens**. Failed response usage учитывается отдельно. Output, input и деньги от этой коррекции не увеличиваются. Отсутствующее поле reasoning отмечается счётчиком missing, а не интерпретируется как доказанный ноль.

| Job | Input всего | Cache read | Read/input | Вызовы с hit | Без cache read | Частичный hit |
| --- | --- | --- | --- | --- | --- | --- |
| diag-glm-t2-history-r1 | 130273 | 115200 | 88.4% | 5 | 0 | 5 |
| diag-glm-t2-history-r2 | 254432 | 225792 | 88.7% | 9 | 0 | 9 |
| diag-glm-t2-reset-r1 | 72984 | 59445 | 81.4% | 11 | 0 | 11 |
| diag-glm-t2-reset-r2 | 114513 | 107392 | 93.8% | 14 | 1 | 14 |
| diag-haiku-stateless-t1-outputguard | 136336 | 118052 | 86.6% | 12 | 0 | 12 |
| diag-luna-managed-lifecycle | 140461 | 16512 | 11.8% | 6 | 34 | 6 |
| diag-luna-managed-maintain | 134524 | 2048 | 1.5% | 2 | 35 | 2 |
| main-glm-icl | 576597 | 461760 | 80.1% | 25 | 10 | 25 |
| main-glm-managed | 223617 | 128515 | 57.5% | 29 | 19 | 29 |
| main-glm-stateless | 195917 | 154690 | 79.0% | 42 | 4 | 42 |
| main-haiku-icl | 934756 | 872680 | 93.4% | 31 | 0 | 31 |
| main-haiku-managed | 594735 | 492332 | 82.8% | 55 | 1 | 55 |
| main-haiku-stateless | 357482 | 292676 | 81.9% | 31 | 3 | 31 |
| main-haiku-stateless-cont | 186967 | 146477 | 78.3% | 19 | 2 | 19 |
| pilot2-luna-icl | 340891 | 115712 | 33.9% | 12 | 18 | 12 |
| pilot2-luna-managed | 86510 | 7168 | 8.3% | 3 | 26 | 3 |
| pilot2-luna-stateless | 127269 | 10880 | 8.5% | 4 | 38 | 4 |

Наличие cache marker или большого общего префикса **не означает 100% hit**. Нулевая доля может быть cold/short prompt/expiry/provider policy; по логам нельзя однозначно выбрать причину. Partial hit означает наличие и cached, и non-read input, не обязательно ошибку кэша. Результаты отражают фактические запуски с возможным межзапусковым provider cache, не гарантированно cold-cache сравнение.

## 4. Первый target turn и переносимый контекст
Ниже каждый T1/T2/T3: input самого первого запроса из ledger, pre-task history, locally constructed request после task prompt и максимальный размер history после ответа. Формат chars совпадает с `len(json.dumps(native_history))` runner. History включает tool outputs, native reasoning/opaque data и прочие сообщения; payload также содержит инструменты/системные параметры. Это наблюдаемые размеры, **не токенизация chars/4 и не причинная доля расходов памяти**. Сумма state_chars в JSON многократно считает одинаковые префиксы и пригодна только как нагрузка повторной сериализации.

| Job | Target | Первый input | Первый cached | Hit | Pre history chars | Request history chars | Max state_chars | Memory before chars |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| diag-glm-t2-history-r1 | T2 | 25216 | 23040 | 91.4% | 98510 | 102318 | 121845 | 0 |
| diag-glm-t2-history-r2 | T2 | 25216 | 23040 | 91.4% | 98510 | 102318 | 139566 | 0 |
| diag-glm-t2-reset-r1 | T2 | 1246 | 37 | 3.0% | 693 | 4741 | 61599 | 0 |
| diag-glm-t2-reset-r2 | T2 | 1209 | 0 | 0.0% | 693 | 4741 | 64067 | 0 |
| diag-haiku-stateless-t1-outputguard | T1 | 2296 | 2292 | 99.8% | 2 | 5172 | 75248 | 0 |
| diag-luna-managed-lifecycle | T1 | 1440 | 0 | 0.0% | 1479 | 6617 | 37539 | 0 |
| diag-luna-managed-lifecycle | T2 | 1236 | 0 | 0.0% | 1479 | 5561 | 32726 | 0 |
| diag-luna-managed-lifecycle | T3 | 1177 | 0 | 0.0% | 1479 | 5390 | 50429 | 0 |
| diag-luna-managed-maintain | T1 | 1460 | 0 | 0.0% | 1557 | 6695 | 37905 | 226 |
| diag-luna-managed-maintain | T2 | 1256 | 0 | 0.0% | 1557 | 5639 | 24438 | 369 |
| diag-luna-managed-maintain | T3 | 1197 | 0 | 0.0% | 1557 | 5468 | 28900 | 369 |
| main-glm-icl | T1 | 14154 | 9216 | 65.1% | 55327 | 60263 | 98510 | 0 |
| main-glm-icl | T2 | 25216 | 18432 | 73.1% | 98510 | 102318 | 126200 | 0 |
| main-glm-icl | T3 | 32003 | 27648 | 86.4% | 126200 | 129789 | 156348 | 0 |
| main-glm-managed | T1 | 1433 | 0 | 0.0% | 841 | 5945 | 57375 | 9900 |
| main-glm-managed | T2 | 1272 | 37 | 2.9% | 841 | 4889 | 41962 | 9900 |
| main-glm-managed | T3 | 1175 | 0 | 0.0% | 841 | 4718 | 40431 | 9900 |
| main-glm-stateless | T1 | 1407 | 0 | 0.0% | 693 | 5797 | 48499 | 0 |
| main-glm-stateless | T2 | 1209 | 0 | 0.0% | 693 | 4741 | 55819 | 0 |
| main-glm-stateless | T3 | 1186 | 37 | 3.1% | 693 | 4570 | 33789 | 0 |
| main-haiku-icl | T1 | 30101 | 23888 | 79.4% | 83787 | 88959 | 133996 | 0 |
| main-haiku-icl | T2 | 46149 | 38114 | 82.6% | 133996 | 138112 | 163229 | 0 |
| main-haiku-icl | T3 | 56153 | 49938 | 88.9% | 163229 | 167174 | 198595 | 0 |
| main-haiku-managed | T1 | 2337 | 544 | 23.3% | 2 | 5172 | 81228 | 0 |
| main-haiku-managed | T2 | 2048 | 544 | 26.6% | 2 | 4116 | 109002 | 0 |
| main-haiku-managed | T3 | 1928 | 544 | 28.2% | 2 | 3945 | 41220 | 0 |
| main-haiku-stateless | T1 | 2296 | 0 | 0.0% | 2 | 5172 | 68274 | 0 |
| main-haiku-stateless-cont | T2 | 2007 | 0 | 0.0% | 2 | 4116 | 87077 | 0 |
| main-haiku-stateless-cont | T3 | 1887 | 0 | 0.0% | 2 | 3945 | 48373 | 0 |
| pilot2-luna-icl | T1 | 10209 | 0 | 0.0% | 41874 | 47012 | 74439 | 0 |
| pilot2-luna-icl | T2 | 16790 | 12928 | 77.0% | 74439 | 78521 | 93964 | 0 |
| pilot2-luna-icl | T3 | 21254 | 18304 | 86.1% | 93964 | 97875 | 109747 | 0 |
| pilot2-luna-managed | T1 | 1405 | 0 | 0.0% | 1288 | 6426 | 35472 | 0 |
| pilot2-luna-managed | T2 | 1201 | 0 | 0.0% | 1288 | 5370 | 32502 | 0 |
| pilot2-luna-managed | T3 | 1142 | 0 | 0.0% | 1288 | 5199 | 35157 | 0 |
| pilot2-luna-stateless | T1 | 1379 | 0 | 0.0% | 1140 | 6278 | 48221 | 0 |
| pilot2-luna-stateless | T2 | 1175 | 0 | 0.0% | 1140 | 5222 | 34165 | 0 |
| pilot2-luna-stateless | T3 | 1116 | 0 | 0.0% | 1140 | 5051 | 34690 | 0 |

Managed notes не добавляются автоматически: их содержимое входит в контекст только через выполненный shell read. Больший первый ICL input описывает перенос истории, но разницу цен нельзя целиком приписать памяти: меняются действия, output, cache и ошибки.

## 5. Native reasoning: retention и offline replay
Для каждого доступного pre/post/error checkpoint проверены точный round-trip `from_state → export_state` и чистое построение `_payload()`. Ни `_headers()`, ни `step()` не вызываются. Anthropic добавляет cache_control на последний user block, OpenRouter удаляет response-only `tool_calls[].index`, Codex передаёт весь native input. Равенство проверяется с учётом только этих преобразований; подписи/encrypted data сравниваются в памяти, но не выводятся. Сохранённый pre проверяется как prefix post; trace с native responses и tool results реконструируется и сравнивается с post. Это проверяет реально сохранённые блоки, а не только декларацию кода.

- **anthropic**: новые native-блоки/поля в доступных post (без повторного суммирования inherited prefixes): `{"anthropic_thinking_blocks": 117, "anthropic_thinking_blocks_with_signature": 117}`. Prefix: {'checked': 16, 'failed': 0}; trace reconstruction: {'checked': 16, 'failed': 0}; payload projection: {'checked': 33, 'failed': 0}.
- **openrouter**: новые native-блоки/поля в доступных post (без повторного суммирования inherited prefixes): `{"openrouter_messages_with_reasoning": 105, "openrouter_messages_with_reasoning_details": 105, "openrouter_detail_type:reasoning.text": 105}`. Prefix: {'checked': 19, 'failed': 0}; trace reconstruction: {'checked': 19, 'failed': 0}; payload projection: {'checked': 38, 'failed': 0}.
- **codex**: новые native-блоки/поля в доступных post (без повторного суммирования inherited prefixes): `{"codex_reasoning_items": 34, "codex_reasoning_items_with_encrypted_content": 34}`. Prefix: {'checked': 25, 'failed': 0}; trace reconstruction: {'checked': 25, 'failed': 0}; payload projection: {'checked': 50, 'failed': 0}.

В JSON есть межзадачные проверки ICL (`previous post == next pre`), подтверждение reset для остальных arms и точные совпадения pre-history диагностических replay с исходным checkpoint. Не утверждается, что сервер обязательно использовал каждый opaque block, сохранил скрытое внутреннее состояние или что audit отправил повторный запрос. Криптографическая валидность подписей также не проверялась.

## 6. Структура действий: эвристика, а не токен-атрибуция
`action_categories.csv/json` содержат **каждую shell-команду**, её полный текст (с защитным redaction), адрес job/task/turn/command, результат, timing, пересекающиеся labels и причины классификации. Категории: схема/README/registry и ориентация; аналитика и подготовка ответа; memory file IO; следующий шаг после наблюдённой ошибки. IO разделён на discovery/read/write candidates; обращение к несуществующему memory path не считается доказанным чтением заметки.

| Job | Фаза | Commands | Schema | Analytical | Memory IO | Recovery | Other | Mixed | С ошибкой |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| diag-glm-t2-history-r1 | prep_W1W2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| diag-glm-t2-history-r1 | target_T1T2T3 | 4 | 2 | 4 | 0 | 0 | 0 | 2 | 0 |
| diag-glm-t2-history-r2 | prep_W1W2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| diag-glm-t2-history-r2 | target_T1T2T3 | 8 | 4 | 8 | 0 | 0 | 0 | 4 | 0 |
| diag-glm-t2-reset-r1 | prep_W1W2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| diag-glm-t2-reset-r1 | target_T1T2T3 | 10 | 6 | 9 | 0 | 1 | 0 | 5 | 1 |
| diag-glm-t2-reset-r2 | prep_W1W2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| diag-glm-t2-reset-r2 | target_T1T2T3 | 14 | 8 | 7 | 0 | 5 | 3 | 8 | 5 |
| diag-haiku-stateless-t1-outputguard | prep_W1W2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| diag-haiku-stateless-t1-outputguard | target_T1T2T3 | 11 | 5 | 8 | 0 | 5 | 0 | 7 | 5 |
| diag-luna-managed-lifecycle | prep_W1W2 | 13 | 6 | 7 | 0 | 1 | 0 | 1 | 1 |
| diag-luna-managed-lifecycle | target_T1T2T3 | 22 | 10 | 11 | 0 | 4 | 2 | 5 | 4 |
| diag-luna-managed-maintain | prep_W1W2 | 12 | 8 | 6 | 4 | 1 | 0 | 6 | 1 |
| diag-luna-managed-maintain | target_T1T2T3 | 20 | 11 | 12 | 8 | 0 | 0 | 10 | 0 |
| main-glm-icl | prep_W1W2 | 14 | 12 | 11 | 0 | 6 | 0 | 12 | 6 |
| main-glm-icl | target_T1T2T3 | 16 | 13 | 16 | 0 | 3 | 0 | 14 | 3 |
| main-glm-managed | prep_W1W2 | 17 | 11 | 12 | 3 | 2 | 0 | 11 | 2 |
| main-glm-managed | target_T1T2T3 | 33 | 20 | 20 | 2 | 3 | 0 | 12 | 3 |
| main-glm-stateless | prep_W1W2 | 15 | 9 | 9 | 0 | 1 | 0 | 4 | 1 |
| main-glm-stateless | target_T1T2T3 | 26 | 13 | 20 | 0 | 3 | 0 | 8 | 3 |
| main-haiku-icl | prep_W1W2 | 13 | 6 | 11 | 0 | 3 | 0 | 7 | 3 |
| main-haiku-icl | target_T1T2T3 | 13 | 4 | 13 | 0 | 2 | 0 | 6 | 2 |
| main-haiku-managed | prep_W1W2 | 19 | 12 | 13 | 1 | 1 | 0 | 8 | 1 |
| main-haiku-managed | target_T1T2T3 | 32 | 17 | 23 | 4 | 9 | 0 | 20 | 9 |
| main-haiku-stateless | prep_W1W2 | 19 | 12 | 13 | 0 | 3 | 0 | 8 | 3 |
| main-haiku-stateless | target_T1T2T3 | 12 | 6 | 9 | 0 | 4 | 0 | 7 | 4 |
| main-haiku-stateless-cont | prep_W1W2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| main-haiku-stateless-cont | target_T1T2T3 | 19 | 11 | 11 | 0 | 4 | 0 | 7 | 4 |
| pilot2-luna-icl | prep_W1W2 | 10 | 4 | 7 | 0 | 1 | 0 | 2 | 1 |
| pilot2-luna-icl | target_T1T2T3 | 15 | 4 | 14 | 0 | 3 | 0 | 6 | 4 |
| pilot2-luna-managed | prep_W1W2 | 9 | 4 | 5 | 0 | 1 | 1 | 2 | 1 |
| pilot2-luna-managed | target_T1T2T3 | 15 | 13 | 9 | 0 | 0 | 0 | 7 | 0 |
| pilot2-luna-stateless | prep_W1W2 | 12 | 9 | 8 | 0 | 1 | 0 | 6 | 1 |
| pilot2-luna-stateless | target_T1T2T3 | 25 | 22 | 11 | 0 | 2 | 0 | 10 | 2 |

**Оговорка аудита:** labels non-exclusive; суммы превышают число команд. Одна команда может читать README, schema, memory и выполнять SQL. Regex не строит shell AST, не доказывает исполнение ветвей `&&` и может видеть SQL внутри записываемого текста. «Recovery» — следующий command после exit/SQL/error-text, не доказанное исправление причины. На эти категории **не распределяются токены, USD или wall time**; нет выдуманной стоимости исследования схемы/памяти. Это прозрачный индекс для ручной проверки команд, а не точная оценка query count.

## 7. Wall time и дорогие SQL-вызовы
Model wall — latency `session.step()`, failed request wall — отдельно из checkpoint failure. Shell wall — всё выполнение bash; CLI SQL wall — внутренний замер subprocess sqlite3 и уже входит в shell. **Не складывать SQL+shell.** Суммы разных jobs не равны длительности всего исследования: jobs работали параллельно. Python `sqlite3` не обёрнут таймером; inline/ранее записанные scripts определяются лишь эвристически. Отсутствие CLI timer не доказывает отсутствие SQL (Python, подавленный stderr, убитая wrapper). Один CLI invocation может исполнять много SQL statements; timeout/kill не всегда оставляет timer.

| Job | Model success s | Model failed s | Shell s | CLI invocations | CLI s | CLI >1s | Shell >1s | Python candidates | Python SQLite candidates |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| diag-glm-t2-history-r1 | 20.78 | 0.00 | 3.11 | 4 | 0.38 | 0 | 0 | 1 | 0 |
| diag-glm-t2-history-r2 | 36.88 | 0.00 | 3.33 | 10 | 0.37 | 0 | 0 | 1 | 0 |
| diag-glm-t2-reset-r1 | 166.75 | 0.00 | 13.32 | 32 | 0.47 | 0 | 1 | 1 | 0 |
| diag-glm-t2-reset-r2 | 61.25 | 0.00 | 5.04 | 11 | 0.17 | 0 | 0 | 4 | 3 |
| diag-haiku-stateless-t1-outputguard | 61.37 | 0.00 | 52.65 | 15 | 48.39 | 1 | 3 | 0 | 0 |
| diag-luna-managed-lifecycle | 300.88 | 0.00 | 12.86 | 18 | 6.05 | 1 | 1 | 14 | 11 |
| diag-luna-managed-maintain | 264.82 | 0.00 | 7.76 | 24 | 0.28 | 0 | 0 | 8 | 4 |
| main-glm-icl | 137.63 | 0.00 | 12.00 | 36 | 1.38 | 0 | 0 | 4 | 0 |
| main-glm-managed | 274.61 | 0.00 | 19.78 | 43 | 1.25 | 0 | 3 | 7 | 0 |
| main-glm-stateless | 461.14 | 0.00 | 19.72 | 44 | 1.65 | 0 | 3 | 6 | 0 |
| main-haiku-icl | 164.89 | 0.00 | 21.93 | 57 | 2.16 | 0 | 5 | 0 | 0 |
| main-haiku-managed | 245.79 | 0.00 | 77.81 | 40 | 62.33 | 2 | 4 | 7 | 3 |
| main-haiku-stateless | 126.99 | 21.99 | 19.41 | 55 | 1.70 | 0 | 4 | 3 | 1 |
| main-haiku-stateless-cont | 98.25 | 0.00 | 8.99 | 19 | 0.95 | 0 | 3 | 2 | 0 |
| pilot2-luna-icl | 270.33 | 0.00 | 6.81 | 23 | 0.50 | 0 | 0 | 5 | 0 |
| pilot2-luna-managed | 277.10 | 0.00 | 5.79 | 18 | 0.16 | 0 | 0 | 7 | 6 |
| pilot2-luna-stateless | 303.95 | 0.00 | 15.60 | 56 | 0.44 | 0 | 3 | 7 | 4 |

### Все реально наблюдённые SQL CLI invocations >1 s (4)
Ниже полный список, а не только максимум. Wrapper сохраняет порядок таймеров, но не argv: для смешанной команды публикуется родительская команда целиком, без выдуманной привязки времени к отдельному SQL statement.

#### `diag-haiku-stateless-t1-outputguard/T1/turn-9/command-1` — CLI #1
CLI **47.311958 s**, SQL exit `1`; shell 47.623415 s, shell exit `1`; группа `diagnostic`.

````bash
cd /work; D=../data/current.db; sqlite3 -header $D "$(cat base.sql) , cells AS (SELECT period, region_code, class_code, build_code, COUNT(*) n, SUM(tf) f, 100.0*SUM(tf)/COUNT(*) p FROM base GROUP BY 1,2,3,4), w AS (SELECT build_code, AVG(p) std FROM cells GROUP BY 1), d AS (SELECT c.period,c.region_code,c.class_code, c.p cand, r.p ref FROM cells c JOIN cells r ON r.period=c.period AND r.region_code=c.region_code AND r.class_code=c.class_code AND r.build_code='idx-r18' WHERE c.build_code='idx-r19') SELECT (SELECT std FROM w WHERE build_code='idx-r18') ref_std, (SELECT std FROM w WHERE build_code='idx-r19') cand_std, (SELECT std FROM w WHERE build_code='idx-r19')-(SELECT std FROM w WHERE build_code='idx-r18') diff, (SELECT COUNT(*) FROM d WHERE cand>ref) worse, (SELECT COUNT(*) FROM d) slices; SELECT build_code, COUNT(*), SUM(f), 100.0*SUM(f)/SUM(n) FROM cells GROUP BY 1; SELECT period, build_code, SUM(n), SUM(f), 100.0*SUM(f)/SUM(n) FROM cells GROUP BY 1,2; SELECT period, SUM(n), SUM(f), 100.0*SUM(f)/SUM(n) FROM cells GROUP BY 1;"
````

#### `diag-luna-managed-lifecycle/W1/turn-4/command-1` — CLI #1
CLI **5.895709 s**, SQL exit `0`; shell 6.184357 s, shell exit `0`; группа `diagnostic`.

````bash
sqlite3 -header -column ../data/current.db "WITH ops AS (SELECT o.operation_id,r.service_id FROM logical_operations o JOIN service_routes r USING(route_id) WHERE opened_at_ms>=1777629600000 AND opened_at_ms<1777633200000), a AS (SELECT a.operation_id,count(*) attempts,sum(CASE WHEN f.is_success=0 THEN 1 ELSE 0 END) failed_attempts FROM attempt_events a JOIN failure_codes f USING(code_id) GROUP BY a.operation_id), fin AS (SELECT a.operation_id,f.is_success FROM attempt_events a JOIN failure_codes f USING(code_id) WHERE a.attempt_no=(SELECT max(x.attempt_no) FROM attempt_events x WHERE x.operation_id=a.operation_id)), pools AS (SELECT DISTINCT o.operation_id,ra.pool_id FROM ops o JOIN logical_operations lo USING(operation_id) JOIN service_routes sr USING(route_id) JOIN route_assignments ra ON ra.route_id=sr.route_id AND lo.opened_at_ms>=ra.effective_from_ms AND lo.opened_at_ms<ra.effective_to_ms) SELECT s.service_code,count(*) operations,sum(a.attempts) attempts,sum(a.failed_attempts) failed_attempts,sum(fin.is_success=0) terminal_failures,sum(a.attempts>1) retried_operations,round(100.0*sum(fin.is_success=0)/count(*),4) terminal_failure_pct,(SELECT count(DISTINCT p.pool_id) FROM pools p WHERE p.operation_id IN (SELECT operation_id FROM ops WHERE service_id=s.service_id)) physical_pools FROM ops JOIN services s USING(service_id) JOIN a USING(operation_id) JOIN fin USING(operation_id) GROUP BY s.service_id;"
````

#### `main-haiku-managed/T2/turn-7/command-1` — CLI #1
CLI **56.940824 s**, SQL exit `-9`; shell 57.208482 s, shell exit `247`; группа `primary`.

````bash
cd /work; cat > /tmp/base.sql <<'EOF'
with ops as (
  select o.operation_id, o.opened_at_ms,
    case when o.opened_at_ms>=1778148000000 and o.opened_at_ms<1778151600000 then 'reference_10_11'
         when o.opened_at_ms>=1778151600000 and o.opened_at_ms<1778155200000 then 'incident_11_12' end period,
    a.pool_id, p.pool_code, pp.deadline_ms
  from logical_operations o
  join service_routes sr on sr.route_id=o.route_id and sr.service_id=2
  join route_assignments a on a.route_id=o.route_id and o.opened_at_ms>=a.effective_from_ms and o.opened_at_ms<a.effective_to_ms
  join worker_pools p on p.pool_id=a.pool_id
  join policy_profiles pp on pp.profile_id=a.profile_id
  where o.opened_at_ms>=1778148000000 and o.opened_at_ms<1778155200000
),
att as (
  select ae.*, fc.is_success from attempt_events ae join failure_codes fc on fc.code_id=ae.code_id
),
opstat as (
  select ops.*,
    (select count(*) from att where att.operation_id=ops.operation_id) natt,
    (select is_success from att where att.operation_id=ops.operation_id order by attempt_no desc limit 1) final_success,
    (select queue_ms from att where att.operation_id=ops.operation_id order by attempt_no desc limit 1) final_queue,
    (select execution_ms from att where att.operation_id=ops.operation_id order by attempt_no desc limit 1) final_exec
  from ops
)
EOF
cat /tmp/base.sql > /tmp/q1.sql; cat >> /tmp/q1.sql <<'EOF'
select period, pool_code, count(*) operations,
  sum(final_success=0) terminal_failures,
  round(100.0*sum(final_success=0)/count(*),4) terminal_failure_pct,
  sum(natt) attempts,
  sum((select count(*) from att a where a.operation_id=opstat.operation_id and a.is_success=0)) failed_attempts,
  round(100.0*sum((select count(*) from att a where a.operation_id=opstat.operation_id and a.is_success=0))/sum(natt),4) attempt_failure_pct,
  sum(natt>1) retried_operations,
  min(deadline_ms) min_deadline_ms, max(deadline_ms) max_deadline_ms,
  round(avg(case when final_success=0 then final_queue end),4) failed_terminal_queue_mean_ms,
  round(avg(case when final_success=0 then final_exec end),4) failed_terminal_execution_mean_ms
from opstat group by period, pool_code order by period, pool_code;
EOF
sqlite3 -header ../data/current.db < /tmp/q1.sql
````

#### `main-haiku-managed/T2/turn-8/command-1` — CLI #1
CLI **3.051095 s**, SQL exit `0`; shell 3.344054 s, shell exit `0`; группа `primary`.

````bash
cd /work; cat > /tmp/q1.sql <<'EOF'
with ops as (
  select o.operation_id, o.opened_at_ms,
    case when o.opened_at_ms>=1778148000000 and o.opened_at_ms<1778151600000 then 'reference_10_11'
         when o.opened_at_ms>=1778151600000 and o.opened_at_ms<1778155200000 then 'incident_11_12' end period,
    p.pool_code, pp.deadline_ms
  from logical_operations o
  join service_routes sr on sr.route_id=o.route_id and sr.service_id=2
  join route_assignments a on a.route_id=o.route_id and o.opened_at_ms>=a.effective_from_ms and o.opened_at_ms<a.effective_to_ms
  join worker_pools p on p.pool_id=a.pool_id
  join policy_profiles pp on pp.profile_id=a.profile_id
  where o.opened_at_ms>=1778148000000 and o.opened_at_ms<1778155200000
),
att as (
  select ae.operation_id, ae.attempt_no, ae.queue_ms, ae.execution_ms, fc.is_success,
    count(*) over (partition by ae.operation_id) natt,
    row_number() over (partition by ae.operation_id order by ae.attempt_no desc) rn_desc
  from attempt_events ae join failure_codes fc on fc.code_id=ae.code_id
  where ae.operation_id in (select operation_id from ops)
),
opstat as (
  select ops.period, ops.pool_code, ops.deadline_ms, ops.operation_id,
    max(case when att.rn_desc=1 then att.is_success end) final_success,
    max(case when att.rn_desc=1 then att.queue_ms end) final_queue,
    max(case when att.rn_desc=1 then att.execution_ms end) final_exec,
    max(att.natt) natt,
    sum(att.is_success=0) failed_attempts
  from ops join att using(operation_id) group by 1,2,3,4
)
select period, pool_code, count(*) operations,
  sum(final_success=0) terminal_failures,
  round(100.0*sum(final_success=0)/count(*),4) terminal_failure_pct,
  sum(natt) attempts, sum(failed_attempts) failed_attempts,
  round(100.0*sum(failed_attempts)/sum(natt),4) attempt_failure_pct,
  sum(natt>1) retried_operations,
  min(deadline_ms) min_deadline_ms, max(deadline_ms) max_deadline_ms,
  round(avg(case when final_success=0 then final_queue end),4) failed_terminal_queue_mean_ms,
  round(avg(case when final_success=0 then final_exec end),4) failed_terminal_execution_mean_ms
from opstat group by period, pool_code order by period, pool_code;
EOF
time sqlite3 -header ../data/current.db < /tmp/q1.sql
````

Список **всех shell >1 s**, включая Python без отдельного SQL timer, находится в `cost_summary.json → long_shell_commands_over_1s`; полные команды и durations также доступны в action CSV. Nonzero exit при длинном запросе — затраченное время, не успешный результат. Причину kill нельзя уверенно вывести лишь из exit code.

## 8. Access / native smoke — отдельные известные затраты
Не смешиваются с ledger исследования. Используются только сохранённые `usage` из доступных `access*.json` и `native_smoke.json`. Haiku оценён по тем же настроенным тарифам (smoke изначально мог иметь cost=null без rates); OR — `usage.cost`; Codex неизвестен. Каталоги, access summary, OAuth и ошибки без usage не превращаются в выдуманные $0 или предполагаемые inference-токены. Сохранённые данные не доказывают полноту всех исторических probes.

| Файл | Provider | Turn | Input | Output | Reasoning | USD | Источник |
| --- | --- | --- | --- | --- | --- | --- | --- |
| access_native_checks.json | anthropic | — | 503 | 32 | 0 | 0.000066 | estimate_configured_Haiku_rates_not_ledger |
| access_native_checks.json | openrouter | — | 196 | 11 | 0 | 0.000013 | usage.cost |
| native_smoke.json | anthropic | 1 | 417 | 54 | 0 | 0.000069 | estimate_configured_Haiku_rates_not_ledger |
| native_smoke.json | anthropic | 2 | 489 | 24 | 0 | 0.000061 | estimate_configured_Haiku_rates_not_ledger |
| native_smoke.json | anthropic | 3 | 539 | 100 | 85 | 0.000117 | estimate_configured_Haiku_rates_not_ledger |
| native_smoke.json | openrouter | 1 | 192 | 17 | 0 | 0.000010 | usage.cost |
| native_smoke.json | openrouter | 2 | 224 | 9 | 0 | 0.000014 | usage.cost |
| native_smoke.json | openrouter | 3 | 252 | 6 | 0 | 0.000015 | usage.cost |
| native_smoke.json | codex | 1 | 159 | 23 | 0 | неизв. | unknown_subscription_marginal_cost |
| native_smoke.json | codex | 2 | 203 | 5 | 0 | неизв. | unknown_subscription_marginal_cost |
| native_smoke.json | codex | 3 | 231 | 7 | 0 | неизв. | unknown_subscription_marginal_cost |

| Provider | Известный probe subtotal USD | Полный USD | Записей usage |
| --- | --- | --- | --- |
| anthropic | 0.000313 | 0.000313 | 4 |
| openrouter | 0.000052 | 0.000052 | 4 |
| codex | неизв. | неизв. | 3 |

## 9. Выводы и границы интерпретации
- Денежный итог нужно брать из ledger с failed responses: сумма успешных traces занижает оплаченные расходы при output guard.
- Reasoning у Haiku действительно наблюдается; исходный ноль — дефект локальной нормализации, а не отсутствие thinking.
- Full-context ICL измеримо переносит историю; кэш уменьшает оплачиваемую нагрузку неодинаково по вызовам. Cache read и полный input — разные метрики.
- Managed memory требует фактического чтения/записи. Категория directory discovery сама по себе не доказывает перенос полезной информации.
- Большинство SQL CLI timings и shell timings следует читать раздельно; редкие долгие и неуспешные запросы могут заметно увеличить tool wall. Python SQL покрыт лишь частично.
- Одна последовательность и выбранные постфактум диагностики не дают оснований объявлять причинную «цену памяти», универсальное преимущество arm или стоимость category в токенах.

### Локальные источники
- [`../providers.py`](../providers.py): `_tokens`, `_payload`, `_extract`, `from_state` и сохранение native history.
- [`../run_study.py`](../run_study.py): `cost`, ledger, порядок сохранения turns, task/session lifecycle и state_chars.
- [`../sandbox.py`](../sandbox.py): SQL CLI timing wrapper, shell wall, limits и частичное покрытие Python.
- [`../provider_config.json`](../provider_config.json), [`../ledger.jsonl`](../ledger.jsonl), `../runs/*/{manifest.json,*/trace.json}`.
- Private `pre_state/post_state/error_state` используются только для локальных сравнений; содержимое не публикуется.
- [`amendments.md`](amendments.md), [`protocol.md`](protocol.md): исключение pilot v1 и отдельные диагностики.
- [`../public_results/cost_summary.json`](../public_results/cost_summary.json), [`../public_results/action_categories.csv`](../public_results/action_categories.csv): воспроизводимые детали.
