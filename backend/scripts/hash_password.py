#!/usr/bin/env python3
"""
Считает bcrypt-хеш для колонки users.hashed_password (через пакет bcrypt).
Формат совместим с verify_password в app.security (passlib принимает такие хеши).

Запуск из каталога backend:

  python scripts/hash_password.py твой_пароль

или:

  python scripts/hash_password.py

Пример INSERT:

  INSERT INTO users (id, email, hashed_password, full_name, role)
  VALUES (
    gen_random_uuid(),
    'admin@studio.local',
    'СЮДА_ХЕШ',
    'Администратор',
    'admin'
  );
"""

from __future__ import annotations

import argparse
import getpass
import sys

import bcrypt


def main() -> None:
    p = argparse.ArgumentParser(description="Bcrypt-хеш для users.hashed_password")
    p.add_argument("password", nargs="?", help="Пароль (иначе — скрытый ввод)")
    args = p.parse_args()
    raw = args.password
    if raw is None:
        raw = getpass.getpass("Пароль: ")
    if not raw:
        print("Пустой пароль", file=sys.stderr)
        sys.exit(1)
    h = bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt(rounds=12))
    print(h.decode("ascii"))


if __name__ == "__main__":
    main()
