/**
 * FH6 AutoBot — Web UI Client
 * ============================
 * WebSocket 连接 + 状态更新 + 日志渲染
 */

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
    badge.textContent = "⚡ Connected";
    badge.className = "badge badge-connected";
});

socket.on("disconnect", () => {
    const badge = document.getElementById("connection-status");
    badge.textContent = "⚡ Disconnected";
    badge.className = "badge badge-disconnected";
});

// ==========================================
// 状态更新
// ==========================================
socket.on("state_update", (data) => {
    document.getElementById("current-state").textContent = formatState(data.current_state);
    document.getElementById("loop-count").textContent = data.loop_count || 0;
    document.getElementById("skill-points").textContent = data.skill_points || 0;

    if (data.uptime_seconds) {
        document.getElementById("uptime").textContent = formatUptime(data.uptime_seconds);
    }

    // Update stage progress
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
    container.innerHTML = '<div class="log-empty">Logs cleared</div>';
    logCount = 0;
    document.getElementById("log-count").textContent = "0 entries";
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

    // 移除空状态提示
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
    document.getElementById("log-count").textContent = `${logCount} entries`;

    // 自动滚动到底部
    if (autoScroll) {
        container.scrollTop = container.scrollHeight;
    }

    // 限制 DOM 节点数量（保留最新 1000 条）
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
        IDLE: "Idle",
        STATE_FARM_POINTS: "Farm Points",
        STATE_BUY_CARS: "Buy Cars",
        STATE_UPGRADE_CARS: "Upgrade",
        STATE_TRASH_CARS: "Sell Cars",
    };
    return map[state] || state || "Idle";
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
