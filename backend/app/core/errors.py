from fastapi import HTTPException, status

# Nouns ending in «ь» are mostly masculine here («Пользователь»); the feminine ones are listed.
_FEMININE_SOFT = {"Роль", "Связь", "Запись"}


def _not_found_word(noun: str) -> str:
    """«Группа не найдена», «Задание не найдено», «Ученик не найден» (QA H-8)."""
    head = noun.split(" ", 1)[0]
    if head in _FEMININE_SOFT or head[-1:] in ("а", "я"):
        return "не найдена"
    if head[-1:] in ("о", "е"):
        return "не найдено"
    if head[-1:] in ("ы", "и"):
        return "не найдены"
    return "не найден"


def not_found(what: str = "Объект") -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} {_not_found_word(what)}")


def forbidden(msg: str = "Недостаточно прав") -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, msg)


def bad_request(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, msg)


def conflict(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, msg)
