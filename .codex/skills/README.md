# Локальные навыки проекта

## `diagram-design`

Точка входа `.codex/skills/diagram-design` — символическая ссылка на `vendor/diagram-design/skills/diagram-design`. Исходный репозиторий подключён Git submodule и не устанавливается в глобальный `$CODEX_HOME/skills`.

Текущая версия определяется gitlink `vendor/diagram-design`. После чистого клона сначала инициализируйте submodule; затем используйте контролируемое обновление:

```sh
git submodule update --init --recursive
git submodule status vendor/diagram-design
git submodule update --remote vendor/diagram-design
```

После обновления проверьте `SKILL.md`, релевантные шаблоны и diff gitlink перед коммитом.

## `sa-infostyle`

Локальный навык `.codex/skills/sa-infostyle` помогает писать и редактировать русскоязычные документы системного анализа ясным, проверяемым языком. Он улучшает форму и различает факты, решения, гипотезы и открытые вопросы, но не заменяет анализ предметной области или решение владельца.

## `humanizer-ru`

Локальная копия [Vladimir-Human/humanizer-ru](https://github.com/Vladimir-Human/humanizer-ru) в `.codex/skills/humanizer-ru`. Навык предназначен для явной редакторской просьбы сделать русскоязычный текст естественнее; он не должен подменять анализ фактов, терминологию или правила доказательности в аналитических артефактах.
