"use strict";

const $ = (selector) => document.querySelector(selector);
const state = {
    accessToken: sessionStorage.getItem("scrm_access_token"),
    refreshToken: sessionStorage.getItem("scrm_refresh_token"),
    userId: null,
    conversationId: null,
    sending: false,
};

const elements = {
    loginView: $("#login-view"), appView: $("#app-view"), loginForm: $("#login-form"),
    loginUser: $("#login-user"), loginPassword: $("#login-password"), loginButton: $("#login-button"),
    loginError: $("#login-error"), currentUser: $("#current-user"), userAvatar: $("#user-avatar"),
    conversationList: $("#conversation-list"), conversationTitle: $("#conversation-title"),
    messageList: $("#message-list"), emptyState: $("#empty-state"), chatForm: $("#chat-form"),
    messageInput: $("#message-input"), sendButton: $("#send-button"), settingsModal: $("#settings-modal"),
    passwordForm: $("#password-form"), passwordError: $("#password-error"), toast: $("#toast"),
};

function saveTokens(payload) {
    state.accessToken = payload.access_token;
    state.refreshToken = payload.refresh_token;
    sessionStorage.setItem("scrm_access_token", state.accessToken);
    sessionStorage.setItem("scrm_refresh_token", state.refreshToken);
}

function clearSession() {
    state.accessToken = null; state.refreshToken = null; state.userId = null; state.conversationId = null;
    sessionStorage.removeItem("scrm_access_token"); sessionStorage.removeItem("scrm_refresh_token");
}

async function responsePayload(response) {
    const type = response.headers.get("content-type") || "";
    return type.includes("application/json") ? response.json() : null;
}

async function refreshSession() {
    if (!state.refreshToken) return false;
    const response = await fetch("/api/v1/auth/refresh", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({refresh_token: state.refreshToken}),
    });
    if (!response.ok) { clearSession(); return false; }
    saveTokens(await response.json());
    return true;
}

async function api(path, options = {}, retry = true) {
    const headers = new Headers(options.headers || {});
    if (state.accessToken) headers.set("Authorization", `Bearer ${state.accessToken}`);
    const response = await fetch(path, {...options, headers});
    const refreshable = !path.endsWith("/auth/token") && !path.endsWith("/auth/refresh") && !path.endsWith("/auth/logout");
    if (response.status === 401 && retry && state.refreshToken && refreshable) {
        if (await refreshSession()) return api(path, options, false);
        showLogin();
    }
    const payload = await responsePayload(response);
    if (!response.ok) throw new Error(payload?.detail || `请求失败 (${response.status})`);
    return payload;
}

function showLogin(message = "") {
    elements.appView.hidden = true; elements.loginView.hidden = false;
    elements.loginError.textContent = message;
    elements.loginPassword.value = "";
}

function showWorkspace() {
    elements.loginView.hidden = true; elements.appView.hidden = false;
    elements.currentUser.textContent = state.userId;
    elements.userAvatar.textContent = (state.userId || "U").slice(0, 1).toUpperCase();
}

function toast(message) {
    elements.toast.textContent = message; elements.toast.hidden = false;
    clearTimeout(toast.timer); toast.timer = setTimeout(() => { elements.toast.hidden = true; }, 2800);
}

function formatTime(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "" : date.toLocaleString("zh-CN", {month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit"});
}

function shortConversation(id) { return `会话 ${id.slice(0, 10)}`; }

async function loadConversations() {
    const data = await api("/api/v1/conversations?limit=50&offset=0");
    elements.conversationList.replaceChildren();
    if (!data.items.length) {
        const empty = document.createElement("p"); empty.className = "sidebar-heading"; empty.textContent = "暂无会话";
        elements.conversationList.append(empty); return;
    }
    data.items.forEach((conversation) => {
        const wrapper = document.createElement("div"); wrapper.style.position = "relative";
        const button = document.createElement("button"); button.type = "button"; button.className = "conversation-item";
        if (conversation.conversation_id === state.conversationId) button.classList.add("active");
        const title = document.createElement("strong"); title.textContent = shortConversation(conversation.conversation_id);
        const time = document.createElement("span"); time.textContent = formatTime(conversation.updated_at);
        button.append(title, time); button.addEventListener("click", () => openConversation(conversation.conversation_id));
        const remove = document.createElement("button"); remove.type = "button"; remove.className = "delete-conversation";
        remove.textContent = "×"; remove.title = "删除会话";
        remove.addEventListener("click", (event) => { event.stopPropagation(); deleteConversation(conversation.conversation_id); });
        wrapper.append(button, remove); elements.conversationList.append(wrapper);
    });
}

function setEmpty(visible) { elements.emptyState.hidden = !visible; }

function appendMessage(role, content, pending = false) {
    setEmpty(false);
    const row = document.createElement("div"); row.className = `message-row ${role}${pending ? " pending" : ""}`;
    const avatar = document.createElement("div"); avatar.className = "message-avatar"; avatar.textContent = role === "user" ? "我" : "AI";
    const bubble = document.createElement("div"); bubble.className = "message-bubble";
    if (pending) {
        const dots = document.createElement("span"); dots.className = "typing-dots";
        dots.append(document.createElement("span"), document.createElement("span"), document.createElement("span")); bubble.append(dots);
    } else bubble.textContent = content;
    row.append(avatar, bubble); elements.messageList.append(row); elements.messageList.scrollTop = elements.messageList.scrollHeight;
    return row;
}

function newConversation() {
    state.conversationId = null; elements.conversationTitle.textContent = "新会话";
    elements.messageList.querySelectorAll(".message-row").forEach((node) => node.remove()); setEmpty(true);
    loadConversations().catch((error) => toast(error.message)); elements.messageInput.focus();
}

async function openConversation(conversationId) {
    try {
        const data = await api(`/api/v1/conversations/${encodeURIComponent(conversationId)}`);
        state.conversationId = conversationId; elements.conversationTitle.textContent = shortConversation(conversationId);
        elements.messageList.querySelectorAll(".message-row").forEach((node) => node.remove());
        data.messages.forEach((message) => appendMessage(message.role, message.content)); setEmpty(!data.messages.length);
        await loadConversations();
    } catch (error) { toast(error.message); }
}

async function deleteConversation(conversationId) {
    if (!window.confirm("确定删除这个会话及其持久记忆吗？此操作不可恢复。")) return;
    try {
        await api(`/api/v1/conversations/${encodeURIComponent(conversationId)}`, {method: "DELETE"});
        if (state.conversationId === conversationId) newConversation(); else await loadConversations();
        toast("会话已删除");
    } catch (error) { toast(error.message); }
}

async function sendMessage(message) {
    if (state.sending || !message.trim()) return;
    state.sending = true; elements.sendButton.disabled = true; appendMessage("user", message.trim());
    const pending = appendMessage("assistant", "", true);
    try {
        const body = {message: message.trim()}; if (state.conversationId) body.conversation_id = state.conversationId;
        const data = await api("/api/v1/chat", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
        pending.remove(); state.conversationId = data.conversation_id; elements.conversationTitle.textContent = shortConversation(data.conversation_id);
        appendMessage("assistant", data.content); await loadConversations();
    } catch (error) { pending.remove(); appendMessage("assistant", `请求未完成：${error.message}`); }
    finally { state.sending = false; elements.sendButton.disabled = false; elements.messageInput.focus(); }
}

elements.loginForm.addEventListener("submit", async (event) => {
    event.preventDefault(); elements.loginButton.disabled = true; elements.loginError.textContent = "";
    try {
        const body = new URLSearchParams({username: elements.loginUser.value.trim(), password: elements.loginPassword.value});
        const response = await fetch("/api/v1/auth/token", {method: "POST", headers: {"Content-Type": "application/x-www-form-urlencoded"}, body});
        const payload = await responsePayload(response); if (!response.ok) throw new Error(payload?.detail || "登录失败");
        saveTokens(payload); state.userId = (await api("/api/v1/auth/me")).user_id; showWorkspace(); newConversation();
    } catch (error) { elements.loginError.textContent = error.message; }
    finally { elements.loginButton.disabled = false; }
});

elements.chatForm.addEventListener("submit", (event) => {
    event.preventDefault(); const message = elements.messageInput.value; elements.messageInput.value = "";
    elements.messageInput.style.height = "auto"; sendMessage(message);
});
elements.messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); elements.chatForm.requestSubmit(); }
});
elements.messageInput.addEventListener("input", () => {
    elements.messageInput.style.height = "auto"; elements.messageInput.style.height = `${Math.min(elements.messageInput.scrollHeight, 180)}px`;
});
document.querySelectorAll("[data-prompt]").forEach((button) => button.addEventListener("click", () => sendMessage(button.dataset.prompt)));
$("#new-chat-button").addEventListener("click", newConversation);
$("#refresh-list-button").addEventListener("click", () => loadConversations().catch((error) => toast(error.message)));
$("#settings-button").addEventListener("click", () => { elements.settingsModal.hidden = false; $("#current-password").focus(); });
$("#close-settings").addEventListener("click", () => { elements.settingsModal.hidden = true; elements.passwordForm.reset(); });
elements.settingsModal.addEventListener("click", (event) => { if (event.target === elements.settingsModal) $("#close-settings").click(); });

elements.passwordForm.addEventListener("submit", async (event) => {
    event.preventDefault(); elements.passwordError.textContent = "";
    const currentPassword = $("#current-password").value, newPassword = $("#new-password").value;
    if (newPassword !== $("#confirm-password").value) { elements.passwordError.textContent = "两次输入的新密码不一致"; return; }
    try {
        await api("/api/v1/auth/change-password", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({current_password: currentPassword, new_password: newPassword})});
        clearSession(); elements.settingsModal.hidden = true; elements.passwordForm.reset(); showLogin("密码已更新，请使用新密码重新登录");
    } catch (error) { elements.passwordError.textContent = error.message; }
});

$("#logout-button").addEventListener("click", async () => {
    try {
        if (state.refreshToken) await fetch("/api/v1/auth/logout", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({refresh_token: state.refreshToken})});
    } finally { clearSession(); showLogin("已安全退出"); }
});

(async function restore() {
    if (!state.accessToken && !state.refreshToken) { showLogin(); return; }
    try {
        state.userId = (await api("/api/v1/auth/me")).user_id; showWorkspace(); newConversation();
    } catch { clearSession(); showLogin("登录状态已过期，请重新登录"); }
})();
