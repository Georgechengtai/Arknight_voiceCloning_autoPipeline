# S6 BB-ST-1 端到端整合、聽審、投稿檢查表

## 目標
以 S1–S5 的產物做出可發佈的 BB-ST-1 影片；形成「一條命令跑一場」的流程文件；準備 bilibili 投稿材料。

## 步驤
1. `scripts/run_scene.sh act33side_st01`：fetch-gamedata → parse → assets → tts manifest → cluster push → (等待 sbatch) → cluster pull → tts --engine elevenlabs → render。每步可 `--skip`。
2. 聽審：把 qc_report 的 flag 句與每個說話者各 3 句隨機樣本做成 `out/<scene>/review.html`（文字＋音訊播放器），使用者聽；對不合格句改 seed / 改 lexicon / 改 casting 重生，直到通過。
3. 全片審看：使用者看 MP4；記錄節奏（0.5 s 間隔是否合適）、字體大小、立繪位置錯誤、音量平衡（語音 -16 LUFS、BGM 低 12 dB 起調）。
4. 投稿材料：
   - 標題/簡介模板：註明「同人作品、非盈利、語音由 AI 生成（IndexTTS-2 / ElevenLabs）、素材版權歸鷹角網絡、如官方要求立即刪除」。
   - **AI 生成內容聲明必勾**（《人工智能生成合成内容标识办法》2025-09-01 施行；bilibili 投稿頁有對應選項）；片頭 3 秒加「本片語音為 AI 生成」字卡（渲染器加 `--intro-card`）。
   - 準備 `--no-bgm` 版本備用。
5. 回填：把 BB-ST-1 的實測數字（渲染時間、TTS 每句秒數、flag 率、總成本）寫進 `docs/00-decisions.md` 新一節「BB-ST-1 實測」；決定 D13（情緒）是否進入第二版。

## 驗收
- 使用者認可的 BB-ST-1 MP4。
- `scripts/run_scene.sh` 對第二個場景（建議 BB-1 行動前）能跑到渲染前（選角缺口除外）。

## 邊界
- 不在本 session 擴到全巴別塔選角；只記錄缺口清單。
- 是否實際上傳 bilibili 由使用者操作；本 session 只準備材料。

## 完成記錄
（session 結束時填寫）
