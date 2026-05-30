/**
 * FH6 AutoBot — Web UI Client
 * ============================
 * WebSocket + i18n + 状态更新 + 日志渲染
 */

// ==========================================
// i18n 双语系统
// ==========================================
const GUIDE_EN = `
<h3>🖥️ Prerequisites</h3>
<ol>
    <li><strong>Python 3.10+</strong></li>
    <li><strong>Tesseract OCR</strong> — <a href="https://github.com/UB-Mannheim/tesseract/releases" target="_blank">Download</a> (check "Add to PATH")</li>
    <li><strong>ViGEmBus</strong> driver — <a href="https://github.com/ViGEm/ViGEmBus/releases" target="_blank">Download</a> (restart required)</li>
    <li>Game must run in <strong>Windowed</strong> or <strong>Borderless Windowed</strong> mode</li>
    <li>Recommended resolution: <strong>2560×1440</strong></li>
</ol>
<h3>🎮 In-Game Preparation</h3>
<ol>
    <li><strong>Set language to English</strong> (OCR depends on English text)</li>
    <li><strong>Buy main car</strong>: 1998 Subaru Impreza 22B-STI Version</li>
    <li><strong>Install S2 tune</strong>: Any S2-class tune (PI badge = blue)</li>
    <li><strong>Favorite blueprint</strong>: Share code <code>890169683</code></li>
</ol>
<p class="warn">⚠️ The S2 blue PI badge is how the bot distinguishes "keep" vs "deletable" cars.</p>
<h3>🚀 How to Use</h3>
<ol>
    <li>Select a <strong>Start Stage</strong> from the dropdown above</li>
    <li>Optionally check <strong>Auto Loop</strong> for continuous cycling</li>
    <li>Click <strong>▶ Start Bot</strong> — the bot runs in background</li>
    <li>Monitor progress via the Live Logs and status cards</li>
    <li>Click <strong>⏹ Stop Bot</strong> to stop at any time</li>
</ol>
<h3>📊 Stage Descriptions</h3>
<table>
    <tr><th>Stage</th><th>Description</th></tr>
    <tr><td>🏎️ Farm</td><td>OCR scans skill points → auto-enters EventLab to farm up to 999</td></tr>
    <tr><td>🛒 Buy</td><td>Navigate to Car Collection → batch-purchase 33 Subaru Imprezas</td></tr>
    <tr><td>⚡ Upgrade</td><td>Enter garage → select each NEW Impreza → spend skill points</td></tr>
    <tr><td>🗑️ Sell</td><td>Enter garage → batch-remove upgraded Imprezas (keep S2 main car)</td></tr>
</table>`;

const GUIDE_ZH = `
<h3>🖥️ 前置要求</h3>
<ol>
    <li><strong>Python 3.10+</strong></li>
    <li><strong>Tesseract OCR</strong> — <a href="https://github.com/UB-Mannheim/tesseract/releases" target="_blank">下载安装</a>（安装时勾选 Add to PATH）</li>
    <li><strong>ViGEmBus</strong> 驱动 — <a href="https://github.com/ViGEm/ViGEmBus/releases" target="_blank">下载安装</a>（安装后需重启）</li>
    <li>游戏需运行在 <strong>窗口化</strong> 或 <strong>无边框窗口</strong> 模式</li>
    <li>建议分辨率：<strong>2560×1440</strong></li>
</ol>
<h3>🎮 游戏内准备</h3>
<ol>
    <li><strong>游戏语言设置为英文</strong>（OCR 识别依赖英文文本）</li>
    <li><strong>购买主力车</strong>：1998 Subaru Impreza 22B-STI Version</li>
    <li><strong>安装 S2 级改装</strong>：任意 S2 改装方案（PI 徽章显示蓝色）</li>
    <li><strong>收藏蓝图</strong>：搜索代码 <code>890169683</code></li>
</ol>
<p class="warn">⚠️ 主力车的 S2 蓝色 PI 徽章是程序区分「保留车」与「可删除车」的关键依据。</p>
<h3>🚀 使用方法</h3>
<ol>
    <li>从上方下拉框选择 <strong>起始阶段</strong></li>
    <li>如需持续循环，勾选 <strong>自动循环</strong></li>
    <li>点击 <strong>▶ 启动</strong> — Bot 在后台运行</li>
    <li>通过实时日志和状态卡片监控进度</li>
    <li>点击 <strong>⏹ 停止</strong> 随时中止</li>
</ol>
<h3>📊 阶段说明</h3>
<table>
    <tr><th>阶段</th><th>描述</th></tr>
    <tr><td>🏎️ 刷点</td><td>OCR 扫描技能点 → 自动进入 EventLab 刷满 999</td></tr>
    <tr><td>🛒 买车</td><td>导航至 Car Collection → 批量购买 33 辆 Subaru Impreza</td></tr>
    <tr><td>⚡ 加点</td><td>进入车库 → 逐辆选择 NEW 标签 Impreza → 消耗技能点</td></tr>
    <tr><td>🗑️ 卖车</td><td>进入车库 → 批量移除已升级 Impreza（保留 S2 主力车）</td></tr>
</table>`;

const I18N = {
    en: {
        subtitle: "A Never-Ending AFK Farming Machine",
        connected: "⚡ Connected",
        disconnected: "⚡ Disconnected",
        currentStage: "Current Stage",
        loopCount: "Loop Count",
        uptime: "Uptime",
        superWheelspins: "Super Wheelspins",
        stageFarm: "Farm",
        stageBuy: "Buy",
        stageUpgrade: "Upgrade",
        stageSell: "Sell",
        startStage: "Start Stage",
        optFarm: "🏎️ Farm Skill Points",
        optBuy: "🛒 Buy Cars",
        optUpgrade: "⚡ Upgrade Cars",
        optSell: "🗑️ Sell Cars",
        autoLoop: "Auto Loop (4-stage cycle)",
        skipBuy: "Skip Buy Stage",
        btnStart: "▶ Start Bot",
        btnStop: "⏹ Stop Bot",
        btnClear: "🗑 Clear Logs",
        liveLogs: "📜 Live Logs",
        waitingConnection: "Waiting for connection...",
        logsCleared: "Logs cleared",
        entries: "entries",
        logsCopied: "✅ Logs copied to clipboard",
        reconnecting: "⚡ Reconnecting (#{n})...",
        stateIdle: "Idle",
        stateFarm: "Farm Points",
        stateBuy: "Buy Cars",
        stateUpgrade: "Upgrade",
        stateSell: "Sell Cars",
        guideTitle: "📖 Usage Guide",
        guideContent: GUIDE_EN,
        qrTitle: "📱 Scan to access on mobile",
    },
    zh: {
        subtitle: "一个永不落幕的全自动挂机工具",
        connected: "⚡ 已连接",
        disconnected: "⚡ 未连接",
        currentStage: "当前阶段",
        loopCount: "循环次数",
        uptime: "运行时长",
        superWheelspins: "超级轮盘",
        stageFarm: "刷点",
        stageBuy: "买车",
        stageUpgrade: "加点",
        stageSell: "卖车",
        startStage: "选择阶段",
        optFarm: "🏎️ 刷技能点",
        optBuy: "🛒 买车",
        optUpgrade: "⚡ 加技能点",
        optSell: "🗑️ 卖车",
        autoLoop: "自动循环（四阶段闭环）",
        skipBuy: "跳过买车阶段",
        btnStart: "▶ 启动",
        btnStop: "⏹ 停止",
        btnClear: "🗑 清空日志",
        liveLogs: "📜 实时日志",
        waitingConnection: "等待连接...",
        logsCleared: "日志已清空",
        entries: "条",
        logsCopied: "✅ 日志已复制到剪贴板",
        reconnecting: "⚡ 正在重连 (#{n})...",
        stateIdle: "空闲",
        stateFarm: "刷技能点",
        stateBuy: "买车",
        stateUpgrade: "加技能点",
        stateSell: "卖车",
        guideTitle: "📖 使用说明",
        guideContent: GUIDE_ZH,
        qrTitle: "📱 扫码手机访问",
    },
};

let currentLang = localStorage.getItem("fh6_lang") || "en";

function t(key) {
    return (I18N[currentLang] && I18N[currentLang][key]) || I18N.en[key] || key;
}

function applyI18n() {
    document.querySelectorAll("[data-i18n]").forEach((el) => {
        const key = el.getAttribute("data-i18n");
        el.textContent = t(key);
    });
    // Update HTML content blocks (guide)
    document.querySelectorAll("[data-i18n-html]").forEach((el) => {
        const key = el.getAttribute("data-i18n-html");
        el.innerHTML = t(key);
    });
    // Update connection badge
    const badge = document.getElementById("connection-status");
    if (socket.connected) {
        badge.textContent = t("connected");
    } else {
        badge.textContent = t("disconnected");
    }
    // Update log counter
    document.getElementById("log-count").textContent = `${logCount} ${t("entries")}`;
    // Re-render current state display
    const stateEl = document.getElementById("current-state");
    if (stateEl._rawState) {
        stateEl.textContent = formatState(stateEl._rawState);
    }
    // Highlight active language option
    document.querySelectorAll(".lang-option").forEach((el) => {
        el.classList.toggle("active", el.dataset.lang === currentLang);
    });
    // Sync custom dropdown display text
    if (typeof syncCustomSelect === "function") syncCustomSelect();
}

function setLang(lang) {
    currentLang = lang;
    localStorage.setItem("fh6_lang", currentLang);
    applyI18n();
    document.getElementById("lang-dropdown").classList.remove("open");
}

function toggleLangDropdown() {
    document.getElementById("lang-dropdown").classList.toggle("open");
}

// Close dropdowns on outside click
document.addEventListener("click", (e) => {
    const langWrap = document.querySelector(".lang-dropdown-wrap");
    if (langWrap && !langWrap.contains(e.target)) {
        document.getElementById("lang-dropdown").classList.remove("open");
    }
});

// ==========================================
// WebSocket 连接
// ==========================================
const socket = io({ transports: ["websocket", "polling"] });

let logCount = 0;
let autoScroll = true;
let botRunning = false;

// ==========================================
// 连接状态
// ==========================================
socket.on("connect", () => {
    const badge = document.getElementById("connection-status");
    badge.textContent = t("connected");
    badge.className = "badge badge-connected";
    badge.classList.remove("reconnecting");
});

socket.on("disconnect", () => {
    const badge = document.getElementById("connection-status");
    badge.textContent = t("disconnected");
    badge.className = "badge badge-disconnected";
});

socket.io.on("reconnect_attempt", (attempt) => {
    const badge = document.getElementById("connection-status");
    badge.textContent = t("reconnecting").replace("{n}", attempt);
    badge.className = "badge badge-disconnected reconnecting";
});

socket.io.on("reconnect", () => {
    const badge = document.getElementById("connection-status");
    badge.textContent = t("connected");
    badge.className = "badge badge-connected";
    badge.classList.remove("reconnecting");
});

// ==========================================
// 状态更新
// ==========================================
socket.on("state_update", (data) => {
    const stateEl = document.getElementById("current-state");
    stateEl._rawState = data.current_state;
    stateEl.textContent = formatState(data.current_state);
    document.getElementById("loop-count").textContent = data.loop_count || 0;
    document.getElementById("super-wheelspins").textContent = data.super_wheelspins || 0;

    if (data.uptime_seconds) {
        document.getElementById("uptime").innerHTML = formatUptime(data.uptime_seconds);
    }

    updateStageProgress(data.current_state);

});

socket.on("bot_status", (data) => {
    botRunning = data.running;
    updateButtons();
});

// ==========================================
// 日志流
// ==========================================
socket.on("log", (data) => {
    appendLog(data);
});

// ==========================================
// UI 交互
// ==========================================
function startBot() {
    const stageSelect = document.getElementById("stage-select");
    const skipBuy = document.getElementById("skip-buy").checked;
    const autoLoop = document.getElementById("auto-loop").checked;

    socket.emit("start_bot", {
        initial_state: stageSelect.value || null,
        skip_buy: skipBuy,
        loop: autoLoop,
    });

    botRunning = true;
    updateButtons();
}

function stopBot() {
    socket.emit("stop_bot");
    botRunning = false;
    updateButtons();
}

function clearLogs() {
    const container = document.getElementById("log-container");
    container.innerHTML = `<div class="log-empty">${t("logsCleared")}</div>`;
    logCount = 0;
    document.getElementById("log-count").textContent = `0 ${t("entries")}`;
}

function toggleAutoScroll() {
    autoScroll = !autoScroll;
    const btn = document.getElementById("btn-autoscroll");
    btn.classList.toggle("active", autoScroll);
    if (autoScroll) {
        const container = document.getElementById("log-container");
        container.scrollTop = container.scrollHeight;
    }
}

function copyLogs() {
    const entries = document.querySelectorAll(".log-entry");
    const text = Array.from(entries).map((el) => el.textContent).join("\n");
    navigator.clipboard.writeText(text).then(() => {
        showToast(t("logsCopied"));
    });
}

function downloadLogs() {
    const entries = document.querySelectorAll(".log-entry");
    const text = Array.from(entries).map((el) => el.textContent).join("\n");
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `fh6_autobot_${new Date().toISOString().slice(0, 19).replace(/:/g, "-")}.log`;
    a.click();
    URL.revokeObjectURL(url);
}

function showToast(msg) {
    let toast = document.getElementById("toast");
    if (!toast) {
        toast = document.createElement("div");
        toast.id = "toast";
        toast.style.cssText = `
            position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
            background: rgba(16,22,40,0.9); color: var(--neon-cyan);
            border: 1px solid rgba(0,229,200,0.3); border-radius: 8px;
            padding: 8px 20px; font-size: 0.82rem; backdrop-filter: blur(12px);
            box-shadow: 0 4px 20px rgba(0,0,0,0.4); z-index: 9999;
            opacity: 0; transition: opacity 0.3s;
        `;
        document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.style.opacity = "1";
    setTimeout(() => { toast.style.opacity = "0"; }, 2000);
}

function updateButtons() {
    document.getElementById("btn-start").disabled = botRunning;
    document.getElementById("btn-stop").disabled = !botRunning;
}

// ==========================================
// 日志渲染
// ==========================================
function appendLog(data) {
    const container = document.getElementById("log-container");

    const empty = container.querySelector(".log-empty");
    if (empty) empty.remove();

    const entry = document.createElement("div");
    entry.className = `log-entry log-${data.level || "info"}`;

    const time = data.timestamp ? formatTime(data.timestamp) : "";
    const level = (data.level || "info").toUpperCase();
    const msg = escapeHtml(data.msg || "");

    entry.innerHTML = `<span class="log-time">${time}</span><span class="log-level">[${level}]</span><span class="log-msg">${msg}</span>`;

    container.appendChild(entry);
    logCount++;
    document.getElementById("log-count").textContent = `${logCount} ${t("entries")}`;

    if (autoScroll) {
        container.scrollTop = container.scrollHeight;
    }

    // DOM performance: cap at 500 entries
    while (container.children.length > 500) {
        container.removeChild(container.firstChild);
    }
}

// ==========================================
// 阶段进度（completed / active / pending）
// ==========================================
const STAGE_ORDER = [
    "STATE_FARM_POINTS",
    "STATE_BUY_CARS",
    "STATE_UPGRADE_CARS",
    "STATE_TRASH_CARS",
];

const CONNECTOR_IDS = [
    "conn-farm-buy",
    "conn-buy-upgrade",
    "conn-upgrade-sell",
];

function updateStageProgress(state) {
    const activeIdx = STAGE_ORDER.indexOf(state);
    const stages = document.querySelectorAll(".progress-stage");

    stages.forEach((el, i) => {
        el.classList.remove("active", "completed");

        if (activeIdx < 0) return; // IDLE — all grey

        if (i < activeIdx) {
            el.classList.add("completed");
        } else if (i === activeIdx) {
            el.classList.add("active");
        }
        // i > activeIdx: remains pending (default grey)
    });

    // Update connectors
    CONNECTOR_IDS.forEach((id, i) => {
        const conn = document.getElementById(id);
        if (!conn) return;
        conn.classList.remove("completed", "flowing");

        if (activeIdx < 0) return;

        if (i < activeIdx) {
            conn.classList.add("completed");
        } else if (i === activeIdx) {
            conn.classList.add("flowing");
        }
    });
}

// ==========================================
// 格式化工具
// ==========================================
function formatState(state) {
    const map = {
        IDLE: "stateIdle",
        STATE_FARM_POINTS: "stateFarm",
        STATE_BUY_CARS: "stateBuy",
        STATE_UPGRADE_CARS: "stateUpgrade",
        STATE_TRASH_CARS: "stateSell",
    };
    const key = map[state];
    return key ? t(key) : state || t("stateIdle");
}

function formatUptime(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    const cls = botRunning ? "colon blink" : "colon";
    return `${pad(h)}<span class="${cls}">:</span>${pad(m)}<span class="${cls}">:</span>${pad(s)}`;
}

function pad(n) {
    return n.toString().padStart(2, "0");
}

function formatTime(ts) {
    const d = new Date(ts * 1000);
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}



// ==========================================
// 自动滚动检测
// ==========================================
document.getElementById("log-container").addEventListener("scroll", function () {
    const el = this;
    const isAtBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 50;
    if (autoScroll !== isAtBottom) {
        autoScroll = isAtBottom;
        document.getElementById("btn-autoscroll").classList.toggle("active", autoScroll);
    }
});

// ==========================================
// 定时刷新 uptime
// ==========================================
setInterval(() => {
    if (botRunning) {
        socket.emit("get_state");
    }
}, 5000);

// ==========================================
// QR Code
// ==========================================
let lanUrl = "";

socket.on("lan_url", (data) => {
    lanUrl = data.url;
    generateQR(lanUrl);
});

function generateQR(url) {
    const canvas = document.getElementById("qr-canvas");
    canvas.innerHTML = "";
    if (!url || typeof qrcode === "undefined") return;

    const qr = qrcode(0, "M");
    qr.addData(url);
    qr.make();
    canvas.innerHTML = qr.createImgTag(5, 0);
    document.getElementById("qr-url").textContent = url;
}

function toggleQR() {
    const popover = document.getElementById("qr-popover");
    popover.classList.toggle("pinned");
}

// ==========================================
// Custom Dropdown (自定义下拉菜单)
// ==========================================
const customSelect = document.getElementById("custom-select");
const selectTrigger = document.getElementById("select-trigger");
const selectDropdown = document.getElementById("select-dropdown");
const selectDisplay = document.getElementById("select-display");
const nativeSelect = document.getElementById("stage-select");

// Toggle open/close
selectTrigger.addEventListener("click", (e) => {
    e.stopPropagation();
    customSelect.classList.toggle("open");
});

// Close on click outside
document.addEventListener("click", () => {
    customSelect.classList.remove("open");
});

// Prevent dropdown clicks from closing
selectDropdown.addEventListener("click", (e) => {
    e.stopPropagation();
});

// Option selection
selectDropdown.querySelectorAll(".custom-select-option").forEach((opt) => {
    opt.addEventListener("click", () => {
        // Update visual state
        selectDropdown.querySelectorAll(".custom-select-option").forEach((o) => o.classList.remove("selected"));
        opt.classList.add("selected");

        // Update display text
        selectDisplay.textContent = opt.textContent;

        // Sync hidden native select
        nativeSelect.value = opt.dataset.value;
        nativeSelect.dispatchEvent(new Event("change"));

        // Close
        customSelect.classList.remove("open");
    });
});

// Sync custom dropdown display from native select value
function syncCustomSelect() {
    const val = nativeSelect.value;
    const match = selectDropdown.querySelector(`[data-value="${val}"]`);
    if (match) {
        selectDropdown.querySelectorAll(".custom-select-option").forEach((o) => o.classList.remove("selected"));
        match.classList.add("selected");
        selectDisplay.textContent = match.textContent;
    }
}

// ==========================================
// 本地状态持久化 (localStorage)
// ==========================================
const PREFS_KEY = "fh6_prefs";

function savePrefs() {
    const prefs = {
        stage: document.getElementById("stage-select").value,
        autoLoop: document.getElementById("auto-loop").checked,
        skipBuy: document.getElementById("skip-buy").checked,
    };
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
}

function restorePrefs() {
    try {
        const raw = localStorage.getItem(PREFS_KEY);
        if (!raw) return;
        const prefs = JSON.parse(raw);
        if (prefs.stage) {
            document.getElementById("stage-select").value = prefs.stage;
            syncCustomSelect();
        }
        if (prefs.autoLoop !== undefined) {
            document.getElementById("auto-loop").checked = prefs.autoLoop;
        }
        if (prefs.skipBuy !== undefined) {
            document.getElementById("skip-buy").checked = prefs.skipBuy;
        }
    } catch (_) {
        // ignore corrupt data
    }
}

// Listen for changes
document.getElementById("stage-select").addEventListener("change", savePrefs);
document.getElementById("auto-loop").addEventListener("change", savePrefs);
document.getElementById("skip-buy").addEventListener("change", savePrefs);

// ==========================================
// 初始化
// ==========================================
restorePrefs();
applyI18n();

// Auto-scroll button default active
document.getElementById("btn-autoscroll").classList.add("active");

// Typewriter effect for waiting text
(function typewriter() {
    const el = document.getElementById("typewriter-text");
    if (!el) return;
    const text = t("waitingConnection");
    let i = 0;
    function tick() {
        if (!el.parentElement) return; // removed by log entries
        el.textContent = text.slice(0, i + 1);
        i++;
        if (i < text.length) {
            setTimeout(tick, 60);
        }
    }
    tick();
})();
