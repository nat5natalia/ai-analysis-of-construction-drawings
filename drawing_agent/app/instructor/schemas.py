from pydantic import BaseModel, Field
from typing import List, Optional, Literal


class Dimension(BaseModel):
    value: float = Field(..., description="Числовое значение")
    unit: Literal["mm", "cm", "m", "inch"] = Field(..., description="Единица измерения")
    dimension_type: str = Field(..., description="Тип размера (ширина, высота, диаметр и т.д.)")
    description: str = Field(..., description="Описание размера")
    between_objects: Optional[List[str]] = Field(None, description="Между какими объектами")


class DrawingObject(BaseModel):
    id: str = Field(..., description="Уникальный идентификатор")
    type: str = Field(..., description="Тип объекта (отверстие, линия, размер и т.д.)")
    description: str = Field(..., description="Описание объекта")
    dimensions: List[Dimension] = Field(default_factory=list, description="Размеры объекта")
    annotations: List[str] = Field(default_factory=list, description="Аннотации")


class Relationship(BaseModel):
    source_id: str = Field(..., description="ID исходного объекта")
    target_id: str = Field(..., description="ID целевого объекта")
    type: str = Field(..., description="Тип связи (connected, aligned, dependent)")


class DrawingAnalysis(BaseModel):
    objects: List[DrawingObject] = Field(default_factory=list, description="Объекты на чертеже")
    relationships: List[Relationship] = Field(default_factory=list, description="Связи между объектами")