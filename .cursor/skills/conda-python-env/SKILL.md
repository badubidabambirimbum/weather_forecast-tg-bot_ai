---
name: conda-python-env
description: Создает и настраивает виртуальное окружение Python через conda, включая проверку conda, создание env, активацию и установку зависимостей. Использовать при задачах про Python окружение, conda, env, venv, setup проекта и подготовку локальной среды разработки.
---

# Conda Python Env

## Quick Start

1. Проверить, что conda доступна:
   - `conda --version`
2. Создать окружение (по умолчанию Python 3.11):
   - `conda create -n <env_name> python=3.11 -y`
3. Активировать окружение:
   - `conda activate <env_name>`
4. Установить зависимости проекта:
   - если есть `environment.yml`: `conda env update -n <env_name> -f environment.yml`
   - иначе: `pip install -r requirements.txt`
5. Проверить интерпретатор:
   - `python --version`
   - `where python` (Windows) или `which python` (Linux/macOS)

## Краткий workflow для агента

- Уточни имя окружения, если пользователь его не дал (рекомендуй `project-env`).
- Если в проекте есть `environment.yml`, используй conda-способ установки в приоритете.
- Если conda-команды не работают, попроси пользователя инициализировать shell:
  - `conda init powershell` (для PowerShell), затем перезапустить терминал.
- После создания окружения предложи команду проверки:
  - `conda info --envs`

## Troubleshooting

- `conda: command not found`:
  - Проверь установку Miniconda/Anaconda и перезапусти терминал после `conda init`.
- Ошибки solve/dependency conflict:
  - Попробуй создать окружение с конкретной версией Python и без лишних пакетов, затем доустановить пакеты по частям.
- Активация не сработала в текущей сессии:
  - Выполни `conda init powershell` и открой новый терминал.
