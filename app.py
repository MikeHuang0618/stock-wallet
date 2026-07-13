"""Stock Wallet — 應用進入點。

前後端分離:
  * 後端邏輯在 api.py(Api 類別)與 indicators.py / analysis.py / wallet.py
  * 前端在 web/(index.html + styles.css + app.js)
這支檔案只負責建立視窗並載入前端。
"""
import webview

from api import Api, resource_path, setup_logging


def main():
    setup_logging()   # 啟動時設定 RotatingFileHandler 日誌(見 api.setup_logging)
    api = Api()
    api.auto_backup()   # 每日一次自動備份 wallet.db(全部資產歷史的唯一來源)
    webview.create_window(
        "Stock Wallet",
        url=resource_path("web/index.html"),
        js_api=api,
        width=1240,
        height=860,
        min_size=(980, 660),
        background_color="#0e0f13",
    )
    webview.start(gui="edgechromium", private_mode=False)


if __name__ == "__main__":
    main()
