workspace "Поиск по ногтям — порты и адаптеры" "TO-BE, не runtime evidence" {
    model {
        system = softwareSystem "Поиск товаров" "Локальный контур" {
            app = container "Основное приложение" "Backend процесс Mac; I отдельно, CLI взаимоисключён с app" "Python" {
                web = component "Web и CLI" "Входные адаптеры" "HTTP / CLI"
                usecases = component "Сценарии приложения" "Search, build и finalize; plain DTO" "Ядро"
                processor = component "Подготовка фото" "Единая политика masks/crops" "NailImageProcessor"
                matcher = component "Сопоставление" "Чистая формула и solver" "match_nail_sets"
                locport = component "Порт выделения" "Контракт принадлежит ядру" "NailLocalizationPort" {
                    tags "Port"
                }
                embport = component "Порт embeddings" "Контракт принадлежит ядру" "NailEmbeddingPort" {
                    tags "Port"
                }
                imageport = component "Порт изображений" "Opaque refs, RGB и производные" "NailImageStorePort"
                catalogport = component "Порт каталога" "Read / build / publish" "NailCatalogPort"
                evalport = component "Порт evidence" "Атомарная финализация" "NailEvaluationPort"
                locadapter = component "HTTP-адаптер Candidate I" "Multipart/PNG и JSON mapping в DTO ядра" "HttpNailLocalizationAdapter"
                embadapter = component "Адаптер трёх моделей" "Pillow и existing providers снаружи" "NailEmbeddingAdapter"
                fileadapter = component "Файловый адаптер" "Decode/EXIF/PNG, roots и permissions" "NailImageStoreAdapter"
                dbadapter = component "Адаптеры PostgreSQL" "Две роли: каталог и evidence" "NailRepository / EvaluationRepository"
                runtime = component "Сборка и runtime runner" "Backend wiring, две identities, query/device/coordinator leases" "main.py / runtime"
            }
            iservice = container "Отдельный сервис Candidate I" "Свои Python/lock/models; admission и shared device lease" "HTTP / LangSAM"
            db = container "Каталог и evidence" "Additive schema, legacy сохранён" "PostgreSQL / pgvector"
        }
        web -> usecases "Вызывает сценарий" "Plain DTO"
        usecases -> processor "Готовит фото" "Python"
        usecases -> matcher "Рассчитывает пары и рейтинг" "Python"
        usecases -> embport "Использует контракт" "Python"
        usecases -> catalogport "Использует контракт" "Python"
        usecases -> evalport "Использует контракт" "Python"
        processor -> locport "Использует контракт" "Python"
        processor -> imageport "Использует контракт" "Python"
        locadapter -> locport "Реализует контракт" "Protocol"
        locadapter -> iservice "Direct PNG POST; маски/исход" "HTTP"
        embadapter -> embport "Реализует контракт" "Protocol"
        fileadapter -> imageport "Реализует контракт" "Protocol"
        dbadapter -> catalogport "Реализует контракт" "Protocol"
        dbadapter -> evalport "Реализует контракт" "Protocol"
        dbadapter -> db "SQL и транзакции" "SQL"
        runtime -> usecases "Внедряет concrete adapters" "Python"
        runtime -> locadapter "Создаёт HTTP-клиент" "Python"
        runtime -> embadapter "Создаёт и управляет lifecycle" "Python"
    }
    views {
        component app "NailSearchOverview" {
            include web usecases processor matcher runtime
            autoLayout lr
            title "Ядро и входные сценарии — зависимости кода"
        }
        component app "NailSearchComponents" {
            include usecases processor locport embport locadapter embadapter iservice
            autoLayout lr
            title "ML-порты, адаптеры и внешняя HTTP-граница"
        }
        component app "NailSearchStorage" {
            include usecases processor imageport catalogport evalport fileadapter dbadapter db
            autoLayout lr
            title "Хранилища за портами — зависимости кода"
        }
        styles {
            element "Element" {
                background #ffffff
                color #263238
                stroke #90a4ae
                fontSize 20
            }
            element "Port" {
                background #e8f0fe
                stroke #2563eb
            }
            relationship "Relationship" {
                color #78909c
                thickness 1
                fontSize 16
            }
        }
    }
}
