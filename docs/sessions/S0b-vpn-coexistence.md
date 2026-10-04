# S0b 讓 CUHK VPN 與 Private Internet Access 在這台 Mac 上並存

寫給一個全新的 Claude Code session。開始前先讀 `cluster/ENV.md` 的「存取方式」與「追加測試一」。
本任務與語音管線無關，只處理使用者 Mac 的網路設定。

## 目標

Private Internet Access（以下稱 PIA，使用者必須常開，否則連不上 Claude）與 CUHK VPN（GlobalProtect 6.3.3，入口 `access.cuhk.edu.hk`）同時連線時：

1. 一般上網與 Claude 正常（走 PIA）。
2. `ssh scrp 'hostname'` 成功（走 CUHK VPN；金鑰 `~/.ssh/id_ed25519_scrp` 與別名已設好，2026-10-02 23:31 實測登入成功過）。
3. GlobalProtect 斷線或自動重連都不會讓 Mac 斷網。

做不到第 1 項就不算成功。

## 已確認的事實（2026-10-02 實測，證據在 `cluster/ENV.md`）

- 兩者同時連線時，隧道本身建得起來（IPSec，閘道 `137.189.192.215`，本機取得 `137.189.202.x`）。
- **問題一，路由被搶**：PIA 的分流清單有一條「`137.189.0.0/16` 不走 VPN」，它加的路由會蓋掉 CUHK VPN 要的同一段。GlobalProtect 日誌：`Route 137.189 shadows access route 137.189.0.0/16`。結果校內流量不進隧道，SSH 不通。
- 這條 PIA 路由被 GlobalProtect 斷線時順手刪掉之後（PIA 重連會再加回來），校內流量就會走隧道（`137.189 → utun5`），**此時 SSH 是通的**。
- **問題二，DNS 被換掉**：GlobalProtect 連上後把系統 DNS 改成 `137.189.192.3`、`137.189.196.3`。實測 `dig @137.189.192.3` 逾時，而 `dig @10.0.0.241`（PIA 的 DNS）正常回應。所以系統解析全部失敗，表現為「整台 Mac 斷網」。校內 DNS 查詢為何出不去尚未查明，推測是 PIA 的 DNS 防洩漏規則擋掉了非 PIA 的 DNS（沒有讀到它的防火牆規則，需要 `sudo pfctl -sr` 才看得到）。
- **GlobalProtect 會自己重連**：按 Disconnect 後，只要偵測到路由變動就可能用快取的登入狀態自動連上（日誌 `GPC-26003 recovery … Forcing network discovery`），已發生兩次（22:37、23:24）。要它安靜只能 Sign Out 或移除。
- GlobalProtect 的系統擴充功能（Network Extension）沒有啟用，隧道不需要它。
- PIA 目前設定（`piactl -u dump daemon-settings`）：`bypassSubnets = 137.189.0.0/16`、`overrideDNS = "pia"`、`killswitch = "auto"`、`splitTunnelEnabled = true`、協定 WireGuard。
- 不靠 VPN 的備用通道一直可用：JupyterHub `https://scrp-login.econ.cuhk.edu.hk/jupyter/`（HTTPS，校外直連）。

## 待驗證的做法（依序試，每次只改一項）

1. PIA 分流清單移除 `137.189.0.0/16`（解決問題一）。副作用：CUHK VPN 沒連時，中大網站改經 PIA 出去，實測 JupyterHub 仍可登入。
2. 解決問題二，候選方案：
   - PIA 的 DNS 設定改成「使用既有 DNS」，看校內 DNS 查詢是否就能通過隧道。
   - 或者反過來，讓系統在 CUHK VPN 連線時仍用 PIA 的 DNS（需要 `sudo` 的 `scutil` 或 `/etc/resolver`，由使用者執行）。
   - 先用 `sudo pfctl -sr`（使用者執行）確認到底是誰擋了 53 埠，再選方案，不要盲試。
3. 驗證 GlobalProtect 自動重連時也不斷網。

## 做法與邊界

- **所有 PIA、GlobalProtect、系統設定的更改都由使用者親手做**，Claude 只給步驟並驗證結果。需要密碼的命令給使用者自己跑。
- **每次讓使用者連 CUHK VPN 之前，先在背景啟動 `tools/vpn_monitor.sh <記錄檔>`**。它每 5 秒記錄 PIA 狀態、到叢集的路由、SSH 埠、Claude 是否可達；即使 Claude 連線斷了，恢復後也能讀記錄。
- **事先告訴使用者怎麼自救**：一旦斷網，點選單列地球圖示 → Disconnect；要防止它自己重連就 Sign Out。
- 連上 CUHK VPN 時系統 DNS 是壞的，測 SSH 請用 IP：`ssh -o HostName=137.189.68.83 scrp`。
- GlobalProtect 日誌可直接讀（不需 sudo）：`/Library/Logs/PaloAltoNetworks/GlobalProtect/PanGPS.log`，看 `access-routes`、`tunnel dns is`、`shadows`、`Set state to`。
- 若最終判定並存不可行或代價太高，如實記錄，建議使用者 Sign Out 或移除 GlobalProtect，改走 JupyterHub。

## 驗收

- 三項目標各附一段命令輸出；最終的 PIA 設定寫進 `cluster/ENV.md`（追加一節，不改寫舊內容）。
- 更新 `docs/00-decisions.md` 追加記錄裡「D4 待定」那一條的結論。

## 完成記錄
2026-10-04 完成，三項目標全部達成。證據與最終設定見 `cluster/ENV.md`「追加測試六」。

- 改了三項設定（都由使用者親手改）：PIA 分流清單移除 `137.189.0.0/16`；PIA 的 DNS 改成 Use Existing DNS；macOS Wi-Fi 的 DNS 設為 `1.1.1.1`、`8.8.8.8`。kill switch 與 GlobalProtect 未動。
- 任務書候選方案之外的發現：只改 PIA 的 DNS 會在下次重連時斷網（供應商 DNS 不回應經 PIA 來的查詢），所以多了 Wi-Fi DNS 那一項。
- 目標一：兩者同時連線時 Claude 可達、出口位址是 PIA 的。目標二：`ssh scrp 'hostname'` 回 `scrp-login`。目標三：GlobalProtect 斷線／重連、PIA 重連共 220 筆記錄中 Claude 不可達 0 筆。
- 副作用：監測腳本探測太頻繁，叢集封鎖了 VPN 位址約一小時（已自行解除）；腳本已改為每 60 秒探一次。
- 另外應使用者要求：SCRP 模型服務的金鑰存入 `~/.config/scrp/env`，用法寫成全域 skill `scrp-api`；移除分流規則後 GLM 實測仍可用。
- `docs/00-decisions.md` 已追加 D4 結論。未提交到 git。
