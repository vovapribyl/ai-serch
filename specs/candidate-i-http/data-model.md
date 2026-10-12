# Phase 1: данные и границы Candidate I HTTP

Дата: 2026-10-07. Extraction из [spec](spec.md), [контракта](../../docs/architecture/candidate-i-http-contract.md), [LLD §4](../../docs/architecture/nail-search-lld.md#4-внутренние-контракты). Не новое утверждение schema/миграций.

## Утверждённая wire-граница

| Данные | Поля / связи | Правило |
|---|---|---|
| Metadata | api_version/request_id/expected_extractor_fingerprint/image_sha256/width/height | Strict keys/types; PNG checksum отдельно от original |
| Response | Request identity → status/image/regions | OK непустой; NO_NAILS пустой; actual extractor |
| Region | ordinal/label/confidence/detector_box_xyxy/mask_png_base64 | Full-frame 0/255 grayscale8, nonempty mask, bbox в кадре, ordinal 1..N; любой invalid region — отказ фото |
| Problem | type/title/status/detail/code/request_id, ready extension | Known HTTP/code pairs, безопасные поля, error не NO_NAILS |
| Ready | api_version/ready/busy/extractor_fingerprint | Ready и busy различны; snapshot не гарантирует admission |

Exact types/constraints — в [OpenAPI](../../docs/architecture/candidate-i-http.openapi.json). Schema parsing не доказывает pixels/checksum/relative geometry semantics.

## Core DTO — проект LLD

| Данные | Связь / создатель |
|---|---|
| PhotoInput | Ordinal, opaque source_ref, original input SHA; входной сценарий/image-store |
| RgbImage/BinaryMask | Width/height/immutable bytes; image-store/validated HTTP adapter, без SDK |
| NailLocalization/LocalizedRegion | OK/NO_NAILS и tuple regions из HTTP client |
| ProcessedPhoto/RegionCrop | Source-frame mask и crop-frame RGB; ядро подготовки |
| PhotoEmbeddings/PairMatch | Три model vectors, region order, assignment/score; providers/matcher |
| SearchRequest/NailSearchExecution | Ordered inputs, representation/runtime identity, candidates/snapshot; orchestrator |

Minimal wire→core mapping рассматривается при review плана. Остальные DTO/signatures не становятся approved через эту таблицу. ArtifactRef internal; I получает bytes, не filesystem locator.

## Representation/evidence — поздний этап

LLD §9/12 задаёт proposed search_representations → catalog_photos → nail_regions → nail_embeddings, active pointer и evaluation evidence. Физические поля не переопределяются.

- BUILDING не читается запросом; READY после terminal outcomes/minimum OK/полных embeddings; publish отдельно разрешён.
- READY immutable, identity/corpus/ownership согласованы; rollback сохраняет старый corpus/evidence.
- Новый score не записан как legacy RRF; финальная evidence transaction атомарна.
- Отсутствие подготовленного фото товара — coverage issue, не правильный автоматический NEW.

## Состояния без job-store

UNREADY → READY после разрешённого bootstrap/actual inventory. BUSY может сосуществовать с READY. Actual completion/exception/exit освобождает admission/device; disconnect не делает native task свободным. Timeout не создаёт durable job/result по request_id.

Backend staged run: success → commit, failed/cancelled → без нового run. Добавление фото меняет input revision; старую выдачу не финализируют как новую. Successful rerun сбрасывает draft labels; failure сохраняет их до корректного run/отказа. Это planned policy LLD, не публичное состояние I API.
