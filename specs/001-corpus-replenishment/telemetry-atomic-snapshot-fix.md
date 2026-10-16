# Чтение телеметрии при атомарной замене файла

> Последующая runtime-проверка: [два запроса прошли после исправления](../corpus-optimization/remaining-quality-report.md).
> Указания «ML не выполнялся» ниже описывают этап подготовки самого исправления.

2026-10-15. STANDARD. Найдено при [семи запросах качества](../corpus-optimization/staged-quality-seven-report.md).
Runtime остановился с TELEMETRY_READ/OBSERVATION_FAILED/OTHER, sample_current=false.
Последний успешный pressure1 нельзя считать измерением в момент отказа.

## Воспроизводимый дефект

Worker публикует telemetry.json через запись временного файла и os.replace.
Reader сначала открываетfd, затем проверяетfstat. Если замена случилась между
этими действиями, открытый старый inode получаетst_nlink=0: его целые байты
доступны, но private_json отклонял их из-за требования одной ссылки.

Детерминированный тест выполняет настоящийos.replace ровно послеopen доfstat;
он подтвердилnlink0 и ошибочныйSTOP для целого свежего сообщения.
В старом runtime-журнале нетfstat/errno: эта гонка объясняет такой класс отказа,
но **точная причина конкретного исторического STOP остаётся UNKNOWN**.
Нельзя объявлять его OOM, criticalpressure или доказанным превышением лимита.

## Исправление и границы

private_json получил opt-inatomic_snapshot. Он разрешаетnlink0 только для
уже открытого authenticated regular descriptor, когда этот режим явно выбран.
Только MacResourceObserver выбирает его для mutabletelemetry. Обычные immutable
control/grant readers сохраняютnlink1. Никакого повторного чтения, ожидания
или подстановки прежнего last_sample после ошибки нет.

O_NOFOLLOW, ownerUID, directory700/file600, предел размера, строгий JSON,
запрет hardlinks>1, workerPID/nonce/MPS/type/freshness и guards прежние.
Старое сообщение проверяется по собственному observed_at: замена на свежий
файл не делает открытое старое сообщение свежим. Недоступный/повреждённый
файл и устаревшее/чужое сообщение по-прежнему даютSTOP.

Выбран APoSDmini (источник893a88a6): деталь жизни файлового descriptor скрыта
в reader; domain/модельный код не меняются. Редкий режим явный только у
телеметрии, а не глобальное ослабление control-reader. Ponytail: standardlib,
без брокера/нового сервиса/retry-цикла. Книги не доказывают эффект исправления.

## Проверки

Два ожидаемых RED: свежий descriptor возвращалSTOP вместоOK, а устаревший
останавливался наREAD вместоFRESHNESS. Два защитных случая уже проходили:
immutablecontrol отклоняет unlinkedfd, telemetry отклоняетhardlink.
После исправления: **135релевантных тестов PASS/0FAIL/0ERROR**, включая CLI,
resource binding, worker binding, stage payloads, monitor и diagnostics;
2existing bounded syntheticDB cases и собственные Unix sockets. Один известный
Starlette/httpx deprecation warning. Ruff/format PASS.

Первый расширенный запуск внутриsandbox дал3socketFAIL и2DBsetupERROR;
после разрешённого доступа к собственным local fixtures и короткогоbasetemp
тот же набор прошёл без дополнительных правок продукта. Это не полный suite.

**Новый ML-прогон после исправления не выполнялся.** Все ранее выданные
пакеты закрепляли код до исправления; их нельзя переиспользовать.
Существующие runtime результаты/STOP не переписывались. Independentreview
не проводилось; commit/push/merge отсутствуют.
