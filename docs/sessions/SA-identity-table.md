# SA 身份表：每一句到底是誰在說

寫給一個全新的 Claude Code session（只在 Mac 上做，不用叢集、不用任何 TTS）。
開始前讀：`docs/00-decisions.md`（含全部追加記錄）、`docs/01-architecture.md` 的 casting.yaml 一節、`docs/02-data-sources.md` §1。

## 為什麼要做
目標是替原版劇情的每一句配上語音。配錯人比配得普通更糟，有三類行最容易配錯：
1. **沒標名字的行**（巴別塔 761 句）：多數是旁白，但有些其實是某角色的內心獨白，必須用該角色的聲音。
2. **「？？？」**（83 句）：後文才揭曉身份；背後對應好幾個不同的人（初步看立繪至少 6 種）。
3. **代稱與同名不同人**：「“阿米娅”」「“疤眼”」「“老师”」、多個「萨卡兹雇佣兵」等。
另外，劇本裡的名字不等於幹員名：特蕾西娅＝幹員「魔王」（`char_4134_cetsyr`），Logos＝逻各斯（`char_4133_logos`），Mantra＝真言（`char_4204_mantra`），Mechanist＝机械师（`char_4230_mcnist`）。這張對應決定誰能用原聲克隆。

## 產出
1. `config/identity/act33side.tsv`（入庫）：每個要配音的行一列。欄位：
   `scene`（storyTxt 的檔名，如 `level_act33side_st01`）、`seq`（該檔內「對白＋旁白＋Subtitle」依序的序號，從 1 起，Sticker 不算——與 `docs/01-architecture.md` 的 line_id 定義相同）、`text_head`（原文前 12 字，日後與 S1 的 timeline 對接時用來核對）、`shown_as`（劇本顯示的名字，無則空）、`identity`（判定的真實身份，用統一的規範名）、`kind`（dialogue / narration / monologue / unknown_language / silent）、`confidence`（high / low）、`basis`（一句話理由：立繪編號、後文哪一行揭曉等）。
   - `silent`＝只有「……」「——」之類、沒有可念的字；`unknown_language`＝帶「（未知语言）」。這兩種不配音但字幕照常（專案擁有者已決定）。
2. `config/identity/speakers.yaml`（入庫）：每個規範身份一條：`aliases`（劇本裡出現過的所有寫法）、`sprite_groups`、`line_count`、`operator_char_id`（有中文語音的幹員才填，查 `character_table.json` 與 `charword_table.json` 的 `voiceLangDict[...].dict` 是否含 `CN_MANDARIN`；注意同名多版本，如 凯尔希 有 `char_003_kalts` 與 `char_1052_kalts2`，預設取本體並註明）、`role`（operator / npc_major(≥30 句) / npc_minor / narrator / doctor）。
3. `docs/identity-review.md`（入庫）：給專案擁有者看的待確認清單，只列 `confidence: low` 的。**每條必須附上下文**（前後各 2–3 行原文與場次），因為他明說單句無從判斷。問法是事實題：「這句我判斷是某某，因為……，對嗎？」
4. 在本檔底部填「完成記錄」。

## 做法
- 下載 23 場劇本與三張表到 `data/`（不入庫）。場次清單在 `story_review_table.json` 的 `act33side.infoUnlockDatas`。
- **逐場通讀全文再判定**，不要只靠規則。可用的線索：`[charslot]`/`[character]` 的立繪編號與 `focus`、說話前後的稱呼、後文揭曉、同一立繪在別處的名字。先用程式產出初稿（顯示名、台上立繪），再人工逐場修正。
- 無名行預設旁白；判成獨白要有具體依據（例如前後都是同一人的心理描寫、字卡以引號呈現某人的話）。字卡（Sticker）不是配音行，但常是判斷獨白歸屬的線索。
- 全活動約 4400 行，分場做，每場做完就寫檔，避免一次塞滿上下文。

## 驗收
- 23 場全覆蓋；`kind` 各類行數與全活動統計寫進完成記錄。
- 每個「？？？」與帶引號的代稱都有 `identity` 與 `basis`。
- 待確認清單每條都有上下文；條數寫明。
- 一個小檢查腳本（放 `tools/`）：驗證 tsv 的 `seq` 連續、`identity` 都出現在 speakers.yaml、`text_head` 與原文相符。

## 邊界
- 不合成、不下載音訊、不碰叢集。
- 不決定聲線（那是選角的事），只決定「是誰」。
- 遊戲文本不入庫：tsv 只放前 12 字的 `text_head`，review 文件的上下文引用以每條前後各 2–3 行為限。

## 完成記錄
（session 結束時填寫）
