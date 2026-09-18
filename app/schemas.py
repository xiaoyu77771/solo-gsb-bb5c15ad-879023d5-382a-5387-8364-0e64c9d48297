"""Pydantic 请求模型(同时用于 /docs 中的接口文档)。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ZoneIn(BaseModel):
    name: str | None = Field(None, description="温区名称,如:冷冻区;留空自动编号")
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


class TransportSegmentIn(BaseModel):
    name: str | None = Field(
        None, description="运输段名称,如:公路干线;留空自动按顺序编号"
    )
    hours: float = Field(..., gt=0, description="该运输段时长(小时),必须大于 0")
    zones: list[ZoneIn] = Field(
        ..., min_length=1, description="该运输段可用温区列表(按车辆/冷库能力维护)"
    )


class PlanRequest(BaseModel):
    transport_hours: float = Field(
        0,
        ge=0,
        description=(
            "运输总时长(小时)。单温区模式下必传;分段模式下可留空,"
            "服务端按各段时长之和计算"
        ),
    )
    box_capacity: float = Field(..., gt=0, description="单个箱体容量(体积单位)")
    max_boxes: int = Field(100, gt=0, description="最多使用的箱子数量")
    volume_unit: str = Field("m³", description="体积单位名称,仅用于展示")
    zones: list[ZoneIn] | None = Field(
        None,
        description=(
            "允许温区列表(单温区模式,与旧版兼容)。提供 segments 时以分段为准,"
            "可留空"
        ),
    )
    segments: list[TransportSegmentIn] | None = Field(
        None,
        description=(
            "按顺序维护的运输段列表,每段包含名称、时长与该段可用温区;"
            "提供后规划器对每个箱子的共同允许温度逐段校验。"
            "留空或不传则使用上方 zones 的单一温区模式(兼容旧版)"
        ),
    )
    cargoes: list[CargoIn] = Field(..., min_length=1, description="货物批次列表")
