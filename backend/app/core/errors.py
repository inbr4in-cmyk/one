from fastapi import HTTPException, status


def not_found(what: str = "Объект") -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} не найден")


def forbidden(msg: str = "Недостаточно прав") -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, msg)


def bad_request(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, msg)


def conflict(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, msg)
