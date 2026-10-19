# Исправление чтения каталожного экспорта

2026-10-17. **IMPLEMENTED_MODEL_FREE_VERIFIED**. Маршрут STANDARD: исправление
дефекта [разрешённой пробы](deferred-photo-probe-package.md#фактический-результат-разрешённого-запуска).
Нового ML, PostgreSQL-контура, START или повторного исполнения старого пакета нет.

## Причина и исправление

Сохранённый каталог имеет размер 209 337 bytes. export_deferred_batch,
терминальный отчёт и замороженный runner читали его через private_json,
предназначенный по умолчанию для CLI-дескрипторов до 65 536 bytes.
Отказ возникал после успешного экспорта. Список отложенных фото также мог
превысить этот предел: его writer уже допускает до 2 MiB.

- В [private_json](../../src/product_search/infrastructure/replenishment_cli.py)
  добавлен явный положительный целочисленный max_bytes. Значение по умолчанию
  по-прежнему 65 536: управляющие файлы, grants, IPC и telemetry не получают
  увеличенный предел автоматически. Размер проверяется и до чтения, и после
  bounded read, включая рост файла после stat.
- [read_catalog_export](../../src/product_search/infrastructure/replenishment_diagnostic_export.py)
  предназначен для каталожных экспортов до 40 MiB. Это конечный предел файла,
  а не изменение ресурсных caps ML или размера IPC-сообщений. Превышение
  приводит к отказу; готовность будущего полного корпуса этим не доказана.
- [Exporter и report CLI](../../src/product_search/infrastructure/replenishment_deferred_photos.py)
  используют этот reader для каталога, а для deferred list — предел 2 MiB,
  общий с writer. Права 700/600, владелец, отказ для symlink/hardlink,
  строгий JSON без повторных ключей и NaN/Infinity остаются общими проверками.
- Новые внешние runner должны читать векторный экспорт через read_catalog_export.
  Замороженный runner израсходованного пакета не редактировался; его FAILED
  не заменяется на PASS задним числом. Его verifier проверен отдельно с новым reader.

## Проверки

[Регрессионные тесты](../../tests/test_replenishment_export_reader.py): сначала
два поведенческих RED — отказ exporter и отчёта на каталоге/списке больше 64 KiB;
затем GREEN. Новые 19 проверок покрывают большой экспорт и список, прежний cap
дескрипторов, отдельные конечные caps, права/ссылки/JSON, неправильный max_bytes
и рост файла после stat.

Итого **165 выбранных model-free проверок PASS** в двух непересекающихся
выборках: 101 проверка exporter/CLI/deferred/runtime-binding и 64 проверки
host/monitor/worker/native-job. Известный Starlette/httpx warning остаётся.
Полный suite не запускался: SQL-fixtures и известный missing fake-server fixture
не включены в эту проверку. В первой выборке фильтр по имени ошибочно захватил
две SQL-fixture; sandbox отказал до создания БД. Они исключены из повторной
выборки, Unix-socket tests прошли с разрешённым доступом. Это не GREEN первой попытки.
Ruff check/format и git diff --check прошли.

## Воспроизведение на сохранённых данных

Приватный replay: `artifacts/corpus-replenishment/export-reader-fix-20261017/`.
Исходный экспорт прочитан новым reader; его photos/outcomes/regions/vectors
перенесены в SQLite в памяти, затем обработаны настоящим export_deferred_batch.
После нового экспорта те же поля и profile совпали с сохранённым результатом:
один deferred, один ready, 8 областей, 24 вектора. Это replay SQL-запросов,
не проверка нового PostgreSQL/runtime-пути.

Настоящий scripts/report_replenishment_batch.py завершился с exit 0 и PASS
на исходном файле 209 337 bytes. Frozen verifier также принял сохранённые
результаты, прочитанные через новый reader. Идентификаторы в вывод не внесены.
Прежний private_json без max_bytes продолжает отклонять этот файл.
SHA исходного экспорта, deferred list, подписанных runner/manifest, экспорта20
и 58 прежних файлов не изменились. Модельные SDK не импортировались.

Следующий возможный шаг — подготовка нового ограниченного runtime-пакета с
актуальными code pins и новым reader. Это исправление не даёт допуска к ML,
оставшимся75, каталогу100 или рабочему cutover. Независимое review не проводилось.
