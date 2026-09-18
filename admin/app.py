import secrets
from pathlib import Path

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from config import ADMIN_PASSWORD, ADMIN_USERNAME, BOT_TOKEN, SECRET_KEY
from database.crud import get_order, get_orders, update_order_status
from database.models import OrderStatus
from database.session import async_session

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Real Estate Video Bot Admin")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

STATUS_LABELS = {
    OrderStatus.NEW.value: "Новая",
    OrderStatus.IN_PROGRESS.value: "В работе",
    OrderStatus.COMPLETED.value: "Готово",
    OrderStatus.CANCELLED.value: "Отменена",
}

STATUS_BADGE = {
    OrderStatus.NEW.value: "badge-new",
    OrderStatus.IN_PROGRESS.value: "badge-progress",
    OrderStatus.COMPLETED.value: "badge-done",
    OrderStatus.CANCELLED.value: "badge-cancel",
}


def get_current_user(request: Request) -> str | None:
    return request.session.get("user")


def require_auth(request: Request) -> str:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user


@app.exception_handler(401)
async def auth_exception_handler(request: Request, exc: HTTPException):
    if request.url.path.startswith("/orders") or request.url.path == "/":
        return RedirectResponse("/login", status_code=303)
    return HTMLResponse("Unauthorized", status_code=401)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if get_current_user(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if secrets.compare_digest(username, ADMIN_USERNAME) and secrets.compare_digest(
        password, ADMIN_PASSWORD
    ):
        request.session["user"] = username
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": "Неверный логин или пароль"}, status_code=401
    )


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, status_filter: str | None = None, _=Depends(require_auth)):
    async with async_session() as session:
        orders = await get_orders(session, status=status_filter or None, limit=200)
        all_orders = await get_orders(session, limit=1000)

    counts = {s.value: 0 for s in OrderStatus}
    for o in all_orders:
        counts[o.status] = counts.get(o.status, 0) + 1

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "orders": orders,
            "counts": counts,
            "status_filter": status_filter,
            "status_labels": STATUS_LABELS,
            "status_badge": STATUS_BADGE,
            "statuses": [s.value for s in OrderStatus],
        },
    )


@app.get("/orders/{order_id}", response_class=HTMLResponse)
async def order_detail(request: Request, order_id: int, _=Depends(require_auth)):
    async with async_session() as session:
        order = await get_order(session, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    return templates.TemplateResponse(
        "order_detail.html",
        {
            "request": request,
            "order": order,
            "status_labels": STATUS_LABELS,
            "status_badge": STATUS_BADGE,
            "statuses": [s.value for s in OrderStatus],
        },
    )


@app.post("/orders/{order_id}/status")
async def change_status(
    request: Request,
    order_id: int,
    status: str = Form(...),
    admin_note: str = Form(""),
    _=Depends(require_auth),
):
    valid = {s.value for s in OrderStatus}
    if status not in valid:
        raise HTTPException(status_code=400, detail="Invalid status")

    async with async_session() as session:
        order = await update_order_status(session, order_id, status, admin_note or None)

    if not order:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    if BOT_TOKEN:
        bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        status_messages = {
            OrderStatus.IN_PROGRESS.value: (
                f"⏳ Ваша заявка #{order_id} принята в работу. "
                "Менеджер скоро свяжется с вами."
            ),
            OrderStatus.COMPLETED.value: (
                f"✅ Ваша заявка #{order_id} выполнена! "
                "Менеджер отправит вам готовый ролик."
            ),
            OrderStatus.CANCELLED.value: (
                f"❌ Заявка #{order_id} отменена. Если это ошибка — напишите нам."
            ),
        }
        if status in status_messages:
            try:
                async with async_session() as session:
                    full_order = await get_order(session, order_id)
                if full_order:
                    await bot.send_message(
                        full_order.user.telegram_id, status_messages[status]
                    )
            except Exception:
                pass
        await bot.session.close()

    return RedirectResponse(f"/orders/{order_id}?updated=1", status_code=303)


@app.post("/orders/{order_id}/message")
async def send_message(
    request: Request,
    order_id: int,
    message: str = Form(...),
    _=Depends(require_auth),
):
    async with async_session() as session:
        order = await get_order(session, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    if not BOT_TOKEN:
        raise HTTPException(status_code=500, detail="BOT_TOKEN not configured")

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        await bot.send_message(
            order.user.telegram_id,
            f"💬 Сообщение от менеджера:\n\n{message}",
        )
    except Exception as e:
        await bot.session.close()
        raise HTTPException(status_code=400, detail=str(e)) from e
    await bot.session.close()

    return RedirectResponse(f"/orders/{order_id}?sent=1", status_code=303)
