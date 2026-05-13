from pydantic import BaseModel, Field, conlist
from typing import List, Optional, Literal

class Dimension(BaseModel):
    value: float
    unit: Literal["mm", "cm", "m"] # Убрали лишнее
    dimension_type: str = Field(..., max_length=50) # Ограничили длину
    description: Optional[str] = Field(None, max_length=100) # Сделали необязательным
    # between_objects: Optional[List[str]] # УДАЛИЛИ или упростили, это поле очень тяжелое

class DrawingObject(BaseModel):
    id: str
    type: str = Field(..., max_length=50)
    description: str = Field(..., max_length=200) # Жёсткий лимит на описание
    dimensions: List[Dimension] = Field(default_factory=list)
    # annotations: List[str] # Если не критично, лучше вынести в описание

class DrawingAnalysis(BaseModel):
    # Ограничиваем количество объектов, которые модель может вернуть за раз (например, 10-15)
    objects: List[DrawingObject] = Field(default_factory=list, max_items=15)
    # relationships: List[Relationship] # ВНИМАНИЕ: Связи лучше извлечь отдельным вызовом,
    # если объектов много. Они сильно раздувают JSON.