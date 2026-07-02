"""Stock Wallet — 應用進入點。

前後端分離:
  * 後端邏輯在 api.py(Api 類別)與 indicators.py / analysis.py / wallet.py
  * 前端在 web/(index.html + styles.css + app.js)
這支檔案只負責建立視窗並載入前端。
"""
import webview

from api import Api, resource_path


def main():
    webview.create_window(
        "Stock Wallet",
        url=resource_path("web/index.html"),
        js_api=Api(),
        width=1240,
        height=860,
        min_size=(980, 660),
        background_color="#0e0f13",
    )
    webview.start(gui="edgechromium", private_mode=False)


if __name__ == "__main__":
    main()
