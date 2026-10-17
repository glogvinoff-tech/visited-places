from functools import wraps

from django.shortcuts import redirect, render

from db.database import fetch_one


class CurrentUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user_id = request.session.get("user_id")
        request.user = (
            fetch_one(
                "SELECT id, username, name, email, is_staff FROM users "
                "WHERE id = ? AND is_active = 1",
                (user_id,),
            )
            if user_id
            else None
        )
        return self.get_response(request)


def user_context(request):
    return {"user": request.user}


def login_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.user is None:
            return redirect("visited_places:login")
        return view(request, *args, **kwargs)

    return wrapper


def staff_required(view):
    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user["is_staff"]:
            return render(
                request,
                "visited_places/error.html",
                {
                    "title": "Доступ запрещён",
                    "message": "Изменять каталог может администратор.",
                },
                status=403,
            )
        return view(request, *args, **kwargs)

    return wrapper
