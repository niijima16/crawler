from datetime import date

from pydantic import BaseModel, ConfigDict


class Order(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: str
    purchased_on: date
    total_yen: int
