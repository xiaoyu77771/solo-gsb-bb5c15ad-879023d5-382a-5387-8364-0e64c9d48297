"""Pydantic 请求模型(同时用于 /docs 中的接口文档)。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ZoneIn(BaseModel):
    name: str = Field(..., description="温区名称,如:冷冻区")
    t_min: float = Field(..., description="温区下限 ℃")
    t_max: float = Field(..., description="温区上限 ℃")


class CargoIn(BaseModel):
    name: str = Field(..., description="货物批次名称")
    units: int = Field(..., gt=0, description="件数(拆分的最小单位)")
    unit_volume: float = Field(..., gt=0, description="单件占用体积")
    t_min: float = Field(..., description="允许温度下限 ℃")
    t_max: float = Field(..., description="允许温度上限 ℃")
    max_transport_hours: float | None = Field(
        None, ge=0, description="该批货物可承受的最长运输时长(小时),留空表示不限"
    )


class PlanRequest(BaseModel):
    transport_hours: float = Field(..., ge=0, description="运输时长(小时)")
    box_capacity: float = Field(..., gt=0, description="单个箱体容量(体积单位)")
    max_boxes: int = Field(100, gt=0, description="最多使用的箱子数量")
    volume_unit: str = Field("m³", description="体积单位名称,仅用于展示")
    zones: list[ZoneIn] = Field(..., min_length=1, description="可用温区列表")
    cargoes: list[CargoIn] = Field(..., min_length=1, description="货物批次列表")
