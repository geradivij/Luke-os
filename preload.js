const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("luke", {
  toggleChat:  ()         => ipcRenderer.send("toggle-chat"),
  closeChat:   ()         => ipcRenderer.send("close-chat"),
  moveWidget:  (x, y)     => ipcRenderer.send("widget-move", { x, y }),
});