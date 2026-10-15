# Маршрут работ по оптимизации

2026-10-12. Проект **AI-поиск дублей**.
Рабочая Git-ветка: `codex/upload-optimiz`.
Рабочий каталог: `/Users/v.pribylovskiy/Documents/ChatGPT/Ai`.

По решению владельца от 2026-10-12 дальнейшие анализ, гипотезы, документы и код
оптимизации вести в текущем рабочем каталоге на `codex/upload-optimiz`.

Прежняя точка входа и незакоммиченные изменения находятся в сохранённом checkout
`/Users/v.pribylovskiy/.codex/worktrees/corpus-optimization/Ai` на
`codex/corpus-optimization`. Его README описывает предыдущее место работы;
актуальный маршрут задаёт этот документ. Смена маршрута не переносит код между
checkout и не подтверждает совпадение их реализации.

## Актуальная точка продолжения

Последний пакет2026-10-15: [20фото прошли](../001-corpus-replenishment/four-batches-runtime-report.md),
[качество5из7частично оценено](staged-quality-seven-report.md).
Обнаружен плохой положительный ранг16; на оставшейся партииSTOPтелеметрии.
Воспроизводимая гонка исправлена поTDD, без новогоML. [Текущий статус этапов](../001-corpus-replenishment/verification-followup-status.md).
50–100не запускались, рабочий корпус не изменён.


**2026-10-15:** [контекст проекта](project-context.md) — текущие коммиты,
реализованные возможности, измерения нагрузки, ограничения и следующий шаг.
Реализация и ограниченные runtime-пробы уже выполнены. Последующие записи
этого README — история этапов; формулировки «следующий шаг» в них относятся
к своей дате, а не задают текущую задачу.

## Документы исследования

Для первого знакомства с процессом: [AS-IS](as-is.md) — текущая сборка и её
ограничения; [TO-BE](to-be.md) — проект обработки партиями с решениями владельца.
В документах встроены SVG; [исходники и инструкция редактирования](diagrams/README.md).

[Функциональные требования к пополнению](functional-requirements.md) — отдельный
документ набора ART-06, v1 / APPROVED_BY_OWNER; утверждён сообщением «Утверждаю»
2026-10-12 после review и исправления Minor.

[HLD пополнения корпуса](hld.md) — v1.1 / APPROVED_BY_OWNER: компоненты, управление режимами,
checkpoints, публикация через снимки каталога и границы ядра/портов/адаптеров.
Утверждён сообщением «Утверждаю» 2026-10-12 после review и исправлений.

1. [Сводка исследования](research-summary.md) — проблема, факты, ограничения,
   источники, позиции владельца и открытые вопросы.
2. [Реестр гипотез](hypotheses.md) — предположения, основания и способы проверки,
   включая условия, которые будут им противоречить.
3. [План сравнения моделей](model-ablation-plan.md) и
   [результат семи комбинаций](model-ablation-report.md) — завершённая ограниченная проверка.
4. [Инвентаризация данных](model-ablation-inventory.md),
   [план ручного стенда](manual-recheck-plan.md) и
   [отчёт стенда](manual-recheck-report.md) — подготовка запросов и owner-разметки.

Подробные источники: [диагностика памяти](../candidate-i-http/memory-pressure-diagnosis.md),
[анализ вариантов](../candidate-i-http/memory-efficiency-proposal.md),
[результат image-only загрузки](../candidate-i-http/image-only-load-report.md),
[остановленная сборка100](../candidate-i-http/skip-photo-build-report.md) и
[предложение пополнения](../candidate-i-http/incremental-corpus-proposal.md).

Смена рабочей ветки не является разрешением на новый ML/build/publish.

Последняя проверка: [сравнение семи комбинаций моделей](model-ablation-report.md)
на трёх подтверждённых запросах. Все варианты дали ранги1/1/1; модель не отключена.

[TO-BE v2](to-be.md) утверждён владельцем 2026-10-12 сообщением «Да утверждаю»
после независимого review и исправления Minor. [Функциональные требования v1](functional-requirements.md)
также утверждены. [HLD v1.1](hld.md) утверждён владельцем. Следующий этап —
отдельный LLD/технический план реализации и проверки.
Владелец выбрал до 5 фото на запуск, ручной retry ошибок, ограниченную паузу
warning, работу поиска/build по очереди и автоматическую публикацию товара
после завершения всех выбранных фото при наличии хотя бы одного готового.
Процесс и инженерные механизмы утверждены как проект; их работоспособность
ещё предстоит проверить. Утверждение процесса не разрешает ML/build/DB/publish.

## Spec Kit

[Компактная спецификация](../001-corpus-replenishment/spec.md) — v1 / APPROVED_BY_OWNER;
[чек-лист](../001-corpus-replenishment/checklists/requirements.md). Канонические ФТ
сохранены в ART-06; критерии пополнения добавлены в ART-09 со статусом APPROVED_BY_OWNER.
TDD применяется к последующей реализации. Спецификация/критерии согласованы
2026-10-12; следующий шаг — speckit-plan и speckit-tasks по owner gates.

[Технический план Spec Kit](../001-corpus-replenishment/plan.md) — v1 / APPROVED_BY_OWNER;
research, data-model, contracts и quickstart содержат выборочный LLD.
План сохраняет TDD и отдельные gates baseline/test DB/native/ML; tasks после approval.

[Задачи Spec Kit](../001-corpus-replenishment/tasks.md) подготовлены по
утверждённому техническому пакету: 51 пункт, TDD и зависимости. Самопроверка
speckit-analyze не выявила пробелов покрытия; исполнение не начиналось.
Первый шаг исполнения — B0 source manifest и согласование baseline.

B0, 2026-10-13: [manifest и предложение переноса](../001-corpus-replenishment/baseline-review.md)
подготовлены, пункт001 выполнен. Конкретный baseline ожидает owner approval
по пункт002; ни source transfer, ни ML/БД не выполнены.

Обновление2026-10-13: B0 утверждён владельцем, baseline перенесён;
[отчёт проверок и первого TDD цикла](../001-corpus-replenishment/baseline-transfer-report.md).
Отдельные integration/native/ML gates сохраняются.

2026-10-13: [unit core008–016](../001-corpus-replenishment/unit-core-report.md)
реализован и проверен; [B1](../001-corpus-replenishment/test-execution-package.md)
подготовлен к утверждению. Фактическое пополнение ещё не разрешено и не выполнялось.

2026-10-13: [B1 progress](../001-corpus-replenishment/b1-progress-report.md):
native26/files15 иunit427passed; DB bootstrap blocked наPythonpgvector
migration0005. [Dependency дополнение](../001-corpus-replenishment/test-dependency-addendum.md)
подготовлено, установка ожидает отдельного утверждения.

2026-10-13: dependency блокер снят отдельным разрешением владельца:
pgvector0.5.0 установлен изpipcache; B1baseline bootstrap1passed,
ownedcontainer удалён. Дальше020–022 schema/stateTDD; фактического
пополнения/ML/рабочейDBpublication не было.

2026-10-13: [schema/state adapter020–022](../001-corpus-replenishment/state-adapter-report.md)
реализован по TDD:25DB и всего497проверок выбранных компонентов прошли.
Временные testDB удалены. Следующий этап — транзакция публикации; реальное
пополнение, ML и изменение рабочей БД ещё не выполнялись.

2026-10-14: [подготовка и публикация026–028](../001-corpus-replenishment/publication-report.md)
проверены по TDD в B1 synthetic DB. Дальше — чтение snapshot поиском;
автоматическое включение публикации в пользовательский процесс ещё предстоит.

2026-10-14: [snapshot reader/runtime binding029–031](../001-corpus-replenishment/catalog-binding-report.md)
проверены в B1; synthetic legacy/snapshot parity прошла. Backend приложения
не переключён. Далее — CLI, временная недоступность и fake вертикальный сценарий.

2026-10-14: [CLI и вертикальный fake flow032–035](../001-corpus-replenishment/cli-flow-report.md)
проверены:582passed выбранной регрессии. Start/status проходят через private IPC;
resume/retry пока отклоняются до реализации036–046. Реальный runtime не запускался.

2026-10-14: [resume, ожидание и recovery036–042](../001-corpus-replenishment/resume-recovery-report.md)
проверены на синтетических данных:601passed выбранной регрессии. Resume использует
сохранённую партию; следующие фото и ERROR автоматически не запускаются.
Ожидание ограничено300секундами. Далее — явные retry043–046;
реальный runtime и пополнение остаются за отдельным допуском.

2026-10-14: [ручной retry043–046](../001-corpus-replenishment/retry-report.md)
проверен в B1:611passed выбранной регрессии. Ошибочное фото повторяется явно
в новой редакции; публикация повторяется без ML после сверки сохранённого состояния.
Следующий шаг — трассировка требований и оставшиеся сквозные проверки047–048.
Реальное пополнение и runtime не запускались.

2026-10-14: [трассировка и сквозные проверки047–048](../001-corpus-replenishment/acceptance-verification-report.md).
Все52 FR сопоставлены с тестами;7остаются частично подтверждёнными до runtime.
Синтетические5+2 и migration rollback проверены; исправлена неполная сводка
состояния товаров.619различных успешных случаев, при этом общий B1 дал один
setup error readiness, а отдельная диагностика этого случая прошла.
Реальный runtime/пополнение не запускались. Следующий шаг049 — конкретный
пакет runtime и binding; запуск050 требует отдельного разрешения.

2026-10-14: [runtime proposal049](../001-corpus-replenishment/runtime-probe-proposal.md)
подготовлен для одного выбранного фото. Локальные модели/окружения найдены,
bytes/metadata fingerprints проверены; исходник сохранён, private copy зафиксирована.
049 остаётся открытым до настоящей связки StageWorkers/host/resources/claims.
Model-free readiness не означает ML-ready;050 и рабочее пополнение не запускались.

2026-10-14: продолжение049 — [runtime binding подготовлен](../001-corpus-replenishment/runtime-binding-verification-report.md),
512 выбранных проверок и1 synthetic DB case. Новый пакет для одного фото
заморожен;049 выполнен как подготовка. [050](../001-corpus-replenishment/runtime-probe-proposal.md)
не запущен и требует отдельного разрешения на конкретный SHA;051 открыт.
