# S3 選角表、參考音、ElevenLabs 聲線設計

## 目標
產出可用的 `config/casting.yaml`、`config/lexicon.yaml`、`refs/<speaker>/*.wav`、`out/<scene>/tts_manifest.json`（BB-ST-1 先，巴別塔全量其次）。這是**唯一需要使用者大量參與**的前期 session（聽聲線、拍板）。

## 步驤
1. `python -m pipeline casting init --act act33side`：讀 S1 的 speakers.csv，產生 casting.yaml 骨架：
   - 查 `character_table.json` 把說話者名對到 charId；再查 `charword_table.voiceLangDict` 是否有 CN_MANDARIN → `role: operator`。同名多版本（阿米娅 ×3、凯尔希 ×?）列候選讓使用者選；特蕾西娅是否有可玩幹員版本與中文語音也在此確認。
   - 其餘按行數分 `npc_major`（≥ 30 行）與 `npc_minor`；`？？？`、帶引號假名列入 `identity_overrides` 待填。
   - 旁白、博士固定存在。
2. 參考音挑選 `pipeline casting refs`：對每個 operator，從 `voice_cn/<charId>/` 下載全部 MP3（raw URL，限 30 檔），轉 24 kHz 單聲道 WAV，自動評分：時長 5–15 s、無長靜音、RMS 穩定、（可選）用 charword_table 的 voiceText 做 ASR 核對確保乾淨；選前 3 段為候選，存 `refs/<speaker>/`，並生成一個 `refs/<speaker>/README.txt` 記錄來源 voiceId 與台詞。
3. ElevenLabs 聲線設計（使用 MCP 工具或 REST API，模型 eleven_v3 / Voice Design）：
   - 旁白：沉穩中低音、無角色感、普通話標準。
   - 博士：使用者要求「巴別塔時期的博士感」——冷靜、克制、年輕成年、低情緒起伏；給 3 個候選。
   - 主要 NPC（特雷西斯、“疤眼”、曼弗雷德、尤莉叶、奥达、Ace、Scout、菈玛莲、杜卡雷 等依 speakers.csv 行數）：各依劇情設定寫 prompt，給 2 個候選。
   - 共用池 8–10 個（male_rough / male_old / male_young / female_young / female_mature / child / sakaz_soldier …）。
   - 每個候選用該角色一句真實台詞試聽；用 AskUserQuestion 讓使用者逐一拍板（一次一個角色）。保存 voice_id 到 casting.yaml。
   - **禁止**上傳任何 refs/ 或遊戲音訊到 ElevenLabs（D3）。在 `pipeline/tts/elevenlabs.py` 加斷言。
4. `config/lexicon.yaml`：專有名詞→拼音/替換。先列巴別塔高頻：特蕾西娅、特雷西斯、凯尔希、阿斯卡纶、卡兹戴尔、萨卡兹、源石、博士、巴别塔、拉特兰、“疤眼”、曼弗雷德 等；格式 `{"萨卡兹": "sa4 ka3 zi1"}` 或整詞替換；具體怎麼餵給 IndexTTS-2（pinyin 標註語法）由 S4 確定，S3 先收集。
5. `pipeline tts manifest --scene act33side_st01`：套 casting + lexicon，產生 tts_manifest.json；對 `tts_text` 做：去 `*…*` 舞台提示、全角標點正規化、省略號「……」保留為停頓、純符號句（「……」「？！」）標 `skip_tts: true`（渲染時按字數停留）。

## 驗收
- BB-ST-1 manifest 中每一項都有 engine 與 voice_id/refs；`pipeline casting lint` 無錯（elevenlabs 無 refs、operator 有 ≥ 1 ref、無 unassigned）。
- 使用者已聽並確認：旁白、博士、凯尔希、阿斯卡纶，及 BB-ST-1 出現的 NPC。

## 邊界
- 不在本 session 跑開源 TTS（Mac 無 GPU）；只做 ElevenLabs 試聽。
- 巴別塔全量選角可留到 BB-ST-1 跑通後。

## 完成記錄
（session 結束時填寫）
