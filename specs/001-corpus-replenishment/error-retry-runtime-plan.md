# Пакет ошибок фото и публикации: план исполнения

Итог: **EXECUTED / OK**. Все пять фаз выполнены; [результаты и ограничения](error-retry-runtime-report.md). Ниже сохранён план до исполнения.

Дата:2026-10-15. STANDARD, пакетный допуск владельца «Разрешаю» после предъявления состава. Промежуточные разрешения не запрашиваются. Рабочие данные не затрагиваются.

Одна собственная временная PostgreSQL, прежний закреплённый image512MiB/1CPU/128PID/tmpfs256MiB/localhost; одна тяжёлая стадия одновременно. Предел контура2520с,1200с/package, не более5выбранных фото и24admissions на ML-пакет, RSS/MPS6GiB/encoder5GiB, прежние freshness/HTTP/DB/cleanup. Native worker teardown и межфазное absence подтверждаются перед каждым новым грантом. Источники и полные команды/UUID сохраняются private.

## Сценарии

1. START одного товара с четырьмя выбранными фото: два намеренно повреждённых файла, один ранее успешный реальный input и один созданный для теста белыйPNG256×256. Повреждённое фото стоит первым: ошибка не должна блокировать независимое корректное. Ожидаем ERROR/OK/NO_NAILS/ERROR, publication1. Белый фон не изображает ногти по построению; если модель выделит области, это FAIL отрицательного сценария, а не принудительная замена результата наNO_NAILS.
2. RETRY_PHOTO только первой ошибки в новой редакции; второй ERROR и готовые/NO_NAILS фото не повторяются. Повреждённые байты намеренно не исправляются: повтор должен остаться ERROR, это проверка выбора и изоляции, не восстановления содержимого. Пригодные результаты переиспользуются; старая публикация сохранена, новая current revision публикуется один раз.
3. START второго независимого товара с одним ранее успешным фото. Только в собственной БД устанавливается обратимый BEFORE INSERT trigger на catalog_snapshots с SQLSTATE23514. Ожидаем publication FAILED при сохранённых READY/ML результатах; старый active snapshot первого товара не меняется.
4. После удаления только тестового trigger/function RETRY_PUBLICATION второго товара: без ML/worker, новый SUCCEEDED receipt, активный каталог содержит оба товара. Checkpoints/files/vector values не пересчитываются.
5. Ещё одна заранее запланированная RETRY_PUBLICATION уже успешной редакции с новым грантом: нет нового snapshot/publication и нет ML. Это явная проверка идемпотентности, не автоматический повтор ошибки.

Пакеты замораживаются до исполнения; retry revision/photo/head и receipt references берутся из фактического SQL состояния. Каждый этап получает отдельный grant в рамках общего допуска. При safety failure контур закрывается; при несовпадении отдельного ожидаемого исхода сохраняется FAIL, независимые проверки могут продолжиться. После завершения own processes/DB/socket/secrets удаляются, evidence остаются.

## Выявленный до ML дефект

Malformed source при сохранённых SHA/байтах приводил к BuildStop всего native запуска. RED-тест подтвердил дефект перевода декодирования. Добавлен отдельный SourceImageDecodeError как subtype старого BuildStop: legacy поведение сохранено, native driver переводит только его в PhotoProcessingError(INVALID_IMAGE). Hash/path/size/shared-storage ошибки остаются terminal. Это реализация FR-037/038 во внешнем адаптере, core DTO и критерии не меняются. Book-guidance/Clean Architecture: перевод деталей остаётся снаружи. Все runtime fingerprints обновляются после исправления.

План не доказывает качество реальных негативных фото на разных фонах: один синтетический белыйPNG — ограниченный smoke-case. Нового production cutover/установки dependencies/повышения лимитов/commit/push/merge нет.

## Зафиксированные пакеты исполнения

- S / START / 24 admissions: `192370ad9ce99b03a712c8836fe7ed9f16e4f9f196bcadaaa6850c03481d1b97`.
- T / RETRY_PHOTO / 24 admissions: `0b028ed56bde8ec2846ccf3390a553e979bf962916fc404d7d228f47c1814aff`.
- F / START / 24 admissions: `1a5962e4298126b03212fae789d87f702d8da6ea626fd01fd1cd2e23b24b7cc3`.
- P / RETRY_PUBLICATION / 1 admissions: `3f118ec8a87662204fa7b6a863cbaf46c1b0946800c4c90b1b18ed3b44d82810`.
- I / RETRY_PUBLICATION / 1 admissions: `d834e12b5286bfcb64c0bf9c9832eb36d50c7e4768f035bf60812014da7e224c`.

Code/input/permissions всех пяти пакетов проверены;5metadata assemblies и15actual entrypoint refusals прошли без SDK. Полная регрессия пополнения510passed; выбранные image-store/build/payload тесты65passed, с пересечением случаев. Проверки проведены до grants/DB/ML.
