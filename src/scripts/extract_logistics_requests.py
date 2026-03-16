#!/usr/bin/env python3
"""
CLI для пайплайна извлечения структурированных логистических заявок из индекса documents
и записи в logistics_requests_structured.

Запуск из каталога src (или PYTHONPATH=src из корня):
  python3 -m scripts.extract_logistics_requests [--limit N] [--force] [--filename FILE] [--dry-run]

Примеры:
  Один файл:            python3 -m scripts.extract_logistics_requests --filename "заявка.pdf"
  Первые 5 кандидатов:   python3 -m scripts.extract_logistics_requests --limit 5
  Все новые:            python3 -m scripts.extract_logistics_requests
  Все заново:           python3 -m scripts.extract_logistics_requests --force
  Dry-run:              python3 -m scripts.extract_logistics_requests --limit 2 --dry-run
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта в path для импортов
_src = Path(__file__).resolve().parent.parent
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

try:
    import httpx  # noqa: F401
except ModuleNotFoundError:
    print(
        "Ошибка: зависимости проекта не установлены для этого Python.\n"
        "Используйте виртуальное окружение (на системном Python pip может быть запрещён):\n"
        "  1) Создать:        python3 -m venv .venv\n"
        "  2) Активировать:  source .venv/bin/activate   (Linux/macOS)\n"
        "  3) Установить:    pip install -e .\n"
        "Затем снова запустите скрипт из каталога src.",
        file=sys.stderr,
    )
    sys.exit(1)

from config.settings import clients
from services.logistics_extraction_service import LogisticsExtractionService
from utils.logging_config import configure_from_env, get_logger

configure_from_env()
logger = get_logger(__name__)


async def main_async(
    limit: int | None,
    force: bool,
    filename: str | None,
    dry_run: bool,
) -> None:
    # Инициализация только OpenSearch (без Langflow)
    await clients.initialize_opensearch_only()
    if clients.opensearch is None:
        logger.error("OpenSearch не инициализирован")
        sys.exit(1)

    # LLM-клиент инициализируется лениво при первом обращении (в сервисе)
    service = LogisticsExtractionService(opensearch=clients.opensearch)

    if filename:
        candidates = await service.get_candidate_filenames(only_filename=filename)
        if not candidates:
            logger.warning("Файл не найден или не подходит под фильтр (PDF + ключевые слова)", filename=filename)
            sys.exit(0)
    else:
        candidates = await service.get_candidate_filenames(limit=limit)
        logger.info("Найдено кандидатов на логистические заявки", count=len(candidates))

    if not candidates:
        logger.info("Нет кандидатов для обработки")
        return

    success_count = 0
    skipped_count = 0
    failed_count = 0

    for i, fn in enumerate(candidates, start=1):
        logger.info("Обработка документа", index=i, total=len(candidates), filename=fn)
        result = await service.process_one(
            filename=fn,
            force=force,
            dry_run=dry_run,
        )
        status = result.get("status", "failed")
        err_cat = result.get("error_category")
        err_msg = result.get("error_message")

        if status == "success":
            success_count += 1
            logger.info("Extraction успешен", filename=fn)
        elif status == "skipped":
            skipped_count += 1
        else:
            failed_count += 1
            logger.warning(
                "Extraction завершился с ошибкой",
                filename=fn,
                error_category=err_cat,
                error_message=err_msg,
            )

    logger.info(
        "Batch завершён",
        total=len(candidates),
        success=success_count,
        skipped=skipped_count,
        failed=failed_count,
        dry_run=dry_run,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Извлечение структурированных логистических заявок из индекса documents в logistics_requests_structured",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Обработать только первые N файлов-кандидатов",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Переобработать даже уже сохранённые документы",
    )
    parser.add_argument(
        "--filename",
        type=str,
        default=None,
        metavar="FILE",
        help="Обработать только указанный файл (по имени)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Не писать в индекс, только логировать и выводить результат",
    )
    args = parser.parse_args()

    asyncio.run(
        main_async(
            limit=args.limit,
            force=args.force,
            filename=args.filename,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
