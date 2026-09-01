#!/usr/bin/env sh
set -eu

runtime_env_file=${1:?Передайте путь к runtime-env файлу.}
case "$runtime_env_file" in
  /*) ;;
  *) echo "Runtime-env файл должен быть задан абсолютным путём." >&2; exit 1 ;;
esac

if [ ! -f "$runtime_env_file" ]; then
  echo "Runtime-env файл не найден." >&2
  exit 1
fi

if [ -L "$runtime_env_file" ]; then
  echo "Runtime-env файл не может быть символической ссылкой." >&2
  exit 1
fi

repository_root=$(cd "$(dirname "$0")/.." && pwd -P)
resolved_env_file=$(cd "$(dirname "$runtime_env_file")" && pwd -P)/$(basename "$runtime_env_file")
case "$resolved_env_file" in
  "$repository_root"|"$repository_root"/*)
    echo "Runtime-env файл не может находиться внутри репозитория." >&2
    exit 1
    ;;
esac

if [ "$(stat -f %u "$resolved_env_file")" != "$(id -u)" ]; then
  echo "Runtime-env файл должен принадлежать текущей учётной записи." >&2
  exit 1
fi

if [ "$(stat -f %Lp "$resolved_env_file")" != "600" ]; then
  echo "Runtime-env файл должен иметь права 600." >&2
  exit 1
fi
