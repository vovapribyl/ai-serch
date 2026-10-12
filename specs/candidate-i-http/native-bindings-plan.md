# T051 — реальные bindings и model-free подготовка тестового прогона

2026-10-10. Owner «Разрешаю, начинай» на переход от generic fake wiring к подготовке
реальных bindings, тестового корпуса/bill и изолированного интерфейса. Состав первого
прогона отдельно уточняется: исходные674/input manifest/oversize-фото не менять.
Действующее source defer сохраняется до конкретного owner ответа.

FULL: исполнитель inline/TDD → реальные metadata/manifest/DB checks без ML →
concrete pinned native job/bill → один independent read-only reviewer → допуск
execution по конкретным входам/fingerprints/числовым bounds. Новый native run пока
не запускается; publish/READY/active pointer не выполняются до coverage и отдельного
test-activation решения. Рабочая система/Git публикация остаются за пределами.

Ponytail/Clean Architecture mini: переиспользовать `assemble_service`,
`HttpNailLocalizationAdapter`, existing provider classes, `PostgresNailCatalog`,
`NailSearchService`/`NailQueryRunner`, generic composition и guards. SDK imports
только внутри lazy admitted factories, не в preparation/check CLI. G4 accepted
source/config/env/weights и старые snapshots не менять.

- [x] Проверить exact G4 I assembly/profile/interpreters/package fingerprints и
  provider manifests по actual byte metadata, без Torch/Transformers import.
- [x] TDD: native provider factories lazy; actual Postgres/image/HTTP/query ports
  строятся без SDK; wrong identity/permit/target → до записи/model load. Подготовить
  independent pinned runtime observations и owned I server startup/ready/teardown.
- [x] После owner ответа подготовить отдельные test inputs с provenance; исходный
  corpus/manifest и oversize-фото сохранить. Подготовить actual native worker/command
  с I/backend environment separation, observer/budget/owned teardown и no publish.
- [x] Scoped fake/SQL/native-model-free checks → private source/job snapshots,
  safe report и exact bill → independent review. Native SDK/build перед предъявлением
  concrete execution package не запускать.

Без owner ответа зависимая подготовка subset не выполняется. Query examples/window,
coverage exceptions, test publish и final activation не подменяются разрешением
подготовить реальные bindings. Не объявлять подготовку готовым индексом/качеством.


Обновление2026-10-11: source choice закрыт — approved отдельная копия1536×1536,
674positions; [подготовка входов](oversize-input-report.md) выполнена. Объединённый
шаг inputs/nativeworker остаётся[ ], так как actual worker/command/bill ещё не готовы.
Исторический defer и вопрос673vs674 выше относятся к2026-10-10.

Обновление2026-10-11 после подготовки команды: [actual package](native-execution-package.md)
и frozen nativeworker/argv/check готовы. Шаги подготовки выполнены; real ML approval
не присвоен. Историческая запись о combinedstep[ ] выше относится к состоянию до command.
