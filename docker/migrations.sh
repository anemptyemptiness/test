#!/bin/bash

echo "Starting alembic upgrade head..."
alembic upgrade head
echo "Alembic upgrade head completed."

psql -h postgres_db -U postgres -d bot -c "
INSERT INTO employees (user_id, fullname, username, role) VALUES
(123456789, 'test_fullname', 'test_username', 'admin');"
psql -h postgres_db -U postgres -d bot -c "
INSERT INTO places (chat_id, title) VALUES
(-123456789, 'тест точка');"
