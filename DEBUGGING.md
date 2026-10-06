# Отладка консольного приложения в VS Code

Группа: ЭФБО-14-24

ФИО: Логвинов Глеб Дмитриевич

Работа выполнена самостоятельно, в индивидуальном формате.

Документ описывает точки остановки и переменные рабочего приложения Visited
Places. Операции меню сохраняют реальные изменения в SQLite. Для учебного
разбора используйте отдельный каталог данных и один экземпляр приложения.

## Запуск

В Run and Debug доступна конфигурация `Python: Visited Places` из
`.vscode/launch.json`. Она запускает `main.py` во встроенном терминале VS Code,
где можно вводить команды меню. По умолчанию используется `data/journal.sqlite3`.
Для отдельной базы передайте программе `--data-dir .\debug-data` в параметрах
запуска отладчика. Обычный запуск отдельного журнала:

```powershell
python main.py --data-dir .\debug-data
```

Если в новом каталоге нет базы и всех четырех JSON-файлов, сначала запрашиваются
имя и email первого пользователя. Для существующего журнала сразу появляется
меню с первым пользователем. Выбор профиля не является аутентификацией.

## Точки остановки

| Файл и метод | Что наблюдать |
| --- | --- |
| `main.py`, `main` | Разбор `--data-dir`, выбор существующей базы или начального JSON-набора, вызов `initialize`/`load`, запуск `ConsoleApplication.run` |
| `visited_places/cli.py`, `ConsoleApplication.run` | Ввод команды, выбор обработчика, повтор меню при ошибке, выход по `0`, EOF или `Ctrl+C` |
| `visited_places/cli.py`, `_commit` | Создание `candidate`, применение `action`, сохранение и замена `self.journal` |
| `visited_places/cli.py`, `_add_visit` | Выбор места, времени, необязательной поездки, рейтинга и заметки |
| `visited_places/cli.py`, `_edit_visit` | Сохранение текущих полей при пустом вводе, удаление рейтинга через `0`, очистка заметки через `-` |
| `visited_places/cli.py`, `_delete_visit` | Выбор отметки и подтверждение перед сохранением |
| `visited_places/cli.py`, `_edit_trip` | Новые название и даты поездки, сохранение текущего поля при пустом вводе |
| `visited_places/cli.py`, `_delete_trip` | Подтверждение удаления и сохранение посещений без поездки |
| `visited_places/database.py`, `JournalDatabase.initialize`/`load`/`save` | Создание базы, проверка версии схемы, восстановление связей и транзакционное сохранение |
| `visited_places/database.py`, `_connection`/`_write` | Соединение, `PRAGMA foreign_keys = ON`, удаление и вставка снимка в одной транзакции |

В `visited_places/service.py` полезны точки остановки в `add_visit`,
`update_visit`, `remove_visit`, `update_trip` и `remove_trip`. Проверки
владельца поездки и диапазона даты посещения также находятся в конструкторе
`Visit` в `visited_places/visits.py`. Статистика рассчитывается в
`visited_places/statistics.py`, `build_travel_statistics`.

## Переменные

| Контекст | Переменные и выражения |
| --- | --- |
| `main` | `arguments.data_dir`, `data_dir`, `database.path`, `database.exists`, `journal`; `seed_files` только в ветке новой базы |
| Методы CLI | `self.user_id`, `self.user.name`, `self.journal.users`, `self.journal.places`, `self.journal.trips`, `self.journal.visits`, `self.database.path` |
| `run` | `command`, `action`, `error` при обработке ошибки |
| `_commit` | `candidate`, `result`, `self.journal`; до успешного `save` рабочий журнал остается прежним |
| `_add_visit` | `place_id`, `visited_at`, `trip_id`, `rating`, `note`, `visit` после сохранения |
| `_edit_visit`/`_delete_visit` | `visit`, `place_id`, `visited_at`, `trip_id`, `rating`, `note`, `updated` в обработчике редактирования |
| `_edit_place`/`_edit_user` | исходный объект, новые поля, `updated` после сохранения |
| `_edit_trip`/`_delete_trip` | `trip`, `name`, `start_date`, `end_date`, `updated` в обработчике редактирования |
| `_show_catalog`/`_search_catalog` | `query`, `places`; пункт `2` сразу показывает весь каталог, пункт `14` запрашивает поиск |
| `_show_statistics` | `statistics`: `visits`, `visited_places`, `cities`, `countries`, `trips`, `average_rating` |
| `JournalDatabase` | `self.path`, `connection`; в `_check_version` - `version`, в `_write` - `table`, `items`, `records` |

Для исходного начального набора статистика первого пользователя до изменений:
4 отметки, 4 места, 2 города, 1 страна, 2 поездки с посещениями, средняя оценка
`14 / 3`. `_show_statistics` форматирует ее как `4.67/5`.

## Сценарий разбора

1. В отдельном журнале создайте пользователя, место и поездку через меню.
2. Поставьте точки остановки в `_add_visit`, `_commit` и `JournalDatabase.save`.
   Через пункт `6` добавьте посещение в пределах дат поездки.
3. На остановке в `_commit` сравните `candidate.visits` и `self.journal.visits`.
   Пройдите сохранение: присваивание `self.journal = candidate` выполняется
   после успешного `self.database.save(candidate)`.
4. Через `7` измените место, дату, поездку, оценку и заметку. Пустой ввод
   сохраняет текущее значение, `0` снимает связь с поездкой или убирает оценку
   в соответствующем поле, `-` очищает заметку.
5. Через `12` попробуйте сузить даты поездки так, чтобы добавленное посещение
   оказалось вне диапазона. В `TravelJournal.update_trip` операция отклоняется;
   прежний рабочий журнал сохраняется, меню продолжает работать.
6. Через `13` удалите поездку с подтверждением `д`, `да`, `y` или `yes`.
   В `remove_trip` у связанных посещений устанавливается `trip = None`.
   История (`1`) продолжает сразу показывать посещения.
7. Завершите работу и повторно запустите приложение с тем же `--data-dir`.
   В `main` выполняется `database.load`, JSON-набор не загружается повторно.

Другие случаи для разбора: неверный рейтинг, неизвестный идентификатор,
поездка другого профиля и повторная отметка с тем же `user_id`, `place_id`,
`visited_at`. Ошибки валидации не доходят до публикации нового рабочего состояния.
Проверки неуспешного сохранения и транзакций находятся в `test_cli.py` и
`test_database.py`; изменение рабочего кода для демонстрации не требуется.

## Проверки

```powershell
pip install -r requirements.txt
python -m pytest -q
python -m flake8
```

По результатам интеграционной проверки текущей версии: `pytest==8.3.3` -
`152 passed`, `flake8==7.1.1` - без замечаний. Шаги ручного разбора выше описывают
сценарий отладки и не являются журналом его выполнения.
