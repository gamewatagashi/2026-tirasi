# 公開手順（Streamlit Community Cloud）

無料でランニングコストほぼ0円、社内複数人が使える形で公開する手順です。

## 前提：何をGitHubに置き、何を置かないか

`templates/` `images/` `data/` は `.gitignore` に入っています（写真は権利上の理由・
テンプレートやマスタデータは非公開情報のため）。GitHubには**コードだけ**を公開し、
これらの資産は次のどちらかで用意します。

| 方法 | 向いているケース |
|---|---|
| **A. Google Drive連携を使う**（本アプリに実装済み） | 資産を非公開のGoogle Driveフォルダに置いたまま、コードだけを公開したい場合。おすすめ。 |
| **B. リポジトリに含めてしまう** | 学内限定などGitHub側も非公開でよい場合。`.gitignore` からその行を消せば含められます。 |

以下は **A（Drive連携）** を前提にした手順です。Bで良ければ手順4は不要です。

## 1. GitHubにコードをプッシュ

```bash
cd oc_app
git init
git add app.py generator.py drive_helper.py requirements.txt packages.txt README.md DEPLOY.md .gitignore
git commit -m "OC chirashi generator"
git remote add origin https://github.com/<your-account>/<repo>.git
git push -u origin main
```

`templates/` `images/` `data/` はコミットされません（`.gitignore` により除外）。

## 2. Streamlit Community Cloud にデプロイ

1. https://share.streamlit.io にアクセスし、GitHubアカウントで連携。
2. 「New app」→ 先ほどのリポジトリ・ブランチを選択。
3. **Main file path** に `oc_app/app.py`（リポジトリ直下にコードを置いた場合は `app.py`）を指定。
4. 「Deploy」をクリック。この時点ではまだ `templates/` `images/` `data/` が無いのでエラーになりますが、次の手順4で解消します。

## 3. `packages.txt` の確認（PDF変換用）

`packages.txt` に `libreoffice` と書かれていればOKです。Streamlit CloudのLinux環境に
自動でLibreOfficeがインストールされ、Word→PDF変換ができるようになります。

## 4. Google Drive連携の設定（テンプレート・写真をコードと分離する場合）

アプリ内の「⚙️ Google Drive連携」タブにも同じ手順が載っています。

1. **Google Cloud Console**（https://console.cloud.google.com）で新規プロジェクトを作成。
2. 「APIとサービス」→「ライブラリ」から **Google Drive API** を有効化。
3. 「APIとサービス」→「認証情報」→「認証情報を作成」→「サービスアカウント」。
   作成後、そのサービスアカウントの「鍵」タブから **JSON形式のキーを1つダウンロード**。
4. 写真用・テンプレート用のGoogle Driveフォルダを作成し、それぞれ
   サービスアカウントのメールアドレス（JSON内の `client_email`）に**閲覧者権限で共有**。

   > 手元の `pixta素材.zip` のような写真アーカイブは、Claudeの作業環境からは
   > あなたのGoogle Driveへ直接アップロードできません（ネットワーク制限のため）。
   > 一度PCで解凍し、ブラウザからGoogle Driveの当該フォルダにドラッグ＆ドロップで
   > アップロードしてください。ファイル名（例：`静岡大学_pixta_61980911_M.jpg`）は
   > そのままでOKです。アプリ側は `pixta_` より前の部分を大学名として認識します。

5. フォルダを開いたときのURL末尾の文字列がフォルダIDです：
   `https://drive.google.com/drive/folders/`**`1AbCdEfGhIjKlMnOpQrStUvWxYz`** ← ここ
6. Streamlit Cloudの管理画面で、対象アプリの「⋮」→「Settings」→「Secrets」を開き、
   ダウンロードしたJSONの中身をそのまま使って以下を貼り付けます：

```toml
[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "xxxxxxxxxxxxxxxx"
private_key = "-----BEGIN PRIVATE KEY-----\nMIIExxxxx...\n-----END PRIVATE KEY-----\n"
client_email = "oc-drive-reader@your-project-id.iam.gserviceaccount.com"
client_id = "123456789012345678901"
token_uri = "https://oauth2.googleapis.com/token"

drive_images_folder_id = "1AbCdEfGhIjKlMnOpQrStUvWxYz"
drive_templates_folder_id = "1AbCdEfGhIjKlMnOpQrStUvWxYz"
```

> `private_key` はJSON内の値をそのままコピーします（`\n` はそのまま文字として残してOK。
> Streamlit CloudのSecretsはTOMLとして解釈するので、コピペした改行コードのままで動きます）。

7. 保存すると数秒でアプリが再起動し、サイドバーが「✅ Google Drive 連携: 有効」に変わります。

これで **設定した管理者だけがSecretsを保有**し、他のメンバーはURLにアクセスするだけで
Drive連携の恩恵（大学名からの自動写真検索・テンプレート自動取得）を受けられます。

## 5. `data/university_map.xlsx` について

都道府県×大学のマスタ表（`番号` `都道府県` `掲載大学` の3列）は現状ローカル読み込み
（`data/university_map.xlsx`）のままです。これも同様にDrive経由にしたい場合は
教えてください（`drive_helper.py` に読み込み関数を1つ追加するだけで対応できます）。

## よくあるトラブル

| 症状 | 原因・対処 |
|---|---|
| デプロイ後 `FileNotFoundError: university_map.xlsx` | `data/` がリポジトリに含まれていない。Bの方法でコミットするか、Drive経由に変更。 |
| PDFボタンを押すとエラー | `packages.txt` に `libreoffice` が無い、またはCloud再起動直後で反映待ち。 |
| Drive連携が「未設定」のまま | Secretsの `[gcp_service_account]` セクション名やフォルダIDのtypoを確認。保存後は必ずアプリが自動再起動するまで待つ。 |
| Driveの写真が見つからない | サービスアカウントのメールアドレスにフォルダを共有し忘れている（フォルダ単位の共有が必要）。 |
