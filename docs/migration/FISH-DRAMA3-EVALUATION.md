# Fish Audio Drama 3：SCRP 對照測試方案

2026-10-23 核實：使用者所指應為 Fish Audio **Drama 3**，不是名為 Dream Drama Free 的模型。
官方技術報告：35B MoE、每 token 啟用約 3B。參數多不代表本專案效果一定較好。

官方來源：
- https://speech.fish.audio/install/
- https://speech.fish.audio/inference/
- https://github.com/fishaudio/fish-speech
- https://arxiv.org/abs/2610.18010

官方要求 NVIDIA、Linux/WSL，FP8 至少 48 GB；不支援 CPU、MPS、ROCm 或 --compile。
RTX 3090 只有 24 GB，且不應把新 GPU 的原生 FP8 路徑套在它上面。官方提供多卡 --device cuda:0,cuda:1,...，最後一張卡放 decoder/codec；實際精度、分配與餘量必須實測。
先查 SCRP 當前 GPU；優先合適的大顯存卡，否則評估同節點多張 3090。兩張 24 GB 不等於保證可載入。歷史配額允許最多四張 3090、兩張 A100，但未證實目前可排到、A100 容量或帳號當前權限。

## 隔離環境
不要改現有 IndexTTS 環境。在 ~/large-data/aktts/fish-drama3 建新環境（Python 3.12），固定 fish-speech commit 和 Hugging Face revision，保存安裝版本及模型 license。
在計算作業內按官方文件安裝，先確認磁碟餘量、driver/CUDA 相容性；不在登入節點載入模型。
官方權重：`hf download fishaudio/drama-3 --local-dir checkpoints/drama-3`。
若缺 codec.pth，官方文件要求準備 S2-Pro codec。不要把權重上傳 GitHub。

在獲分配的計算節點，用官方 CLI 小樣本測試：
```bash
python fish_speech/models/text2semantic/inference.py \
  --checkpoint-path checkpoints/drama-3 \
  --text '這裏換成所選的原劇本台詞' \
  --prompt-audio /path/to/approved-reference.wav \
  --prompt-text '這裏換成參考音的正確逐字稿' \
  --output /path/to/new-evaluation-output.wav \
  --device cuda:0,cuda:1,cuda:2,cuda:3
```
只列出 Slurm 實際分配到的卡；不預設四卡一定可用。此命令未在 SCRP 執行驗證。

## 公平 A/B
選 24 段：平穩長句、短反應、急喊、悲痛、未完成句與專名各四段。角色以凱爾希與特蕾西婭先開始，加入其他有可用參考音的角色。
第一輪固定相同原文與相同已認可參考音；第二輪才允許引擎各自最佳提示。IndexTTS 的墊尾句/情緒強度是引擎特定策略，不直接套用到 Fish。
每段保留原始 wav、精度、GPU 型號/峰值 VRAM、seed、耗時、版本、輸入、參考音 hash。
檢查漏字/多字（雙 ASR＋同音歸一）、語速、句尾、音色一致性；盲聽關鍵段判斷是否出戲。
以每分鐘合格音訊的 GPU 時間和重試率比較成本，不只比較一次生成速度。
結果若只是大部分持平，不取代整個 IndexTTS 流程；可按角色或場景選引擎。所有輸出放新目錄，不覆寫 out/act33side_st01。
