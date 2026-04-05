const { app, BrowserWindow, ipcMain, screen } = require("electron");
const path = require("path");

let widgetWin = null;
let chatWin   = null;

// ── Widget window — transparent always-on-top bunny ────────────────────────
function createWidget() {
  const { width, height } = screen.getPrimaryDisplay().workAreaSize;

  widgetWin = new BrowserWindow({
    width:          160,
    height:         210,
    x:              width  - 180,
    y:              height - 230,
    frame:          false,
    transparent:    true,
    alwaysOnTop:    true,
    resizable:      false,
    skipTaskbar:    true,
    hasShadow:      false,
    webPreferences: {
      preload:          path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration:  false,
    },
  });

  widgetWin.loadFile("widget.html");
  widgetWin.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
}

// ── Chat panel — slides up from the widget ─────────────────────────────────
function createChat() {
  const { width, height } = screen.getPrimaryDisplay().workAreaSize;

  chatWin = new BrowserWindow({
    width:          480,
    height:         660,
    x:              width  - 500,
    y:              height - 730,
    frame:          false,
    transparent:    false,
    alwaysOnTop:    true,
    resizable:      true,
    skipTaskbar:    true,
    show:           false,
    webPreferences: {
      preload:          path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration:  false,
    },
  });

  chatWin.loadFile("chat.html");

  chatWin.on("close", (e) => {
    e.preventDefault();
    chatWin.hide();
  });
}

// ── IPC handlers ───────────────────────────────────────────────────────────
ipcMain.on("toggle-chat", () => {
  if (!chatWin) return;
  if (chatWin.isVisible()) {
    chatWin.hide();
  } else {
    const [wx, wy] = widgetWin.getPosition();
    const { width } = screen.getPrimaryDisplay().workAreaSize;
    const chatX = Math.min(wx - 330, width - 500);
    const chatY = Math.max(wy - 680, 10);
    chatWin.setPosition(chatX, chatY);
    chatWin.show();
    chatWin.focus();
  }
});

ipcMain.on("close-chat", () => {
  if (chatWin) chatWin.hide();
});

ipcMain.on("widget-move", (_, { x, y }) => {
  if (widgetWin) widgetWin.setPosition(x, y);
});

// ── App lifecycle ──────────────────────────────────────────────────────────
app.whenReady().then(() => {
  createWidget();
  createChat();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
