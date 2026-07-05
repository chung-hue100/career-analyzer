# LC-VCO 模擬結果分析工具

基於 Flask + Groq AI 的 LC-VCO 電路分析網頁工具，適用於 TSMC 0.18μm RF CMOS 設計。

## 功能

- **電路架構圖 AI 識別**：上傳 ADS 截圖 → AI 自動辨識拓樸、讀取電晶體/電感/變容二極體參數
- **模擬圖 AI 自動填入**：上傳調諧曲線、KVCO 圖、相位雜訊圖 → AI 萃取數值並填入表單
- **自動分析與圖表**：VC vs FOUT、VC vs KVCO、相位雜訊曲線，含目標規格線
- **修正建議**：KVCO 線性化、PLL 鎖定點建議、FoM 評估

## 安裝

```bash
pip install -r requirements.txt
```

## 設定 API Key

需要 [Groq](https://console.groq.com) API Key（免費）：

```powershell
# Windows（永久設定）
[System.Environment]::SetEnvironmentVariable("GROQ_API_KEY", "your_key_here", "User")
```

設定後重新開啟終端機再啟動伺服器。

## 啟動

```bash
python app.py
```

開啟瀏覽器前往 `http://localhost:5000/vco`

## 使用流程

1. 上傳 ADS 電路架構圖 → 點「AI 識別架構並讀取元件參數」
2. 上傳模擬截圖（調諧曲線、PN 圖）→ 點「AI 分析圖片並自動填入參數」
3. 點「分析並給出修正方向」查看結果與圖表

## 支援的 VCO 拓樸

- Complementary CMOS（PMOS + NMOS 互補）
- NMOS-only 交叉耦合
- PMOS-only 交叉耦合
