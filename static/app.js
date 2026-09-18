/* 冷链装箱温控规划器前端逻辑(无第三方依赖) */
"use strict";

const $ = (id) => document.getElementById(id);

/* ---------------- 示例数据 ---------------- */
const SAMPLE = {
  transport_hours: 24,
  box_capacity: 12,
  max_boxes: 20,
  volume_unit: "m³",
  zones: [
    { name: "深冷区", t_min: -30, t_max: -18 },
    { name: "冷冻区", t_min: -18, t_max: -2 },
    { name: "冷藏区", t_min: 0, t_max: 8 },
    { name: "常温区", t_min: 15, t_max: 25 },
  ],
  // 多式联运:产地冷库 → 公路干线 → 铁路冷链 → 末端配送
  segments: [
    {
      name: "产地冷库",
      hours: 6,
      zones: [
        { name: "深冷区", t_min: -30, t_max: -18 },
        { name: "冷冻区", t_min: -18, t_max: -2 },
        { name: "冷藏区", t_min: 0, t_max: 8 },
        { name: "常温区", t_min: 15, t_max: 25 },
      ],
    },
    {
      name: "公路干线",
      hours: 10,
      zones: [
        { name: "深冷区", t_min: -28, t_max: -18 },
        { name: "冷冻区", t_min: -18, t_max: -2 },
        { name: "冷藏区", t_min: 0, t_max: 8 },
      ],
    },
    {
      name: "铁路冷链",
      hours: 5,
      zones: [
        { name: "冷冻区", t_min: -20, t_max: -4 },
        { name: "冷藏区", t_min: 2, t_max: 8 },
      ],
    },
    {
      name: "末端配送",
      hours: 3,
      zones: [
        { name: "冷冻区", t_min: -15, t_max: 0 },
        { name: "冷藏区", t_min: 0, t_max: 10 },
        { name: "常温区", t_min: 10, t_max: 28 },
      ],
    },
  ],
  cargoes: [
    { name: "冷冻牛排", units: 30, unit_volume: 0.8, t_min: -22, t_max: -15, max_transport_hours: "" },
    { name: "冰淇淋(末端无深冷)", units: 24, unit_volume: 0.5, t_min: -28, t_max: -18, max_transport_hours: 48 },
    { name: "三文鱼刺身", units: 18, unit_volume: 0.4, t_min: -2, t_max: 2, max_transport_hours: 36 },
    { name: "巴氏鲜奶", units: 40, unit_volume: 0.25, t_min: 2, t_max: 6, max_transport_hours: "" },
    { name: "鲜切水果", units: 20, unit_volume: 0.3, t_min: 2, t_max: 8, max_transport_hours: 20 },
    { name: "冷冻饺子", units: 26, unit_volume: 0.6, t_min: -18, t_max: -5, max_transport_hours: "" },
    { name: "巧克力(全程无常温段)", units: 30, unit_volume: 0.2, t_min: 15, t_max: 22, max_transport_hours: "" },
    { name: "温控疫苗(最长运输 12h)", units: 12, unit_volume: 0.15, t_min: 2, t_max: 8, max_transport_hours: 12 },
    { name: "热带水果(温区缺失)", units: 10, unit_volume: 0.4, t_min: 10, t_max: 14, max_transport_hours: "" },
  ],
};

/* ---------------- 动态行(温区 / 货物) ---------------- */
function addRow(tbody, cells) {
  const tr = document.createElement("tr");
  cells.forEach((html) => {
    const td = document.createElement("td");
    td.innerHTML = html;
    tr.appendChild(td);
  });
  tbody.appendChild(tr);
  tr.querySelector("input")?.focus();
  return tr;
}

const zoneCell = (v = "", ph = "", type = "text") =>
  `<input type="${type}" value="${v ?? ""}" placeholder="${ph}" ${type === "number" ? 'step="any"' : ""} />`;

function addZoneRowTo(tbody, z = {}) {
  return addRow(tbody, [
    zoneCell(z.name, "如 冷藏区"),
    zoneCell(z.t_min ?? "", "-18", "number"),
    zoneCell(z.t_max ?? "", "8", "number"),
    '<button type="button" class="btn btn-del">删除</button>',
  ]);
}

const addZoneRow = (z = {}) => addZoneRowTo($("zoneRows"), z);

function addCargoRow(c = {}) {
  addRow($("cargoRows"), [
    zoneCell(c.name, "批次名称"),
    zoneCell(c.units ?? "", "件数", "number"),
    zoneCell(c.unit_volume ?? "", "单件体积", "number"),
    zoneCell(c.t_min ?? "", "下限", "number"),
    zoneCell(c.t_max ?? "", "上限", "number"),
    `<input type="number" step="any" min="0" value="${c.max_transport_hours ?? ""}" placeholder="不限" />`,
    '<button type="button" class="btn btn-del">删除</button>',
  ]);
}

$("btnAddZone").addEventListener("click", () => addZoneRow());
$("btnAddCargo").addEventListener("click", () => addCargoRow());

/* ---------------- 动态运输段卡片 ---------------- */
function renumberSegments() {
  [...$("segmentList").querySelectorAll(".seg-card")].forEach((card, i) => {
    card.querySelector(".seg-no").textContent = `第 ${i + 1} 段`;
  });
  updateSegTotalHint();
}

function addSegmentCard(seg = {}) {
  const card = document.createElement("div");
  card.className = "seg-card";
  card.innerHTML = `
    <div class="seg-head">
      <span class="seg-no">运输段</span>
      <input class="seg-name" type="text" placeholder="运输段名称,如 公路干线" value="${seg.name ?? ""}" />
      <label class="seg-hours">时长 (h)
        <input class="seg-hours-input" type="number" min="0" step="0.5" value="${seg.hours ?? ""}" />
      </label>
      <button type="button" class="btn btn-del seg-del">删除本段</button>
    </div>
    <div class="table-wrap">
      <table class="editable seg-zones">
        <thead>
          <tr><th>本段可用温区名称</th><th>下限 ℃</th><th>上限 ℃</th><th></th></tr>
        </thead>
        <tbody></tbody>
      </table>
    </div>
    <button type="button" class="btn btn-small seg-add-zone">+ 添加本段温区</button>`;
  const tbody = card.querySelector("tbody");
  const zones = seg.zones && seg.zones.length ? seg.zones : [{}];
  zones.forEach((z) => addZoneRowTo(tbody, z));
  card.querySelector(".seg-add-zone").addEventListener("click", () => {
    addZoneRowTo(tbody, {});
  });
  card.querySelector(".seg-del").addEventListener("click", () => {
    card.remove();
    renumberSegments();
  });
  card.querySelector(".seg-hours-input").addEventListener("input", updateSegTotalHint);
  $("segmentList").appendChild(card);
  renumberSegments();
  return card;
}

$("btnAddSegment").addEventListener("click", () => addSegmentCard());

document.addEventListener("click", (e) => {
  if (e.target.classList.contains("btn-del")) {
    // 运输段卡片内的删除按钮只删行,卡片本身由 .seg-del 处理
    const tr = e.target.closest("tr");
    if (tr) tr.remove();
  }
});

/* ---------------- 模式切换 ---------------- */
let segMode = false;

function applyMode() {
  segMode = $("segMode").checked;
  $("singleZoneBox").hidden = segMode;
  $("segmentBox").hidden = !segMode;
  $("transportHours").disabled = segMode;
  $("segTotalHint").hidden = !segMode;
  $("transportHoursLabel").classList.toggle("disabled-label", segMode);
  if (segMode && !$("segmentList").children.length) addSegmentCard();
  updateSegTotalHint();
}

function updateSegTotalHint() {
  if (!segMode) return;
  let total = 0;
  let blank = false;
  [...$("segmentList").querySelectorAll(".seg-card")].forEach((card) => {
    const v = card.querySelector(".seg-hours-input").value;
    if (v === "") blank = true;
    else total += Number(v) || 0;
  });
  $("segTotalHint").textContent =
    `各段时长合计：${total}h（提交时作为运输总时长${blank ? ",尚有段未填时长" : ""}）`;
}

$("segMode").addEventListener("change", applyMode);

/* ---------------- 读取/校验输入 ---------------- */
function num(v, label, rowName) {
  if (v === "" || v === null || Number.isNaN(Number(v)))
    throw new Error(`${rowName ? `「${rowName}」的` : ""}${label}必须填写数字`);
  return Number(v);
}

function readRows(tbody, labels) {
  const out = [];
  [...tbody.querySelectorAll("tr")].forEach((tr, i) => {
    const inputs = [...tr.querySelectorAll("input")];
    const rowName = inputs[0].value || `第 ${i + 1} 行`;
    const obj = {};
    inputs.forEach((inp, idx) => {
      if (idx >= labels.length) return;
      const key = labels[idx].key;
      if (labels[idx].numeric) obj[key] = num(inp.value, labels[idx].label, rowName);
      else obj[key] = inp.value.trim();
    });
    out.push(obj);
  });
  return out;
}

const ZONE_LABELS = [
  { key: "name", label: "名称" },
  { key: "t_min", label: "下限", numeric: true },
  { key: "t_max", label: "上限", numeric: true },
];

function readZones(tbody, defaultPrefix) {
  return readRows(tbody, ZONE_LABELS).map((z, i) => ({
    ...z,
    name: z.name || `${defaultPrefix} ${i + 1}`,
  }));
}

function collectSegments() {
  const cards = [...$("segmentList").querySelectorAll(".seg-card")];
  const segments = [];
  cards.forEach((card, i) => {
    const segNo = i + 1;
    const name = card.querySelector(".seg-name").value.trim() || `运输段 ${segNo}`;
    const hoursRaw = card.querySelector(".seg-hours-input").value;
    if (hoursRaw === "") throw new Error(`请填写运输段「${name}」的时长`);
    const hours = Number(hoursRaw);
    if (!(hours > 0)) throw new Error(`运输段「${name}」时长必须大于 0`);
    let zones;
    try {
      zones = readZones(card.querySelector("tbody"), "温区");
    } catch (e) {
      throw new Error(`运输段「${name}」:${e.message}`);
    }
    if (zones.length === 0)
      throw new Error(`运输段「${name}」至少需要一个可用温区`);
    for (const z of zones)
      if (z.t_min > z.t_max)
        throw new Error(`运输段「${name}」温区「${z.name}」下限不能高于上限`);
    segments.push({ name, hours, zones });
  });
  return segments;
}

function collectInput() {
  let zones = null;
  let segments = null;
  let transportHours = 0;

  if (segMode) {
    if (!$("segmentList").children.length)
      throw new Error("请至少添加一个运输段");
    segments = collectSegments();
    transportHours = segments.reduce((s, x) => s + x.hours, 0);
  } else {
    zones = readZones($("zoneRows"), "温区");
    if (zones.length === 0) throw new Error("请至少添加一个允许温区");
    for (const z of zones)
      if (z.t_min > z.t_max) throw new Error(`温区「${z.name}」下限不能高于上限`);
    transportHours = num($("transportHours").value, "运输时长");
  }

  const cargoes = readRows($("cargoRows"), [
    { key: "name", label: "名称" },
    { key: "units", label: "件数", numeric: true },
    { key: "unit_volume", label: "单件体积", numeric: true },
    { key: "t_min", label: "温度下限", numeric: true },
    { key: "t_max", label: "温度上限", numeric: true },
    { key: "max_transport_hours", label: "最长运输时长", numeric: false },
  ]).map((c, i) => ({
    ...c,
    name: c.name || `批次 ${i + 1}`,
    max_transport_hours: c.max_transport_hours === "" ? null : Number(c.max_transport_hours),
  }));

  if (cargoes.length === 0) throw new Error("请至少添加一批货物");
  for (const c of cargoes) {
    if (c.units <= 0) throw new Error(`货物「${c.name}」件数必须大于 0`);
    if (c.unit_volume <= 0) throw new Error(`货物「${c.name}」单件体积必须大于 0`);
    if (c.t_min > c.t_max) throw new Error(`货物「${c.name}」温度下限不能高于上限`);
    if (c.max_transport_hours !== null && c.max_transport_hours < 0)
      throw new Error(`货物「${c.name}」最长运输时长不能为负`);
  }

  return {
    transport_hours: transportHours,
    box_capacity: num($("boxCapacity").value, "单箱容量"),
    max_boxes: num($("maxBoxes").value, "最大箱数"),
    volume_unit: $("volumeUnit").value.trim() || "体积单位",
    zones,
    segments,
    cargoes,
  };
}

/* ---------------- 渲染结果 ---------------- */
const fmt = (v) => Number(v).toLocaleString("zh-CN", { maximumFractionDigits: 2 });

const rangeText = (segs) =>
  segs
    .map((s) =>
      s.t_min === s.t_max ? `${fmt(s.t_min)}℃` : `${fmt(s.t_min)}~${fmt(s.t_max)}℃`
    )
    .join(" 或 ");

function renderSummary(s, unit) {
  const statusCls = s.transportable ? "ok" : "bad";
  const badge = s.transportable
    ? '<span class="badge badge-ok">✓ 全程可运输</span>'
    : '<span class="badge badge-bad">⚠ 不可运输(存在冲突或分段不兼容)</span>';
  const loadBadge = s.all_loaded
    ? '<span class="badge badge-ok">✓ 全部装载</span>'
    : '<span class="badge badge-bad">⚠ 存在未装载货物</span>';
  const segNote = s.segmented_transport
    ? `${s.segment_count} 个运输段 · `
    : "";
  $("summary").innerHTML = `
    <div class="stat ${statusCls}"><div class="k">可运输判定</div>
      <div class="v">${badge}</div></div>
    <div class="stat ${s.all_loaded ? "ok" : "bad"}"><div class="k">装载状态</div>
      <div class="v">${loadBadge}</div></div>
    <div class="stat"><div class="k">已装 / 总件数</div><div class="v">${fmt(s.loaded_units)} / ${fmt(s.total_cargo_units)}</div></div>
    <div class="stat"><div class="k">已装 / 总体积</div><div class="v">${fmt(s.loaded_volume)} / ${fmt(s.total_cargo_volume)} ${unit}</div></div>
    <div class="stat"><div class="k">运输总时长</div><div class="v">${fmt(s.total_transport_hours)}h <small class="muted">${segNote}共 ${s.boxes_used}/${s.max_boxes} 箱</small></div></div>
    <div class="stat ${s.unloaded_units ? "bad" : "ok"}"><div class="k">未装件数</div><div class="v">${fmt(s.unloaded_units)}</div></div>
  `;
}

function renderSegmentChecks(box) {
  if (!box.segment_checks || box.segment_checks.length <= 1) return "";
  const rows = box.segment_checks
    .map((c) => {
      const cls = c.ok ? "seg-ok" : "seg-bad";
      const icon = c.ok ? "✓" : "⛔";
      const detail = c.ok
        ? `可设定 ${rangeText(c.temperature_segments)} · 温区 ${c.matched_zones.map(escapeHtml).join("、") || "—"}`
        : escapeHtml(c.reason);
      return `<li class="${cls}"><span class="seg-ic">${icon}</span>
        <span class="seg-name">第 ${c.segment_no} 段 · ${escapeHtml(c.name)}（${fmt(c.hours)}h）</span>
        <span class="seg-detail">${detail}</span></li>`;
    })
    .join("");
  return `<ul class="seg-checks">${rows}</ul>`;
}

function renderBox(box, unit) {
  const segText = rangeText(box.temperature_segments);
  const items = box.items
    .map(
      (it) => `<tr>
        <td>#${it.batch_no} ${escapeHtml(it.name)}</td>
        <td class="num">${fmt(it.units)} 件</td>
        <td class="num">${fmt(it.volume)} ${unit}</td>
      </tr>`
    )
    .join("");
  const pct = Math.round(box.utilization * 100);
  const card = document.createElement("div");
  card.className = "box-card" + (box.transportable ? "" : " box-bad");
  const mark = box.transportable
    ? '<span class="badge badge-ok">全程通过</span>'
    : `<span class="badge badge-bad">⛔ 卡在「${escapeHtml(box.first_failed_segment.segment_name)}」段</span>`;
  card.innerHTML = `
    <div class="box-head">
      <span class="box-title">📦 第 ${box.box_no} 箱 ${mark}</span>
      <span><span class="temp-chip">${fmt(box.temperature_range.t_min)} ~ ${fmt(box.temperature_range.t_max)} ℃</span>
      <span class="temp-segments">全程可设定: ${segText}</span></span>
    </div>
    <div class="meta-line">
      推荐设定温度 <strong>${fmt(box.recommended_setpoint)}℃</strong> ·
      匹配温区: ${box.matched_zones.map(escapeHtml).join("、")} ·
      容量 ${fmt(box.used_volume)} / ${fmt(box.capacity)} ${unit}（${pct}%）
    </div>
    ${renderSegmentChecks(box)}
    <div class="cap-bar"><i style="width:${pct}%"></i></div>
    <table class="items">
      <thead><tr><th>装载批次</th><th class="num">件数</th><th class="num">占用体积</th></tr></thead>
      <tbody>${items}</tbody>
    </table>`;
  $("boxes").appendChild(card);
}

function renderSegmentFailures(failures) {
  const wrap = $("segmentFailures");
  wrap.innerHTML = "";
  if (!failures || !failures.length) {
    $("segFailTitle").hidden = true;
    return;
  }
  $("segFailTitle").hidden = false;
  failures.forEach((f) => {
    const div = document.createElement("div");
    div.className = "unloaded-item";
    const batches = f.affected_batches
      .map((b) => `#${b.batch_no} ${escapeHtml(b.name)}`)
      .join("、");
    div.innerHTML = `
      <div class="u-title">⛔ 第 ${f.box_no} 箱在第 ${f.segment_no} 段「${escapeHtml(f.segment_name)}」首次不兼容</div>
      <div class="u-reason">原因：${escapeHtml(f.reason)}</div>
      <div class="u-reason">受影响批次：${batches}</div>`;
    wrap.appendChild(div);
  });
}

function renderUnloaded(unloaded, unit) {
  const wrap = $("unloaded");
  wrap.innerHTML = "";
  if (!unloaded.length) {
    $("unloadedTitle").hidden = true;
    return;
  }
  $("unloadedTitle").hidden = false;
  unloaded.forEach((u) => {
    const div = document.createElement("div");
    div.className = "unloaded-item";
    const segLine = u.failed_segment_name
      ? `<div class="u-reason">首次不兼容运输段：第 ${u.failed_segment_no} 段「${escapeHtml(u.failed_segment_name)}」</div>`
      : "";
    div.innerHTML = `
      <div class="u-title">⛔ #${u.batch_no} ${escapeHtml(u.name)} — 未能装载 ${fmt(u.units)} 件（${fmt(u.volume)} ${unit}）</div>
      ${segLine}
      <div class="u-reason">原因：${escapeHtml(u.reason)}</div>`;
    wrap.appendChild(div);
  });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (ch) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

/* ---------------- 提交 ---------------- */
async function runPlan() {
  const btn = $("btnPlan");
  $("errorBox").hidden = true;
  let payload;
  try {
    payload = collectInput();
  } catch (e) {
    showError(e.message);
    return;
  }
  btn.disabled = true;
  btn.textContent = "规划中…";
  try {
    const resp = await fetch("/api/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || `规划失败（HTTP ${resp.status}）`);
    renderResult(data);
  } catch (e) {
    showError(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "▶ 生成分箱方案";
  }
}

function renderResult(data) {
  $("resultPlaceholder").hidden = true;
  $("resultView").hidden = false;
  renderSummary(data.summary, data.volume_unit);
  $("boxCount").textContent = `（共 ${data.boxes.length} 箱）`;
  $("boxes").innerHTML = "";
  data.boxes.forEach((b) => renderBox(b, data.volume_unit));
  renderSegmentFailures(data.segment_failures);
  renderUnloaded(data.unloaded, data.volume_unit);
}

function showError(msg) {
  $("resultPlaceholder").hidden = true;
  $("resultView").hidden = true;
  $("errorBox").hidden = false;
  $("errorBox").textContent = "⚠ " + msg;
}

$("btnPlan").addEventListener("click", runPlan);

$("btnSample").addEventListener("click", () => {
  $("boxCapacity").value = SAMPLE.box_capacity;
  $("maxBoxes").value = SAMPLE.max_boxes;
  $("volumeUnit").value = SAMPLE.volume_unit;
  $("transportHours").value = SAMPLE.transport_hours;
  $("zoneRows").innerHTML = "";
  SAMPLE.zones.forEach(addZoneRow);
  $("cargoRows").innerHTML = "";
  SAMPLE.cargoes.forEach(addCargoRow);
  $("segmentList").innerHTML = "";
  SAMPLE.segments.forEach((s) => addSegmentCard(s));
  // 默认载入分段模式以展示新能力;取消勾选即回到单一温区(旧版)表单
  $("segMode").checked = true;
  applyMode();
  $("errorBox").hidden = true;
  $("resultView").hidden = true;
  $("resultPlaceholder").hidden = false;
});

/* ---------------- 初始空行 ---------------- */
addZoneRow({ name: "冷藏区", t_min: 0, t_max: 8 });
addCargoRow({ name: "", units: "", unit_volume: "", t_min: "", t_max: "" });
applyMode();
