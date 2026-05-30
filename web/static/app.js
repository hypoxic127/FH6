/**
 * FH6 AutoBot — Web UI Client
 * ============================
 * WebSocket + i18n + 状态更新 + 日志渲染
 */

// ==========================================
// i18n 双语系统
// ==========================================
const I18N = {
    en: {
        subtitle: "Forza Horizon 6 AFK Farming",
        connected: "⚡ Connected",
        disconnected: "⚡ Disconnected",
        currentStage: "Current Stage",
        loopCount: "Loop Count",
        uptime: "Uptime",
        skillPoints: "Skill Points",
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
        langToggle: "🌐 中文",
        stateIdle: "Idle",
        stateFarm: "Farm Points",
        stateBuy: "Buy Cars",
        stateUpgrade: "Upgrade",
        stateSell: "Sell Cars",
    },
    zh: {
        subtitle: "Forza Horizon 6 全自动挂机工具",
        connected: "⚡ 已连接",
        disconnected: "⚡ 未连接",
        currentStage: "当前阶段",
        loopCount: "循环次数",
        uptime: "运行时长",
        skillPoints: "技能点",
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
        langToggle: "🌐 English",
        stateIdle: "空闲",
        stateFarm: "刷技能点",
        stateBuy: "买车",
        stateUpgrade: "加技能点",
        stateSell: "卖车",
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
    // Update language toggle button text
    document.getElementById("lang-toggle").textContent = t("langToggle");
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
}

function toggleLang() {
    currentLang = currentLang === "en" ? "zh" : "en";
    localStorage.setItem("fh6_lang", currentLang);
    applyI18n();
}

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
});

socket.on("disconnect", () => {
    const badge = document.getElementById("connection-status");
    badge.textContent = t("disconnected");
    badge.className = "badge badge-disconnected";
});

// ==========================================
// 状态更新
// ==========================================
socket.on("state_update", (data) => {
    const stateEl = document.getElementById("current-state");
    stateEl._rawState = data.current_state;
    stateEl.textContent = formatState(data.current_state);
    document.getElementById("loop-count").textContent = data.loop_count || 0;
    document.getElementById("skill-points").textContent = data.skill_points || 0;

    if (data.uptime_seconds) {
        document.getElementById("uptime").textContent = formatUptime(data.uptime_seconds);
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

    while (container.children.length > 1000) {
        container.removeChild(container.firstChild);
    }
}

// ==========================================
// 阶段进度
// ==========================================
function updateStageProgress(state) {
    const stages = document.querySelectorAll(".progress-stage");
    stages.forEach((el) => {
        if (el.dataset.stage === state) {
            el.classList.add("active");
        } else {
            el.classList.remove("active");
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
    return `${pad(h)}:${pad(m)}:${pad(s)}`;
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
    autoScroll = el.scrollTop + el.clientHeight >= el.scrollHeight - 50;
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
// 初始化 i18n
// ==========================================
applyI18n();
