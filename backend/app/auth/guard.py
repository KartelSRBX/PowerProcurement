"""Rules about who may approve what, for routes that know the author. They apply only while sign-in is on,
because only then is the name in a request the true one."""

from fastapi import HTTPException, Request


def acting(request: Request) -> str | None:
    """The signed-in user's name, or None while sign-in is off."""
    user = request.scope.get("auth_user")
    return user["name"] if user else None


def not_author(request: Request, author: str | None, what: str) -> None:
    """Refuse (409) when the signed-in user is the one who wrote or entered what they are approving."""
    me = acting(request)
    if me and author and me.casefold() == author.casefold():
        raise HTTPException(409, f"a different person has to approve {what}: {author} edited or entered it")


def remember_editor(request: Request, row) -> None:
    """Record who last changed a text, when it is known who that is."""
    me = acting(request)
    if me:
        row.edited_by = me
