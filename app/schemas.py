from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class FriendRequestCreate(BaseModel):
    username: str = Field(min_length=2, max_length=100)

    @field_validator("username")
    @classmethod
    def clean_username(cls, value: str) -> str:
        return value.strip().removeprefix("@").lower()


class FriendRequestDecision(BaseModel):
    accept: bool


class TransactionCreate(BaseModel):
    kind: Literal["debt", "payment", "settlement"]
    amount: int | None = Field(default=None, ge=1, le=999_999_999_999_999)
    description: str = Field(default="", max_length=500)
    happened_on: date
    direction: Literal["me_to_friend", "friend_to_me"] = "me_to_friend"


class TransactionUpdate(BaseModel):
    amount: int = Field(ge=1, le=999_999_999_999_999)
    description: str = Field(default="", max_length=500)
    happened_on: date


class ExpenseCreate(BaseModel):
    amount: int = Field(ge=1, le=999_999_999_999_999)
    description: str = Field(min_length=1, max_length=500)
    happened_on: date


class SettingsUpdate(BaseModel):
    notifications: bool = True

