# Большое фото: предложение по входам первого теста

2026-10-11. STANDARD: анализ и подготовка варианта без изменения входов или требований.
Статус способа обработки: APPROVED_BY_OWNER, ответ «разрешаю» 2026-10-11 на предложенную отдельную копию1536×1536 с сохранением674positions. Результат: [674inputs preparation PASS](oversize-input-report.md), без ML.

Владелец возобновил отложенный вопрос: «Давай займемся отложенной задачей».
Затем владелец разрешил рекомендованный способ; subset673 и повышение cap не выбраны.
Основания: [бэклог](tasks.md#бэклог), [измерение входов](build-preparation-report.md),
[текущие bindings](native-bindings-report.md).

## Факты и цель

673 фото прошли bounded decode. Одно фото имеет header1802×1802 (3247204pixels),
принятый cap2359296pixels соответствует1536×1536. Новое чтение или преобразование
restricted-фото в этой задаче не выполнялось; размеры взяты из preparation evidence.
Цель предложения — подготовить все674 позиции к первому изолированному тесту,
сохранив исходные фото, исходный manifest и действующий runtime limit.

## Варианты

| Вариант | Последствие | Рекомендация |
|---|---|---|
| Отдельная копия1536×1536 одного фото | Все674 позиции сохраняются; изменяется один input hash и профиль подготовки. Уменьшение может повлиять на мелкие детали | Предпочтительный вариант |
| Тестовый subset673 | Нет преобразования; требуется явно принять отсутствие одной позиции в тесте | Альтернатива |
| Повысить pixel cap | Сохраняются байты; требуется пересмотреть resource policy и подтвердить новое runtime поведение | Отдельная переоценка |

## Предлагаемая обработка и проверка

После выбора владельца — отдельный закрытый каталог вне Git: копии673 остальных
фото byte-identical, одно фото обработать offline. Преобразование: проверка original
SHA/формата/одного кадра и отдельного bounded preparation limit3247204pixels,
EXIF transpose, alpha composite на белый фон, RGB, LANCZOS1536×1536, PNG без metadata.
Это предложение для одноразовой подготовки известного входа, не изменение decode cap
продуктового pipeline. Оригинал не перезаписывать и не менять его права.

Новый frozen manifest связывает original SHA → transformed SHA, алгоритм/версию Pillow,
размеры и настройки; полные локаторы и product IDs только private. Отдельный input
profile/fingerprint отличает этот набор от исходного674 и proposed subset673.
Existing PhotoInput.input_sha256 должен указывать на фактические байты нового входа;
original SHA сохраняется отдельно в provenance, не подменяется transformed hash.

Проверка до ML: originals retained,673byte-identical,1transformed,674bounded decodeOK,
lineage/hashes/permissions PASS. Для утилиты — synthetic tests dimensions/orientation,
alpha/hashes/failure и отсутствие перезаписи; новый SDK не нужен. При ошибке STOP,
не исключать позицию автоматически. Достижение674decodeOK ещё не доказывает качество
локализации, coverage или готовность индекса.

## Граница следующего действия

На момент согласования копия, новый manifest/profile и code ещё не создавались. Model calls этим решением не разрешаются.
После выбора — реализация подготовки и независимое review по FULL перед зависимым
native execution package. Реальный build, query и READY/publish сохраняют свои gates.


## План-контракт исполнения

FULL: scoped offline preparation по утверждённому способу, без ML/DB/Git publication.
Исполнитель: новая небольшая утилита и synthetic TDD; новый private700root/600files,
674inputs с lineage и отдельным profile/hash, повторный decode/checkoriginals; safe
report и один independent read-only reviewer. После Critical/Major повторное review.
Старые bundles/snapshots сохраняются. Native worker/bill ещё отдельный результат;
никакое decodePASS не закрывает T051 и не разрешает dependent ML само по себе.
