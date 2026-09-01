#!/usr/bin/env sh
set -eu

for forbidden_path in .env data runtime artifacts models reports; do
  if git ls-files --error-unmatch "$forbidden_path" >/dev/null 2>&1; then
    echo "Запрещённый рабочий путь отслеживается Git: $forbidden_path" >&2
    exit 1
  fi
done

if git ls-files | grep -E '(^|/).+\.(jpg|jpeg|png|webp|xlsx|pt|pth|onnx|safetensors)$' >/dev/null; then
  echo "В поставке обнаружен файл корпуса, изображения или веса модели." >&2
  exit 1
fi

echo "Поставка не содержит корпуса, изображений, отчётов или весов моделей."
