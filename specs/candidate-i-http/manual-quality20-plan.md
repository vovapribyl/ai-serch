# Ручной тест полного поиска на20 готовых фото

2026-10-11. FULL. OWNER_DECISION / VERIFIED: тестировать20OK; «Полный поиск через
интерфейс системы»; сначала owner оценка качества, затем решение о performance.

План-контракт: read-only freeze20OK/112regions/336vectors и inputs/artifacts →
отдельный immutable тестовый каталог20 с собственной identity, без изменения
BUILDING100/activepointer → переиспользовать core search/HTTP I/native embedding,
query runner/существующий UI и private owner annotations → TDD/самопроверка/один
независимый reviewer → model-free bootstrap loopback UI → владелец делает запросы.
Новые catalogML/build/оптимизация/телеметрияGPU в эту задачу не входят.

20 из списка100:001–010,012–018,020–022. Номера сохранены, фото011NO_NAILS и019ERROR
не входят в тест20; сами100list/Sheetsmarkers/исходные674 сохраняются.
Проверено20sourceSHA и112mask/crop artifacts, без ML. Успех этих20 не качество всего100.

Тестовый каталог: только20OK с полным набором3models для каждой области;
immutable snapshot из G5target, private700/600, hash pin и canonical identity.
read_ready относится только к завершённому subset20; READY100/SQLpublish не имитируются.
Никаких writes/sourceDB/activepointer/publish. Ответы owner сохраняются privately.

UI работает на127.0.0.1. Один manualquery session ≤20поданныхфото из exact allowlist,
≤623admissions (20×31+3), ≤3600s, без agentMLqueries/auto retry.
Текущие maxregions10/40MiB/source20MiB/pixels2359296/MPSfloat32/solver16384,
pressure1/2allowed4STOP/RSS6+5/combined10GiB/storage32/free16GiB сохраняются.
Это разрешённая владельцем manual подготовка/сессия, не бесконечный сервис.
При hardSTOP результаты owner и каталог сохраняются; перезапуск отдельно.

Проверка: snapshot rejected при неполноте/неверных models/identity; foreignupload
отклоняется до ML, лимит20 запросныхфото; private annotation write без БД;
существующий web flow fakeML/synthetic; bootstrap health без Torch/modelcalls.
Нельзя заявлять качество по synthetic/selfmatch/наличию UI. Owner критерии/вердикт
в [методике](manual-validation.md); performance пока отложен.
Clean Architecturemini: static testcatalog как внешний read-only port; core не меняется.

Read-only source уточнение:19nails/1temporarytattoos(008). Не расширять категорию
бизнес-разметки; отдельно owner замечание008. Scope20/search сохранён.


## Предлагаемое исправление загрузки — 2026-10-11

DRAFT_PROPOSAL, пока не разрешает новую ML-сессию. Пользователю нужны новые фото
с ВБ и скриншоты для проверки полного поиска. Exact allowlist запросов мешает
этому сценарию: catalog20 и query inputs ошибочно получили общую границу.

Предлагается оставить неизменным каталог20, но принимать новые запросные PNG/JPEG/WebP
после проверки декодирования, размера и числа пикселей. Убрать только сопоставление
запросного SHA с каталогом; проверку целостности перед обработкой сохранить.
Сделать причины отказа понятными пользователю. Сохранить предел20 поданных фото,
623 admissions, 3600 секунд и все resource STOP. Изменение требует нового pinned
пакета и отдельной ограниченной ручной сессии; живой процесс не править.

До запуска: regression tests на новое фото вне catalog20 и неверные изображения,
проверка фактической поддержки WebP декодером, независимое read-only review.
Исходный каталог не перестраивать; performance остаётся отложенным.


## Разрешённое исправление — 2026-10-11

OWNER_DECISION / VERIFIED: владелец ответил «Да» на исправление загрузки и запуск
обновлённого тестового стенда. Новый запросный PNG/JPEG/WebP может отсутствовать
в catalog20. План-контракт: остановить только own session → regression RED →
минимальная правка query admission/UI → GREEN и read-only reviewer → новый freeze
и one-shot manual window20/623/3600s → открыть интерфейс владельцу. SHA целостности
и все прежние resource STOP сохраняются; performance и catalog build не входят.
Эта секция заменяет exact query allowlist в исходном контракте, не каталог20.
