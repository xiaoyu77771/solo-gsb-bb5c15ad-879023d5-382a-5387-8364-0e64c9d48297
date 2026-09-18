"""冷链装箱温控规划器核心算法。

规则:
- 每个温区是一个闭区间 [t_min, t_max],货物允许温区同理。
- 运输过程可按顺序拆成多个运输段,每段有自己的名称、时长与可用温区
  (如"产地冷库 6h → 公路干线 12h → 末端配送 6h")。未提供分段时,
  自动视为一个名为"运输全程"的单段,与旧版单一温区输入完全兼容。
- 货物只能装入"允许温区与箱中已有货物存在共同温度,且该共同温度在
  每一个运输段都能被该段某个可用温区覆盖"的箱子。
- 箱内可行温度 = 已装入货物允许温区的交集;逐段校验时该段可设定温度段
  为 "可行交集 ∩ 该段各温区" 的合并结果。多式联运允许各运输段重新设定
  温度,因此每个运输段独立存在可设定温度即视为该段通过;箱级温度区间为
  各段可设定温度段的合并(按段切换设定值)。
- 同一批货物可按"件"为最小单位拆分到多个箱子。
- 采用 First-Fit-Decreasing 启发式:温度下限越低(要求越苛刻)的批次优先,
  同温限按总体积降序;依次塞入已有箱子,放不下再开新箱。
- 装箱完成后对每个箱子逐段复核,报告首次出现不兼容的运输段、该箱内
  受影响批次与原因;只有全部货物装载且每个箱子通过全部运输段才标记为
  可运输(各段可重新设定温度,按段独立校验)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

EPS = 1e-9
# 未装载原因中最多列举几个温区/箱子名称
_DETAIL_LIMIT = 3


def _r(v: float) -> float:
    """规整浮点输出,消除 -0.0 之类误差。"""
    v = round(float(v), 4)
    return 0.0 if abs(v) < 1e-9 else v


@dataclass
class _Iv:
    lo: float
    hi: float

    def intersect(self, other: "_Iv") -> "_Iv | None":
        lo, hi = max(self.lo, other.lo), min(self.hi, other.hi)
        return _Iv(lo, hi) if lo <= hi + EPS else None


@dataclass
class _Zone:
    name: str
    iv: _Iv


@dataclass
class _Segment:
    no: int
    name: str
    hours: float
    zones: list[_Zone]


@dataclass
class _Loaded:
    batch_no: int
    name: str
    units: int
    volume: float


@dataclass
class _Box:
    index: int
    capacity: float
    zones: list[_Zone]
    segments: list[_Segment]
    used: float = 0.0
    items: list[_Loaded] = field(default_factory=list)
    # 已装入货物允许温区的交集;首件货物装入时初始化
    feasible: _Iv | None = None

    def _covers_all_segments(self, candidate: _Iv) -> bool:
        """共同温度区间是否在每一个运输段都能被该段某个温区覆盖。"""
        return all(
            any(candidate.intersect(z.iv) is not None for z in seg.zones)
            for seg in self.segments
        )

    def try_load(self, batch: "_Batch", iv: _Iv) -> bool:
        """尝试装入 1 件货物,成功则更新箱内温度交集与容量。"""
        if self.used + batch.unit_volume > self.capacity + EPS:
            return False
        new_feasible = iv if self.feasible is None else self.feasible.intersect(iv)
        if new_feasible is None:
            return False
        # 交集后的温度还必须在每一个运输段都至少能被一个温区覆盖
        if not self._covers_all_segments(new_feasible):
            return False
        if self.items and self.items[-1].batch_no == batch.no:
            self.items[-1].units += 1
            self.items[-1].volume = _r(self.items[-1].volume + batch.unit_volume)
        else:
            self.items.append(
                _Loaded(
                    batch_no=batch.no,
                    name=batch.name,
                    units=1,
                    volume=batch.unit_volume,
                )
            )
        self.used = _r(self.used + batch.unit_volume)
        self.feasible = new_feasible
        return True

    def can_take(self, iv: _Iv) -> bool:
        """该箱是否在全部运输段的温区上能容纳此温度区间的货物(不考虑剩余容量)。"""
        candidate = iv if self.feasible is None else self.feasible.intersect(iv)
        return candidate is not None and self._covers_all_segments(candidate)


@dataclass
class _Batch:
    no: int
    name: str
    units: int
    unit_volume: float
    iv: _Iv
    max_hours: float | None
    total_volume: float


def _fmt_names(names: list[str]) -> str:
    head = "、".join(names[:_DETAIL_LIMIT])
    if len(names) > _DETAIL_LIMIT:
        head += f" 等 {len(names)} 项"
    return head


def _merge_segments(segs: list[_Iv]) -> list[_Iv]:
    """合并相交或端点相接的温度段。"""
    segs = sorted(segs, key=lambda s: (s.lo, s.hi))
    merged: list[_Iv] = []
    for s in segs:
        if merged and s.lo <= merged[-1].hi + EPS:
            merged[-1].hi = max(merged[-1].hi, s.hi)
        else:
            merged.append(_Iv(s.lo, s.hi))
    return merged


def _parse_zones(raw_zones: Any) -> list[_Zone]:
    """解析一组 {name, t_min, t_max} 温区定义。"""
    zones: list[_Zone] = []
    for i, z in enumerate(raw_zones or []):
        lo, hi = float(z["t_min"]), float(z["t_max"])
        name = str(z.get("name") or f"温区 {i + 1}").strip() or f"温区 {i + 1}"
        if lo > hi + EPS:
            raise ValueError(f"温区 {name} 的温度下限高于上限")
        zones.append(_Zone(name=name, iv=_Iv(lo, hi)))
    return zones


def _leg_segments(feasible: _Iv, seg: _Segment) -> list[_Iv]:
    """箱内共同温度在某一运输段可设定的温度段(共同交集 ∩ 该段各温区)。"""
    raw = [
        iv
        for z in seg.zones
        if (iv := feasible.intersect(z.iv)) is not None
    ]
    return _merge_segments(raw)


def plan(payload: dict[str, Any]) -> dict[str, Any]:
    """根据请求 payload 生成分箱方案;输入不合法时抛 ValueError。"""
    box_capacity = float(payload.get("box_capacity", 0))
    max_boxes = int(payload.get("max_boxes", 100))
    volume_unit = str(payload.get("volume_unit") or "体积单位").strip() or "体积单位"

    if box_capacity <= 0:
        raise ValueError("箱体容量必须大于 0")
    if max_boxes <= 0:
        raise ValueError("最大箱数必须大于 0")

    # ---- 运输分段:有 segments 时按分段逐段校验;否则退化为单段(旧版兼容) ----
    raw_segments = payload.get("segments")
    segmented = bool(raw_segments)
    segments: list[_Segment] = []
    if segmented:
        for i, s in enumerate(raw_segments):
            name = str(s.get("name") or f"运输段 {i + 1}").strip() or f"运输段 {i + 1}"
            hours = float(s.get("hours", 0))
            if hours < 0:
                raise ValueError(f"运输段 {name} 的时长不能为负数")
            if hours <= 0:
                raise ValueError(f"运输段 {name} 的时长必须大于 0")
            seg_zones = _parse_zones(s.get("zones"))
            if not seg_zones:
                raise ValueError(f"运输段 {name} 至少需要一个可用温区")
            segments.append(_Segment(no=i + 1, name=name, hours=hours, zones=seg_zones))
        transport_hours = _r(sum(s.hours for s in segments))
    else:
        transport_hours = float(payload.get("transport_hours", 0))
        if transport_hours < 0:
            raise ValueError("运输时长不能为负数")
        legacy_zones = _parse_zones(payload.get("zones"))
        if not legacy_zones:
            raise ValueError("至少需要定义一个允许温区")
        segments = [
            _Segment(no=1, name="运输全程", hours=transport_hours, zones=legacy_zones)
        ]

    # 全部运输段温区的并集(去重),用于装箱阶段的容量无关预检与展示
    seen_zones: dict[tuple[str, float, float], _Zone] = {}
    for seg in segments:
        for z in seg.zones:
            seen_zones.setdefault((z.name, z.iv.lo, z.iv.hi), z)
    all_zones = list(seen_zones.values())

    batches: list[_Batch] = []
    for i, c in enumerate(payload.get("cargoes") or []):
        name = str(c.get("name") or f"批次 {i + 1}")
        lo, hi = float(c["t_min"]), float(c["t_max"])
        if lo > hi + EPS:
            raise ValueError(f"货物 {name} 的允许温度下限高于上限")
        units = int(c["units"])
        unit_volume = float(c["unit_volume"])
        if units <= 0:
            raise ValueError(f"货物 {name} 的件数必须大于 0")
        if unit_volume <= 0:
            raise ValueError(f"货物 {name} 的单件体积必须大于 0")
        mh = c.get("max_transport_hours")
        max_hours = None if mh in (None, "", 0, "0") else float(mh)
        if max_hours is not None and max_hours < 0:
            raise ValueError(f"货物 {name} 的最长运输时长不能为负数")
        batches.append(
            _Batch(
                no=i + 1,
                name=name,
                units=units,
                unit_volume=unit_volume,
                iv=_Iv(lo, hi),
                max_hours=max_hours,
                total_volume=_r(units * unit_volume),
            )
        )
    if not batches:
        raise ValueError("至少需要录入一批货物")

    boxes: list[_Box] = []
    unloaded: list[dict[str, Any]] = []

    def add_unloaded(batch: _Batch, units: int, reason: str, **extra: Any) -> None:
        unloaded.append(
            {
                "batch_no": batch.no,
                "name": batch.name,
                "units": units,
                "volume": _r(units * batch.unit_volume),
                "reason": reason,
                **extra,
            }
        )

    # 温度下限越低越苛刻,优先装;同温限按总体积降序
    for b in sorted(batches, key=lambda x: (x.iv.lo, -x.total_volume)):
        # 1) 运输时长预检(分段模式下总时长为各段之和)
        if b.max_hours is not None and transport_hours > b.max_hours + EPS:
            add_unloaded(
                b,
                b.units,
                f"运输总时长 {_r(transport_hours)}h 超过该批允许的 "
                f"{_r(b.max_hours)}h,全程温度无法保证",
            )
            continue

        # 2) 逐段温区预检:按顺序找到第一个无法容纳该批的运输段
        failed_seg: _Segment | None = None
        for seg in segments:
            if not any(b.iv.intersect(z.iv) is not None for z in seg.zones):
                failed_seg = seg
                break
        if failed_seg is not None:
            add_unloaded(
                b,
                b.units,
                f"在运输段「{failed_seg.name}」(第 {failed_seg.no} 段,"
                f"{_r(failed_seg.hours)}h)中,该批允许温区 "
                f"[{_r(b.iv.lo)}, {_r(b.iv.hi)}]℃ 与该段全部可用温区 "
                f"({_fmt_names([z.name for z in failed_seg.zones])})均无交集",
                failed_segment_no=failed_seg.no,
                failed_segment_name=failed_seg.name,
            )
            continue

        # 3) 先尝试已有箱子(First-Fit)
        remaining = b.units
        unusable_boxes = 0
        for box in boxes:
            if remaining == 0:
                break
            if not box.can_take(b.iv):
                unusable_boxes += 1
                continue
            while remaining > 0 and box.try_load(b, b.iv):
                remaining -= 1
            if remaining > 0:
                # 温区兼容但本箱容量已不足
                unusable_boxes += 1

        # 4) 开新箱继续装,直到装完或达到上限
        while remaining > 0:
            if len(boxes) >= max_boxes:
                covering = [
                    z for z in all_zones if b.iv.intersect(z.iv) is not None
                ]
                add_unloaded(
                    b,
                    remaining,
                    f"温区兼容({_fmt_names([z.name for z in covering])}),"
                    f"但已达最大箱数 {max_boxes},现有 {len(boxes)} 个箱子"
                    f"{'均无兼容温度或容量不足' if unusable_boxes else '容量不足'}",
                    tried_boxes=len(boxes),
                )
                break
            if b.unit_volume > box_capacity + EPS:
                add_unloaded(
                    b,
                    remaining,
                    f"单件体积 {_r(b.unit_volume)} {volume_unit} 超过单箱容量 "
                    f"{_r(box_capacity)} {volume_unit},新箱也无法装载",
                    new_box_failed=True,
                )
                break
            box = _Box(
                index=len(boxes) + 1,
                capacity=box_capacity,
                zones=all_zones,
                segments=segments,
            )
            if not box.try_load(b, b.iv):
                add_unloaded(
                    b,
                    remaining,
                    f"允许温区 [{_r(b.iv.lo)}, {_r(b.iv.hi)}]℃ 无法同时满足"
                    f"全部运输段的可用温区,新箱也无法装载",
                    new_box_failed=True,
                )
                break
            boxes.append(box)
            remaining -= 1
            while remaining > 0 and box.try_load(b, b.iv):
                remaining -= 1

    # 5) 逐段复核并组装输出
    out_boxes: list[dict[str, Any]] = []
    segment_failures: list[dict[str, Any]] = []
    loaded_units = 0
    loaded_volume = 0.0
    for box in boxes:
        assert box.feasible is not None

        # 逐段复核:记录每段可设定温度段与首次不兼容的运输段。
        # 各段允许重新设定温度,因此每段独立存在可设定温度即视为该段通过;
        # 箱级温度区间为各段可设定温度段的合并结果。
        segment_checks: list[dict[str, Any]] = []
        first_failed: dict[str, Any] | None = None
        leg_ivs: list[_Iv] = []
        for seg in box.segments:
            leg_segments = _leg_segments(box.feasible, seg)
            if leg_segments:
                leg_ivs.extend(leg_segments)
            leg_matched = [
                z.name
                for z in seg.zones
                if box.feasible.intersect(z.iv) is not None
            ]
            widest_leg = max(leg_segments, key=lambda s: s.hi - s.lo) if leg_segments else None
            check: dict[str, Any] = {
                "segment_no": seg.no,
                "name": seg.name,
                "hours": _r(seg.hours),
                "ok": bool(leg_segments),
                "matched_zones": leg_matched,
                "temperature_segments": [
                    {"t_min": _r(s.lo), "t_max": _r(s.hi)} for s in leg_segments
                ],
                "temperature_range": (
                    {
                        "t_min": _r(leg_segments[0].lo),
                        "t_max": _r(leg_segments[-1].hi),
                    }
                    if leg_segments
                    else None
                ),
                "recommended_setpoint": (
                    _r((widest_leg.lo + widest_leg.hi) / 2)
                    if widest_leg is not None
                    else None
                ),
            }
            if not leg_segments:
                reason = (
                    f"箱内货物共同允许温区 "
                    f"[{_r(box.feasible.lo)}, {_r(box.feasible.hi)}]℃ "
                    f"与该段全部可用温区 "
                    f"({_fmt_names([z.name for z in seg.zones])})均无交集,"
                    f"该段无可用设定温度"
                )
                check["reason"] = reason
                if first_failed is None:
                    first_failed = {
                        "segment_no": seg.no,
                        "segment_name": seg.name,
                        "reason": reason,
                    }
            segment_checks.append(check)

        segments_out = _merge_segments(leg_ivs) if leg_ivs else []
        if segments_out:
            widest = max(segments_out, key=lambda s: s.hi - s.lo)
            recommended = _r((widest.lo + widest.hi) / 2)
            temp_range = {
                "t_min": _r(segments_out[0].lo),
                "t_max": _r(segments_out[-1].hi),
            }
        else:
            # 正常流程装箱阶段已保证至少一段可走(单段模式下即全部段);
            # 兜底保留共同交集,并交由 first_failed 标记不可运输
            recommended = _r((box.feasible.lo + box.feasible.hi) / 2)
            temp_range = {
                "t_min": _r(box.feasible.lo),
                "t_max": _r(box.feasible.hi),
            }
            segments_out = [box.feasible]
        matched = [
            z.name
            for z in box.zones
            if box.feasible.intersect(z.iv) is not None
        ]

        if first_failed is not None:
            segment_failures.append(
                {
                    "box_no": box.index,
                    "segment_no": first_failed["segment_no"],
                    "segment_name": first_failed["segment_name"],
                    "reason": first_failed["reason"],
                    "affected_batches": [
                        {"batch_no": it.batch_no, "name": it.name}
                        for it in box.items
                    ],
                }
            )

        items_out = []
        for it in box.items:
            loaded_units += it.units
            loaded_volume += it.volume
            items_out.append(
                {
                    "batch_no": it.batch_no,
                    "name": it.name,
                    "units": it.units,
                    "volume": _r(it.volume),
                }
            )
        out_boxes.append(
            {
                "box_no": box.index,
                "temperature_range": {
                    "t_min": _r(segments_out[0].lo),
                    "t_max": _r(segments_out[-1].hi),
                },
                "temperature_segments": [
                    {"t_min": _r(s.lo), "t_max": _r(s.hi)} for s in segments_out
                ],
                "recommended_setpoint": recommended,
                "matched_zones": matched,
                "used_volume": _r(box.used),
                "capacity": _r(box.capacity),
                "utilization": _r(min(1.0, box.used / box.capacity)),
                "transportable": first_failed is None,
                "first_failed_segment": first_failed,
                "segment_checks": segment_checks,
                "items": items_out,
            }
        )

    total_units = sum(c.units for c in batches)
    total_volume = sum(c.total_volume for c in batches)
    unloaded_units = sum(u["units"] for u in unloaded)

    return {
        "summary": {
            "total_cargo_units": total_units,
            "loaded_units": loaded_units,
            "unloaded_units": unloaded_units,
            "total_cargo_volume": _r(total_volume),
            "loaded_volume": _r(loaded_volume),
            "unloaded_volume": _r(total_volume - loaded_volume),
            "boxes_used": len(boxes),
            "max_boxes": max_boxes,
            "all_loaded": unloaded_units == 0,
            "transportable": unloaded_units == 0 and not segment_failures,
            "segment_count": len(segments),
            "total_transport_hours": _r(transport_hours),
            "segmented_transport": segmented,
        },
        "transport_segments": [
            {
                "segment_no": seg.no,
                "name": seg.name,
                "hours": _r(seg.hours),
                "zones": [
                    {"name": z.name, "t_min": _r(z.iv.lo), "t_max": _r(z.iv.hi)}
                    for z in seg.zones
                ],
            }
            for seg in segments
        ],
        "boxes": out_boxes,
        "segment_failures": segment_failures,
        "unloaded": unloaded,
        "volume_unit": volume_unit,
    }
