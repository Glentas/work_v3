"""Запуск сервера системы распознавания языка.

Сервер поднимается на главном ПК и слушает все сетевые интерфейсы, поэтому
остальные машины локальной сети обращаются к нему по адресу
``http://<адрес-сервера>:<порт>``. При старте адреса печатаются в консоль.

    python run.py
    python run.py --port 8080
"""

from __future__ import annotations

import argparse
import logging
import socket

import uvicorn

from app import config


def lan_addresses() -> list[str]:
    """Локальные IPv4-адреса машины для подключения клиентов из сети."""
    addresses: list[str] = []
    try:
        # Пакет фактически не отправляется: приём используется только для
        # того, чтобы операционная система выбрала адрес нужного интерфейса.
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("10.255.255.255", 1))
            addresses.append(probe.getsockname()[0])
        finally:
            probe.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            candidate = info[4][0]
            if candidate not in addresses and not candidate.startswith("127."):
                addresses.append(candidate)
    except OSError:
        pass
    return addresses


def print_banner(host: str, port: int) -> None:
    print("\nСистема распознавания языка текста запущена.")
    print(f"  Локально:      http://127.0.0.1:{port}")
    for address in lan_addresses():
        print(f"  В сети:        http://{address}:{port}  <- адрес для других ПК")
    if host == "0.0.0.0":
        print("  Сервер слушает все интерфейсы (0.0.0.0).")
    else:
        print(f"  Сервер слушает только {host}.")
    print(f"  Коллекция:     {config.TEST_PATH}")
    print(f"  Тренировка:    {config.TRAIN_PATH}")
    print(f"  Модель:        {config.MODEL_PATH}")
    print("  Для остановки нажмите Ctrl+C.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Сервер распознавания языка текста")
    parser.add_argument("--host", default=config.APP_HOST, help="адрес интерфейса (по умолчанию 0.0.0.0)")
    parser.add_argument("--port", type=int, default=config.APP_PORT, help="порт (по умолчанию 8000)")
    parser.add_argument("--reload", action="store_true", help="автоперезапуск при изменении кода")
    args = parser.parse_args()

    config.ensure_dirs()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    print_banner(args.host, args.port)
    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
