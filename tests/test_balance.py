import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from app.main import pair


def test_pair_is_stable():
    assert pair(9, 2) == (2, 9)
    assert pair(2, 9) == (2, 9)
