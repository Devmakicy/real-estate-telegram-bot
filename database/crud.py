from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Order, OrderPhoto, OrderStatus, User


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> User:
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user:
        user.username = username
        user.first_name = first_name
        user.last_name = last_name
        await session.commit()
        return user

    user = User(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def create_order(
    session: AsyncSession,
    user_id: int,
    link: str | None = None,
    text: str | None = None,
    photo_file_ids: list[str] | None = None,
    photo_paths: list[str | None] | None = None,
) -> Order:
    order = Order(user_id=user_id, link=link, text=text)
    session.add(order)
    await session.flush()

    if photo_file_ids:
        for i, file_id in enumerate(photo_file_ids):
            path = photo_paths[i] if photo_paths and i < len(photo_paths) else None
            session.add(OrderPhoto(order_id=order.id, file_id=file_id, file_path=path))

    await session.commit()
    return await get_order(session, order.id)


async def get_order(session: AsyncSession, order_id: int) -> Order | None:
    result = await session.execute(
        select(Order)
        .options(selectinload(Order.user), selectinload(Order.photos))
        .where(Order.id == order_id)
    )
    return result.scalar_one_or_none()


async def get_orders(
    session: AsyncSession,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Order]:
    query = (
        select(Order)
        .options(selectinload(Order.user), selectinload(Order.photos))
        .order_by(Order.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status:
        query = query.where(Order.status == status)
    result = await session.execute(query)
    return list(result.scalars().all())


async def update_order_status(
    session: AsyncSession, order_id: int, status: str, admin_note: str | None = None
) -> Order | None:
    order = await get_order(session, order_id)
    if not order:
        return None
    order.status = status
    if admin_note is not None:
        order.admin_note = admin_note
    await session.commit()
    await session.refresh(order)
    return order


async def get_user_by_telegram_id(
    session: AsyncSession, telegram_id: int
) -> User | None:
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def get_user_by_topic_id(session: AsyncSession, topic_id: int) -> User | None:
    result = await session.execute(select(User).where(User.topic_id == topic_id))
    return result.scalar_one_or_none()


async def set_user_topic_id(
    session: AsyncSession, user_id: int, topic_id: int
) -> None:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        user.topic_id = topic_id
        await session.commit()


async def count_orders(session: AsyncSession, status: str | None = None) -> int:
    from sqlalchemy import func

    query = select(func.count(Order.id))
    if status:
        query = query.where(Order.status == status)
    result = await session.execute(query)
    return result.scalar_one()
