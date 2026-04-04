const { app, BrowserWindow, ipcMain, screen } = require("electron");
const path = require("path");

let widgetWin = null;
let chatWin   = null;

// ── Widget window (always on top, draggable brain orb) ─────────────────────
function createWidget() {
  const { width, height } = screen.getPrimaryDisplay().workAreaSize;

  widgetWin = new BrowserWindow({
    width:          80,
    height:         80,
    x:              width - 100,   // bottom-right by default
    y:              height - 100,
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

// ── Chat window (hidden until widget is clicked) ───────────────────────────
function createChat() {
  const { width, height } = screen.getPrimaryDisplay().workAreaSize;

  chatWin = new BrowserWindow({
    width:          420,
    height:         620,
    x:              width - 440,
    y:              height - 700,
    frame:          false,
    transparent:    false,
    alwaysOnTop:    true,
    resizable:      true,
    skipTaskbar:    true,
    show:           false,          // hidden until widget click
    webPreferences: {
      preload:          path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration:  false,
    },
  });

  chatWin.loadFile("chat.html");

  // hide instead of close when X is pressed
  chatWin.on("close", (e) => {
    e.preventDefault();
    chatWin.hide();
  });
}

// ── IPC handlers ───────────────────────────────────────────────────────────

// Widget clicked → toggle chat
ipcMain.on("toggle-chat", () => {
  if (!chatWin) return;
  if (chatWin.isVisible()) {
    chatWin.hide();
  } else {
    // Re-anchor chat window just above widget
    const [wx, wy] = widgetWin.getPosition();
    const { width } = screen.getPrimaryDisplay().workAreaSize;
    const chatX = Math.min(wx - 360, width - 440);
    chatWin.setPosition(chatX, Math.max(wy - 640, 10));
    chatWin.show();
    chatWin.focus();
  }
});

// Chat close button → hide chat
ipcMain.on("close-chat", () => {
  if (chatWin) chatWin.hide();
});

// Widget drag — renderer sends new position
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