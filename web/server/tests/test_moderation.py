import pytest

from app.moderation import moderator


@pytest.mark.parametrize("name", [
    "Вася", "Капитан Немо", "Наташа", "Команда", "Требую", "Страхов", "Сражение", "Сосиска",
    "Scunthorpe", "Mississippi", "Therapist", "Torpedo", "Killer", "Skill", "Heroine", "Hitchcock",
    "Ann-Marie", "Вася2010", "Модерн", "Nikita", "Max", "Alex", "Mark", "Bob", "Ruslan",
])
def test_accepts_clean_names(name):
    assert moderator.check(name).ok, name


@pytest.mark.parametrize("name", [
    "хуй", "Х у й", "xyй", "ХУЙ123", "пи3да", "бляяяя", "мудак", "Сука", "сучара", "гитлер", "Кацап",
    "Fuck", "sh1t", "kill", "H1tler", "nigga", "жопа", "F_u_c_k", "ass", "Pussy Cat",
])
def test_rejects_profanity(name):
    r = moderator.check(name)
    assert r.code == "rejected_profanity", (name, r)


def test_length_and_charset():
    assert moderator.check("a").code == "too_short"
    assert moderator.check("x" * 17).code == "too_long"
    assert moderator.check("Вася!!").code == "invalid_chars"
    assert moderator.check("Вася  Пупкин").code == "invalid_chars"
    assert moderator.check("F.u.c.k").code == "invalid_chars"


@pytest.mark.parametrize("name", [
    "Admin", "Adminка", "Модератор", "Поддержка", "Support", "Игрок 1", "Игрок_1", "Player",
    "vk com", "www", "Telegram", "Ник ru",
])
def test_rejects_reserved(name):
    r = moderator.check(name)
    assert r.code == "reserved", (name, r)


@pytest.mark.parametrize("name", ["89161234567", "ник 12 34 56", "id12345"])
def test_rejects_contacts(name):
    assert moderator.check(name).code == "contacts", name


def test_short_roots_are_whole_words():
    # "~xxx" collapses to "x": as a substring it would reject every name with an x
    assert moderator.check("xxx").code == "rejected_profanity"
    assert moderator.check("Max").ok and moderator.check("Mike").ok
