# S4 SCRP 端 TTS 批次與 ASR 質檢

## 目標
`cluster/tts_batch.py` 在一張 RTX 3090 上讀 tts_manifest.json，對 `engine == indextts2` 的項目零樣本克隆合成、ASR 回檢、重試，寫 `out/<scene>/audio/<line_id>.wav` 與 `qc_report.json`。Mac 端 `pipeline cluster push/pull` 封裝 rsync。

## 前提
S0 的 `cluster/ENV.md` 與 `setup_env.sh`；S3 的 manifest 與 refs。

## 步驤
1. 環境：依 S0 結論完成 `setup_env.sh`（IndexTTS-2 官方 repo `index-tts/index-tts`，權重 `IndexTeam/IndexTTS-2` 自 HuggingFace；FunASR `paraformer-zh` 或 `SenseVoiceSmall`；若計算節點無外網，在登入節點以 `huggingface-cli download` 到 `~/large-data/models/`）。記錄實際 VRAM 峰值。
2. `tts_batch.py`（自包含，無專案依賴）：
   - 參數：`--manifest`、`--out`、`--refs-root`、`--models-root`、`--cer-threshold 0.10`、`--max-attempts 3`、`--resume`（跳過已成功項）。
   - 每項：載入 refs（多段時拼接或取最佳一段，實測哪種更穩）、合成、`soundfile` 寫 24 kHz WAV、首尾靜音裁到 ≤ 0.15 s、ASR → 與 `text`（去標點）算 CER；超閾值改 seed 重試；寫入 report。
   - lexicon：確認 IndexTTS-2 的拼音標註方式（文本中以拼音替換或特殊標記），落實 S3 收集的表；若不支持，退而用同音字替換並記錄。
   - 情緒：接受 manifest 的 `emotion` 欄但第一版忽略（D13）；程式上留好 `emo_text`/`emo_vector` 參數位置。
   - 日誌到 stdout，進度每 20 句一行。
3. `cluster/job.sbatch`：`#SBATCH --gpus=rtx3090 --cpus-per-task=8 --mem=40G --time=0-12 --job-name=aktts`；用 `$MANIFEST` 環境變數；啟動前 `conda activate` 與 `module load cuda/<S0 確認版本>`。
4. Mac 端 `pipeline cluster push --scene` 只 rsync `out/<scene>/tts_manifest.json`、`refs/`、`config/lexicon.yaml`；`pull` 只拉 `audio/` 與 `qc_report.json`。主機名、使用者名放 `config/settings.yaml` 的 `cluster:` 區。
5. 用 BB-ST-1 的 indextts2 項目（凯尔希、阿斯卡纶 等）實跑，記錄：每句平均秒數、VRAM、CER 分佈、flag 數。

## 驗收
- BB-ST-1 全部 indextts2 項目有 WAV；qc_report 的 flag ≤ 10%。
- `--resume` 中斷重跑不重做已成功項。
- 第二次 sbatch 不需要任何手工步驟。

## 邊界
- 不在叢集上做渲染或 ElevenLabs 呼叫（API key 不上叢集）。
- 不把遊戲素材放到 `~/`（只放 `~/large-data`）。

## 完成記錄
（session 結束時填寫）
