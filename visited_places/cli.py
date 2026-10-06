import sqlite3
from copy import deepcopy
from typing import Any, Callable

from .database import JournalDatabase
from .places import find_places, sort_places_by_name
from .service import TravelJournal
from .statistics import build_travel_statistics
from .trips import Trip
from .users import User
from .visits import Visit


class ConsoleApplication:
    """Interactive local journal with a selected profile and durable changes."""

    def __init__(self, journal: TravelJournal, database: JournalDatabase) -> None:
        self.journal = journal
        self.database = database
        self.user_id = journal.users[0].id if journal.users else None

    @property
    def user(self) -> User:
        user = next(
            (user for user in self.journal.users if user.id == self.user_id), None
        )
        if user is None:
            raise ValueError("Пользователь не выбран")
        return user

    @staticmethod
    def _integer(prompt: str) -> int:
        try:
            value = int(input(prompt).strip())
        except ValueError as error:
            raise ValueError("Введите целое число") from error
        if value < 1:
            raise ValueError("Идентификатор должен быть положительным")
        return value

    @staticmethod
    def _optional_integer(prompt: str) -> int | None:
        value = input(prompt).strip()
        if not value:
            return None
        try:
            return int(value)
        except ValueError as error:
            raise ValueError("Введите целое число или оставьте поле пустым") from error

    def _commit(self, action: Callable[[TravelJournal], Any]) -> Any:
        """Publish the in-memory change only after SQLite commits it."""
        candidate = deepcopy(self.journal)
        result = action(candidate)
        self.database.save(candidate)
        self.journal = candidate
        return result

    def run(self) -> int:
        actions = {
            "1": self._show_history,
            "2": self._show_catalog,
            "3": self._show_trips,
            "4": self._add_place,
            "5": self._add_trip,
            "6": self._add_visit,
            "7": self._edit_visit,
            "8": self._delete_visit,
            "9": self._show_statistics,
            "10": self._select_user,
            "11": self._add_user,
            "12": self._edit_trip,
            "13": self._delete_trip,
        }
        print("Система учета посещенных мест")
        try:
            while True:
                try:
                    if not self.journal.users:
                        print("\nНовый пользователь")
                        self._add_user()
                        continue
                    self._print_menu()
                    command = input("Команда: ").strip()
                    if command == "0":
                        print("До свидания!")
                        return 0
                    action = actions.get(command)
                    if action is None:
                        print("Неизвестная команда")
                        continue
                    action()
                except (ValueError, OSError, sqlite3.Error) as error:
                    print(f"Ошибка: {error}")
        except (EOFError, KeyboardInterrupt):
            print("\nДо свидания!")
            return 0

    def _print_menu(self) -> None:
        print(f"\nПользователь: {self.user.name}")
        print("1. История посещений")
        print("2. Каталог и поиск мест")
        print("3. Мои поездки")
        print("4. Добавить место")
        print("5. Добавить поездку")
        print("6. Добавить посещение")
        print("7. Редактировать отметку")
        print("8. Удалить отметку")
        print("9. Статистика")
        print("10. Выбрать пользователя")
        print("11. Добавить пользователя")
        print("12. Редактировать поездку")
        print("13. Удалить поездку")
        print("0. Выход")

    @staticmethod
    def _print_visits(visits: list[Visit]) -> None:
        if not visits:
            print("Посещений нет")
        for visit in visits:
            rating = f"{visit.rating}/5" if visit.rating is not None else "без оценки"
            trip = visit.trip.name if visit.trip is not None else "без поездки"
            print(
                f"#{visit.id}: {visit.place.name}, {visit.place.city}, "
                f"{visit.visited_at}, {rating}, {trip}"
            )
            if visit.note:
                print(f"  {visit.note}")

    def _show_history(self) -> None:
        trip_id = self._optional_integer("ID поездки (необязательно): ")
        self._print_visits(self.journal.list_visits(self.user.id, trip_id))

    def _show_catalog(self) -> None:
        query = input("Поиск (необязательно): ").strip()
        places = sort_places_by_name(find_places(self.journal.places, query))
        if not places:
            print("Места не найдены")
        for place in places:
            print(f"#{place.id}: {place}, {place.category}")

    def _show_trips(self) -> list[Trip]:
        trips = sorted(
            (trip for trip in self.journal.trips if trip.user_id == self.user.id),
            key=lambda trip: trip.start_date,
        )
        if not trips:
            print("Поездок нет")
        for trip in trips:
            print(f"#{trip.id}: {trip}")
        return trips

    def _add_user(self) -> None:
        name = input("Имя: ")
        email = input("Email: ")
        user = self._commit(lambda journal: journal.add_user(name, email))
        self.user_id = user.id
        print(f"Пользователь сохранен: #{user.id}, {user.name}")

    def _select_user(self) -> None:
        for user in self.journal.users:
            print(f"#{user.id}: {user}")
        user_id = self._integer("ID пользователя: ")
        if not any(user.id == user_id for user in self.journal.users):
            raise ValueError("Пользователь не найден")
        self.user_id = user_id
        print(f"Выбран пользователь: {self.user.name}")

    def _add_place(self) -> None:
        name = input("Название места: ")
        city = input("Город: ")
        country = input("Страна: ")
        category = input("Категория: ")
        place = self._commit(
            lambda journal: journal.add_place(name, city, country, category)
        )
        print(f"Место сохранено: #{place.id}, {place.name}")

    def _add_trip(self) -> None:
        name = input("Название поездки: ")
        start_date = input("Дата начала (YYYY-MM-DD): ").strip()
        end_date = input("Дата окончания (YYYY-MM-DD): ").strip()
        trip = self._commit(lambda journal: journal.add_trip(
            self.user.id, name, start_date, end_date
        ))
        print(f"Поездка сохранена: #{trip.id}, {trip.name}")

    def _add_visit(self) -> None:
        if not self.journal.places:
            print("Сначала добавьте место")
            return
        for place in sort_places_by_name(self.journal.places):
            print(f"#{place.id}: {place}")
        place_id = self._integer("ID места: ")
        visited_at = input("Дата посещения (YYYY-MM-DD HH:MM): ").strip()
        self._show_trips()
        trip_id = self._optional_integer("ID поездки (необязательно): ")
        rating = self._optional_integer("Оценка 1-5 (необязательно): ")
        note = input("Заметка: ")
        visit = self._commit(lambda journal: journal.add_visit(
            self.user.id, place_id, visited_at, rating, note, trip_id
        ))
        print(f"Посещение сохранено: #{visit.id}, {visit.place.name}")

    def _choose_visit(self) -> Visit | None:
        visits = self.journal.list_visits(self.user.id)
        self._print_visits(visits)
        if not visits:
            return None
        visit_id = self._integer("ID отметки: ")
        visit = next((visit for visit in visits if visit.id == visit_id), None)
        if visit is None:
            raise ValueError("Отметка не найдена в истории пользователя")
        return visit

    def _edit_visit(self) -> None:
        visit = self._choose_visit()
        if visit is None:
            return
        current_rating = visit.rating if visit.rating is not None else "нет"
        value = input(f"Оценка [{current_rating}, 0 - убрать]: ").strip()
        rating = visit.rating
        if value:
            try:
                rating = int(value)
            except ValueError as error:
                raise ValueError("Введите целую оценку от 1 до 5") from error
            if rating == 0:
                rating = None
        note = input(f"Заметка [{visit.note}; '-' очистить]: ")
        note = "" if note == "-" else note or visit.note
        updated = self._commit(lambda journal: journal.update_visit(
            self.user.id, visit.id, rating=rating, note=note
        ))
        print(f"Отметка обновлена: #{updated.id}")

    @staticmethod
    def _confirm(prompt: str) -> bool:
        return input(prompt).strip().casefold() in {"д", "да", "y", "yes"}

    def _delete_visit(self) -> None:
        visit = self._choose_visit()
        if visit is None:
            return
        if not self._confirm(f"Удалить отметку #{visit.id}? [д/н]: "):
            print("Удаление отменено")
            return
        self._commit(lambda journal: journal.remove_visit(self.user.id, visit.id))
        print(f"Отметка удалена: #{visit.id}")

    def _show_statistics(self) -> None:
        statistics = build_travel_statistics(self.journal.visits, self.user.id)
        print(f"Отметок: {statistics['visits']}")
        print(f"Уникальных мест: {statistics['visited_places']}")
        print(f"Городов: {statistics['cities']}; стран: {statistics['countries']}")
        print(f"Поездок с посещениями: {statistics['trips']}")
        print(f"Средняя оценка: {statistics['average_rating']:.2f}/5")

    def _choose_trip(self) -> Trip | None:
        trips = self._show_trips()
        if not trips:
            return None
        trip_id = self._integer("ID поездки: ")
        trip = next((trip for trip in trips if trip.id == trip_id), None)
        if trip is None:
            raise ValueError("Поездка не найдена у пользователя")
        return trip

    def _edit_trip(self) -> None:
        trip = self._choose_trip()
        if trip is None:
            return
        name = input(f"Название [{trip.name}]: ").strip() or trip.name
        start_date = input(f"Дата начала [{trip.start_date}]: ").strip()
        end_date = input(f"Дата окончания [{trip.end_date}]: ").strip()
        updated = self._commit(lambda journal: journal.update_trip(
            self.user.id, trip.id, name=name,
            start_date=start_date or trip.start_date,
            end_date=end_date or trip.end_date,
        ))
        print(f"Поездка обновлена: #{updated.id}")

    def _delete_trip(self) -> None:
        trip = self._choose_trip()
        if trip is None:
            return
        if not self._confirm(f"Удалить поездку #{trip.id}? [д/н]: "):
            print("Удаление отменено")
            return
        self._commit(lambda journal: journal.remove_trip(self.user.id, trip.id))
        print(f"Поездка удалена: #{trip.id}; отметки сохранены")
