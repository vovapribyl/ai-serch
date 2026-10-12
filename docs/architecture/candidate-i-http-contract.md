# HTTP-контракт подключения Candidate I

| Поле | Значение |
|---|---|
| Версия / дата | v0.1 / 2026-10-07 |
| Статус | `APPROVED_BY_OWNER`, 2026-10-07: «Утверждаю контракт» в текущем диалоге; реализация и runtime NOT_RUN |
| Принято владельцем | Отдельный HTTP-сервис I в своём окружении; передача изображения непосредственно в POST |
| Утверждено в контракте v0.1 | Синхронный вызов на одно фото, multipart/PNG, JSON/PNG-маски, точные поля и ошибки, правила занятости и identity |
| Входы | [HLD](nail-search-hld.md), [LLD](nail-search-lld.md), [план Mac](mac-common-environment-plan.md) |
| Машиночитаемая схема | [OpenAPI 3.1](candidate-i-http.openapi.json) |
| Маршрут | FULL: план-контракт → автор и self-check → один read-only reviewer → исправления → утверждение готового результата |

## 1. Простыми словами и план-контракт

Основная система уже получила нормализованные RGB-пиксели. HTTP-адаптер упаковывает их в PNG и отправляет сервису I. Сервис вызывает существующий LangSAMAdapter, возвращает маски, координаты и явный исход. Адаптер проверяет ответ и создаёт обычные данные ядра. Ни HTTP, ни Pillow, ни SDK в ядро не попадают.

План-контракт: сохранить принятые решения и продуктовые правила → описать точный wire format и mapping порта → раскрыть identity, отказы, timeout и ресурсы → синхронизировать HLD/LLD/схемы/план и выбранные статусы анализа → проверить ссылки, schemas и инварианты → независимый reviewer → предъявить результат. Код, установка библиотек, загрузка моделей, миграции, данные, публикация и inference не входят в задачу.

Сервис обслуживает только выделение Candidate I. Crops формирует NailImageProcessor; embedding и поиск выполняет основная система. Получение изображения по URL/пути, SQL-доступ I, jobs/очередь, J, пользователи, Sheets, VM/интернет и универсальная категорийная модель — `DEFERRED`, не endpoints этого API.

## 2. Операции и доверенная граница

| Операция | Назначение |
|---|---|
| `POST /v1/localizations` | Один синхронный вызов выделения одного фото |
| `GET /health/ready` | Снимок готовности и actual identity без распознавания фото |

Первая площадка — loopback на одном Mac, один процесс сервиса и один inference executor. Endpoint задаётся внешней конфигурацией; клиент не следует redirects. Это доверенный локальный контур, не публичный API: loopback не является проверкой личности клиента. Интернет-доступ и пользовательская авторизация не проектируются.

## 3. Запрос POST

`Content-Type: multipart/form-data`; ровно две части, без дополнительных files/form fields. Image-файл имеет техническое имя `image.png`, личное имя исходного файла не передаётся.

| Часть | Формат | Правило |
|---|---|---|
| `image` | `image/png`, binary | Один PNG RGB8 без alpha и EXIF; PNG без потерь; ровно один кадр |
| `metadata` | UTF-8 JSON-текст, part `application/json` | Строгая LocalizationMetadata-схема; это поле multipart, не второе JSON-тело запроса |

| Поле metadata | Тип / ограничение | Смысл |
|---|---|---|
| `api_version` | integer, ровно `1` | Версия семантики wire-контракта |
| `request_id` | UUID в каноническом lower-case формате | Новый opaque ID для каждого вызова; correlation, не idempotency key |
| `expected_extractor_fingerprint` | 64 lower-case hex | Ожидаемая identity сервиса I |
| `image_sha256` | 64 lower-case hex | SHA-256 точных переданных PNG-байтов |
| `width`, `height` | positive integers | Размер уже нормализованного кадра |

Все поля обязательны, unknown fields запрещены; parser запрещает duplicate JSON keys и non-finite числа. Профили, пути, пороги, device и URL не принимаются из запроса. Сервис использует один заранее закреплённый профиль; другой expected fingerprint отклоняется до inference.

Утверждённые транспортные caps: PNG до `20 MiB`, metadata до `8 KiB` UTF-8, весь multipart body до `20 MiB + 64 KiB`; лимит считается по реально прочитанным байтам, не только Content-Length. Это принятые ограничения wire-контракта; значения memory/deadline/decoded-pixel/region/solver parameters всё ещё готовятся в runtime bill. Нормализованный PNG может быть больше исходного JPEG; проверка исходного upload не заменяет проверку этого cap.

Сервис сначала проверяет admission/готовность, bounded multipart, SHA-256 и decode: PNG RGB8, один кадр, отсутствие EXIF/alpha, размеры совпадают с metadata и проходят runtime pixel cap. Повторная EXIF-нормализация, resizing или JPEG-перекодирование запрещены. При отказе модель не вызывается. Original input SHA-256 из PhotoInput сохраняется основной системой отдельно и не заменяется checksum этого PNG.

## 4. Ответ 200 и система координат

JSON содержит только обязательные поля, определённые в OpenAPI. Контрактная версия, request_id и image_sha256 совпадают с запросом; extractor_fingerprint берётся из фактического закреплённого состава сервиса, а не копируется из expected поля. Width/height совпадают с нормализованным входом.

| Поле | Формат |
|---|---|
| `api_version`, `request_id`, `image_sha256`, `extractor_fingerprint` | Identity ответа |
| `status` | `OK` или `NO_NAILS` |
| `image` | Объект с обязательными positive width/height |
| `regions` | Упорядоченный массив Region; при OK непустой, при NO_NAILS пустой |

Region: `ordinal` (1..N без пропусков), `label` (непустой текст), `confidence` (finite [0,1]), `detector_box_xyxy` (четыре finite числа), `mask_png_base64` (строгий RFC 4648 Base64 со стандартным алфавитом и padding).

Detector box `[x0,y0,x1,y1]`: начало координат слева сверху, X вправо, Y вниз, `0 <= x0 < x1 <= width`, `0 <= y0 < y1 <= height`; непрерывные координаты границ, не индексы пикселей. Маска — PNG grayscale8, без alpha/EXIF, размер полного нормализованного кадра, pixels только 0/255 и хотя бы один 255. Обрезка по ненулевым mask pixels вычисляется ядром с half-open правой/нижней границей; detector box не подменяет mask bbox. Профиль фиксирует detection order из LLD, ordinal следует ему, confidence не применяется как новый фильтр.

До публикации OK сервис проверяет все области и полный размер ответа. Нарушение любого region → технический отказ всего фото, без частичного OK. HTTP-адаптер повторяет проверку после bounded чтения ответа, строгого JSON и Base64/PNG decode. OpenAPI описывает структуру; pixel contents, checksum, bbox относительно image и ordinal sequence требуют семантической проверки, они не доказываются одной JSON Schema.

`SUCCESS` валидного existing результата I → OK. Только `LOCALIZATION_FAILED / DETECTOR_NO_MATCH` → NO_NAILS. SEGMENTER_EMPTY, unexpected exception, invalid mask и resource failure не преобразуются в NO_NAILS. NO_NAILS относится к одному фото и не означает «товара нет в корпусе».

## 5. Ошибки и mapping

Ответ ошибки — `application/problem+json` по RFC 9457: `type=about:blank`, `title` соответствует HTTP-статусу, `status`, безопасный `detail`, стабильный `code`, `request_id`. Если metadata ещё не разобраны, service создаёт собственный correlation UUID. Нет paths, stack trace, pixel data, runtime secrets и weights/config dumps.

| HTTP | code | Причина |
|---|---|---|
| 400 | `INVALID_REQUEST` | Повреждённый multipart/JSON, duplicate keys, не две требуемые части |
| 413 | `PAYLOAD_TOO_LARGE` | Превышен transport cap |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | Не multipart/PNG или другой part media type |
| 422 | `INVALID_IMAGE` или `INVALID_METADATA` | Decode/размеры/checksum/normalized image либо схема metadata невалидны |
| 409 | `PROFILE_MISMATCH` | Valid expected fingerprint отличается от actual |
| 503 | `BUSY`, `MODEL_NOT_READY` или `RESOURCE_ERROR` | Admission/device lease заняты, профиль не готов, ресурсный отказ |
| 500 | `MODEL_ERROR`, `INVALID_MODEL_OUTPUT` или `SEGMENTER_EMPTY` | Технический отказ I или нарушение ответа |

HTTP adapter переводит 409 в NailProcessingError(PROFILE_MISMATCH), BUSY/RESOURCE_ERROR сохраняет, MODEL_NOT_READY → MODEL_ERROR; INVALID_MODEL_OUTPUT/повреждённый ответ → INVALID_OUTPUT; MODEL_ERROR/SEGMENTER_EMPTY сохраняет technical semantics. Invalid input → INVALID_IMAGE. Transport failures → MODEL_ERROR с безопасной внутренней причиной `CONNECTION_FAILED`/`LOCALIZATION_TIMEOUT`; не NO_NAILS. Неизвестный статус/code, mismatch HTTP/body.status, лишние JSON fields, чужая identity → технический отказ. Публичный `/search` использует собственный mapping LLD §11 и не проксирует internal problem тело целиком.

Retry-After можно вернуть при известной безопасной оценке ожидания; значение не выдумывается. Клиент v1 не повторяет POST автоматически даже при наличии Retry-After. GET readiness не используется как гарантия, что последующий POST будет принят.

## 6. Readiness и fingerprint

200 ready: `api_version=1`, `ready=true`, `busy` boolean, actual `extractor_fingerprint`. 503 — Problem(MODEL_NOT_READY) с `ready=false` extension. Busy inference может сосуществовать с ready=true: readiness сообщает наличие подготовленного профиля, admission решает отдельно и может дать BUSY.

Extractor fingerprint = SHA-256 canonical JSON identity: exact I code revision, полный I-service lock hash, revisions/manifests моделей, hash frozen localization config, preprocessing/mapper semantics, выбранные device/dtype/backend/operator-fallback options и hash полного принятого I-service runtime профиля с finite limits/lifecycle. Filesystem paths и secrets не входят в public identity. Service bootstrap проверяет actual inventory; одной строкой fingerprint без этой проверки нельзя подтвердить готовность. Main runtime_profile закрепляет свой состав, I-service identity и принятую transport/crop/numeric semantics; representation_fingerprint включает их. Замена окружения/модели не является незаметным обновлением READY representation.

Readiness не загружает модели и не выполняет model calls; bootstrap/load — отдельно разрешённая операция. После изменения закреплённого состояния или сбоя процесса ready сбрасывается. Фактические fingerprints и lock I-service пока `UNKNOWN`; existing I runtime не переписывается, новый сервис требует bill новых HTTP-зависимостей.

## 7. Занятость, deadline и общий ресурс Mac

Один in-flight inference, non-blocking admission без накопления очереди. Native ML работает в выделенном executor, не блокирует HTTP event loop/health. Сервис держит собственную admission lease до фактического завершения задания, включая exception и потерю клиента. Client disconnect не освобождает занятую модель.

Основное приложение имеет свой query lock. Для общих device операций существует одна межпроцессная file-lock lease во внешнем runtime root: сервис I захватывает её вокруг реального load/inference/unload, embedding-адаптер — вокруг своих model load/encode/unload операций. Основная система не держит эту device lease, пока ожидает HTTP I: иначе сервис не сможет получить её. Lease держит исполняющий процесс; при client timeout её нельзя освободить из backend. Это эксплуатационная техническая граница, не новый порт ядра. Batch и app по-прежнему не запускают подготовку одновременно; отдельная coordinator lease отлична от device lease, сервис I её не захватывает повторно.

Клиент задаёт конечные connect/write/read/overall deadlines из принятого профиля. Сервер не обещает принудительно прервать native inference по read timeout. При timeout весь новый search run не публикуется; предыдущая выдача/разметка сохраняется, stale finalize запрещён. Поздний ответ не дописывается в отменённую сессию. Зависший I перезапускается явно после остановки процесса; его restart не удаляет БД, каталог или durable evidence. Автоматических retry, job-store и результата по request_id нет.

Сервис не сохраняет исходные фото, маски и ответы на диск и не кэширует их между запросами. Входы/outputs находятся в restricted памяти задания; framework spool, если понадобится, использует отдельный private namespace и гарантированный cleanup, а не произвольный системный каталог. Веса/locks — внешние постоянные inputs. Логи: request_id, безопасный code, длительность/счётчики; raw bodies и mask Base64 запрещены.

На Mac владелец вручную ограничивает фото размером ранее испытанных; точные исторические размеры не объявлены установленными. `max_decoded_pixels`, `max_region_count`, `max_response_bytes`, connect/write/read/overall deadlines и solver budget пока `UNKNOWN`. Их положительные конечные значения нужны в утверждённом runtime bill до model-backed старта; ручной контроль фото не задаёт их численно. Можно писать fake/contract tests без настоящих моделей, подставив явные тестовые limits. Новая универсальная система stress/load testing не вводится.

## 8. Проверки — NOT_RUN

| Группа | Существенные проверки |
|---|---|
| Wire request | PNG round-trip сохраняет RGB bytes; checksum PNG отдельно от original; строгие fields/duplicate keys/part count/media types/byte limits |
| Result | OK непустой и NO_NAILS пустой; правильная identity; full-frame mask 0/255, bbox, ordinal; любой invalid region отклоняет всё фото |
| Errors | Все HTTP/code пары, unknown status/code, SEGMENTER_EMPTY, malformed/truncated/oversized answer не становятся NO_NAILS |
| Timeout | POST не повторяется; client cancel не освобождает service/device lease; поздний ответ не создаёт run; после окончания можно принять следующий запрос |
| Resources | Общая device lease между I и embeddings, отсутствие deadlock на HTTP boundary; BUSY без очереди; coordinator lease app/batch; cleanup exception/restart |
| Identity | Ready/profile mismatch до inference; actual lock/models/device проверены; изменение identity требует нового представления |

Contract tests используют synthetic PNG/маски и fake HTTP/I, TDD по [методу](../development-method.md). Реальный I, embedding smoke, ресурсные пробы и данные — отдельно разрешённые операции по [плану Mac](mac-common-environment-plan.md). Эти проверки не доказывают качество top-10.

## 9. Основания и статус

Book-guidance: APoSD mini — HTTP/кодирование/ошибки скрыты за semantic localize; Clean Architecture mini дополнительно — порты принадлежат приложению, transport снаружи; commit `893a88a6fce3a80c565bf39ac65021b43a8b2990`. Ponytail — одна операция на фото, без speculative jobs/plugins/backlog-сервисов.

[FastAPI multipart](https://fastapi.tiangolo.com/tutorial/request-forms-and-files/) обосновывает передачу файла и metadata form field; [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html) — HTTP semantics и осторожность автоматического повторного POST; [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html) — machine-readable ошибки. Конкретные PNG, поля, codes и deadlines — решения этого проекта, а не предписания стандартов.

Self-check/review текущего пакета фиксируется в [отчёте](nail-search-documents-review.md). Schema parsing и review не означают существующий сервис или совместимость runtime. Owner approval контракта v0.1 получено отдельно 2026-10-07; numerical runtime parameters остаются UNKNOWN и не заменяются этим утверждением.
