#!/usr/bin/env python3
"""
Скрипт запуска веб-приложения Belstat Crime Dataset (Бэкенд и Фронтенд).
"""

import subprocess
import sys
import os
import time

def main():
    backend_dir = os.path.join(os.path.dirname(__file__), "belstat_backend")
    frontend_dir = os.path.join(os.path.dirname(__file__), "web_app")
    
    print("Запуск веб-приложения Belstat Crime Dataset...")
    
    # 1. Установка зависимостей фронтенда ПЕРВОЙ (предотвращает перемешанный вывод)
    if not os.path.exists(os.path.join(frontend_dir, "node_modules")):
        print("Установка зависимостей фронтенда (это может занять некоторое время)...")
        try:
            subprocess.run(["npm", "install"], cwd=frontend_dir, check=True)
        except subprocess.CalledProcessError as e:
            print(f"\n❌ Не удалось установить зависимости фронтенда: {e}")
            sys.exit(1)
        except KeyboardInterrupt:
            print("\n⚠️ Установка отменена пользователем.")
            sys.exit(1)

    # 2. Запуск бэкенда
    print("Запуск FastAPI бэкенда на http://localhost:8001...")
    backend_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "belstat_backend.main:app", "--host", "0.0.0.0", "--port", "8001"],
        cwd=backend_dir
    )
    
    # 3. Запуск фронтенда
    print("Запуск Next.js фронтенда на http://localhost:3000...")
    frontend_process = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=frontend_dir
    )
    
    print("\n✅ Сервисы запущены!")
    print("  - Backend API: http://localhost:8001")
    print("  - API Docs:    http://localhost:8001/docs")
    print("  - Frontend:    http://localhost:3000")
    print("\nНажмите Ctrl+C для остановки обоих сервисов.")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Остановка сервисов...")
        backend_process.terminate()
        frontend_process.terminate()
        
        # Гарантируем полное завершение процессов, даже если они зависают
        for proc in [backend_process, frontend_process]:
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                
        print("Сервисы успешно остановлены.")

if __name__ == "__main__":
    main()
