"""
東進 オープンキャンパス チラシ 自動生成アプリ
"""
import streamlit as st
import pandas as pd
import os, sys, tempfile

sys.path.insert(0, os.path.dirname(__file__))
from generator import (
    generate_chirashi, generate_batch_zip, docx_to_pdf, merge_pdfs,
    get_available_images, find_best_image, find_all_images, get_template_path,
)
import drive_helper as dh

# ── Page config ───────────────────────────────────────────────
st.set_page_config(page_title="OC チラシ生成", page_icon="🎓", layout="wide")
st.title("🎓 オープンキャンパス チラシ 自動生成")
st.caption("東進ハイスクール / 東進衛星予備校")

# ── Constants ─────────────────────────────────────────────────
DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "university_map.xlsx")
BACK_PDF  = os.path.join(os.path.dirname(__file__), "templates", "back_page.pdf")


# ── Load data ─────────────────────────────────────────────────
@st.cache_data
def load_master():
    df = pd.read_excel(DATA_PATH)
    df.columns = ['番号', '都道府県', '掲載大学']
    df = df.dropna(subset=['番号', '都道府県'])
    df['番号'] = df['番号'].astype(int)
    return df


@st.cache_data
def load_images():
    return get_available_images()


df       = load_master()
img_dict = load_images()
DRIVE_OK = dh.drive_enabled()

if "session_tmp_dir" not in st.session_state:
    st.session_state.session_tmp_dir = tempfile.mkdtemp(prefix="oc_session_")
SESSION_TMP = st.session_state.session_tmp_dir


def pref_suffix(pref_name: str) -> str:
    if pref_name in ['大阪', '京都']: return '府'
    if pref_name == '東京':           return '都'
    if pref_name == '北海道':         return ''
    return '県'


def parse_oc_schedule(raw: str) -> dict:
    schedule = {}
    if raw.strip():
        for line in raw.strip().splitlines():
            parts = line.split('\t')
            if len(parts) >= 2:
                schedule[parts[0].strip()] = '\t'.join(parts[1:]).strip()
            elif parts[0].strip():
                schedule[parts[0].strip()] = ''
    return schedule


def resolve_campus_image(univ_name: str, uploaded_file, tmp_dir: str, use_drive: bool):
    """
    Priority: manually uploaded photo > local images/ library > (optional)
    Google Drive folder. Returns a local file path, or None if nothing found.
    """
    if uploaded_file is not None:
        ext = uploaded_file.name.rsplit('.', 1)[-1]
        path = os.path.join(tmp_dir, f'_upload.{ext}')
        with open(path, 'wb') as f:
            f.write(uploaded_file.getvalue())
        return path

    local = find_best_image(univ_name)
    if local:
        return local

    if use_drive and DRIVE_OK:
        folder_id = st.secrets.get("drive_images_folder_id")
        match = dh.find_drive_image(univ_name, folder_id)
        if match:
            ext = match['name'].rsplit('.', 1)[-1]
            path = os.path.join(tmp_dir, f'_drive_{univ_name}.{ext}')
            try:
                dh.download_drive_file(match['id'], path)
                return path
            except Exception:
                return None
    return None


def resolve_template_path(tmpl_key: int, tmp_dir: str, use_drive_template: bool):
    local_path, key = get_template_path(tmpl_key)
    if use_drive_template and dh.templates_from_drive_enabled():
        folder_id = st.secrets.get("drive_templates_folder_id")
        match = dh.find_drive_template(key, folder_id)
        if match:
            dest = os.path.join(tmp_dir, f'_drive_template_{key}.docx')
            try:
                dh.download_drive_file(match['id'], dest)
                return dest, key
            except Exception:
                pass
    return local_path, key


# ── Sidebar: shared OC schedule input ──────────────────────────
with st.sidebar:
    st.header("📋 大学OC日程データ")
    st.caption("スプレッドシートから貼り付け、または手入力（①②共通で使えます）")
    oc_raw = st.text_area(
        "大学名 [TAB] 日程（1行1大学）",
        height=260,
        placeholder=(
            "例（スプレッドシートからコピー）:\n"
            "大阪大学\t6/13(人科)・6/27(外語)・8/4-19 各学部\n"
            "京都大学\t8/6・8/7 吉田キャンパス\n"
            "神戸大学\t8/7・8/8・8/10 各学部"
        ),
        help="Googleスプレッドシートの列をそのまま選択→コピー→貼り付けできます。"
             "大学名をキーに①②両方の生成で自動的に日程が入ります。"
    )
    st.divider()
    if DRIVE_OK:
        st.success("✅ Google Drive 連携: 有効")
    else:
        st.info("ℹ️ Google Drive 連携: 未設定\n\n「⚙️ Google Drive連携」タブを参照")

oc_schedule = parse_oc_schedule(oc_raw)

tab_single, tab_batch, tab_drive = st.tabs(
    ["① 単体作成", "② まとめて作成", "⚙️ Google Drive連携"]
)

# ════════════════════════════════════════════════════════════
# TAB 1: 単体作成（1都道府県ずつ、写真はその場でアップロード）
# ════════════════════════════════════════════════════════════
with tab_single:
    st.subheader("① 都道府県を選択")
    pref_options = df.apply(lambda r: f"{int(r['番号']):02d}  {r['都道府県']}", axis=1).tolist()
    default_idx = next((i for i, s in enumerate(pref_options) if '27' in s), 0)
    selected = st.selectbox("都道府県", pref_options, index=default_idx,
                             label_visibility="collapsed", key="single_pref")
    pref_num  = int(selected.split()[0])
    pref_name = selected.split()[1]

    row = df[df['番号'] == pref_num].iloc[0]
    default_univs_str = str(row['掲載大学'])

    st.subheader("② 掲載大学数・テンプレート")
    col_a, col_b, col_c = st.columns([1, 2, 2])
    with col_a:
        num_univ = st.select_slider("掲載大学数", options=[6, 8, 10, 12], value=12, key="single_num")
    with col_b:
        _, tmpl_key = get_template_path(num_univ)
        st.info(f"使用テンプレート: **{tmpl_key}大学フォーマット**")
    with col_c:
        use_drive_template = False
        if dh.templates_from_drive_enabled():
            use_drive_template = st.checkbox("テンプレートをDriveから読み込む", key="single_tmpl_drive")

    raw_list = [u.strip().strip('（）()') for u in default_univs_str.replace('、', ',').split(',')]
    default_list = [u for u in raw_list if u]

    st.subheader("③ 大学名・日程を確認・編集")
    rows = []
    for i in range(num_univ):
        name = default_list[i] if i < len(default_list) else ''
        schedule = oc_schedule.get(name, '')
        img_ok = '✅' if find_best_image(name) else '❓'
        rows.append({'大学名': name, '日程': schedule, '写真': img_ok})

    edited = st.data_editor(
        pd.DataFrame(rows),
        num_rows="fixed",
        use_container_width=True,
        column_config={
            '大学名': st.column_config.TextColumn('大学名', width='medium'),
            '日程':   st.column_config.TextColumn('日程・場所', width='large'),
            '写真':   st.column_config.TextColumn('写真', width='small', disabled=True),
        },
        key="single_univ_table",
    )
    for i, r in edited.iterrows():
        edited.at[i, '写真'] = '✅' if find_best_image(r['大学名']) else '❓'

    main_univ = edited['大学名'].iloc[0] if len(edited) > 0 else ''

    # ── Step 4: 写真（メイン導線） ──────────────────────────────
    st.subheader("④ 表紙写真を選択")
    st.caption(f"表紙に使う「{main_univ or '1番目の大学'}」の写真を選んでください。候補が複数あれば選べます。")

    photo_mode = st.radio(
        "写真の選び方",
        ["📚 ライブラリ／Driveから選ぶ", "📤 自分の端末からアップロード"],
        horizontal=True, key="single_photo_mode",
    )

    custom_img_file = None
    selected_campus_path = None
    use_drive_photo_single = False

    if photo_mode.startswith("📤"):
        custom_img_file = st.file_uploader(
            "写真をアップロード（共有ライブラリ・Driveには保存されず、この生成にのみ使われます）",
            type=['jpg', 'jpeg', 'png'], key="single_upload",
        )
        if custom_img_file:
            ext = custom_img_file.name.rsplit('.', 1)[-1]
            selected_campus_path = os.path.join(SESSION_TMP, f"_upload_{main_univ}.{ext}")
            with open(selected_campus_path, 'wb') as f:
                f.write(custom_img_file.getvalue())

    else:
        if DRIVE_OK:
            use_drive_photo_single = st.checkbox(
                "Google Drive の写真フォルダも候補に含める", value=True,
                key="single_use_drive_photo",
            )

        candidates = [{'label': os.path.basename(p), 'path': p} for p in find_all_images(main_univ)]

        if use_drive_photo_single:
            folder_id = st.secrets.get("drive_images_folder_id")
            try:
                for f in dh.find_all_drive_images(main_univ, folder_id):
                    candidates.append({'label': f"☁️ {f['name']}", 'drive_id': f['id']})
            except Exception as e:
                st.warning(f"Google Drive検索でエラーが発生しました: {e}")

        if not candidates:
            st.warning(
                f"「{main_univ}」に一致する写真が見つかりませんでした。"
                "「📤 自分の端末からアップロード」に切り替えてください。"
            )
        else:
            # Resolve any Drive candidates to a local cached path (for preview + reuse)
            for cand in candidates:
                if 'path' not in cand:
                    cache_path = os.path.join(SESSION_TMP, f"_drivecache_{cand['drive_id']}.jpg")
                    if not os.path.exists(cache_path):
                        try:
                            with open(cache_path, 'wb') as f:
                                f.write(dh.download_drive_file_bytes(cand['drive_id']))
                        except Exception as e:
                            st.error(f"「{cand['label']}」の取得に失敗しました: {e}")
                            continue
                    cand['path'] = cache_path

            st.caption(f"候補写真（{len(candidates)}件）：")
            cols = st.columns(min(4, len(candidates)))
            for i, cand in enumerate(candidates):
                with cols[i % len(cols)]:
                    if cand.get('path'):
                        st.image(cand['path'], use_container_width=True, caption=cand['label'])

            choice_idx = st.radio(
                f"「{main_univ}」に使う写真を選択",
                list(range(len(candidates))),
                format_func=lambda i: candidates[i]['label'],
                horizontal=True, key=f"single_photo_choice_{main_univ}",
            )
            selected_campus_path = candidates[choice_idx].get('path')

    with st.expander("🖼 選択中の写真プレビュー", expanded=(selected_campus_path is None)):
        if selected_campus_path:
            st.image(selected_campus_path, caption="この写真がチラシに使われます", width=380)
        else:
            st.warning("まだ写真が選択されていません。上で選ぶかアップロードしてください。")

    st.divider()
    col_o1, col_o2 = st.columns(2)
    with col_o1:
        do_pdf = st.checkbox("PDF版も生成する", value=True, key="single_do_pdf")
    with col_o2:
        do_back = st.checkbox("裏面PDFと結合する", value=True, key="single_do_back")

    generate_btn = st.button("🚀 チラシを生成する", type="primary", use_container_width=True, key="single_generate")

    if generate_btn:
        univs = [
            {'name': r['大学名'].strip(), 'schedule': r['日程'].strip()}
            for _, r in edited.iterrows() if r['大学名'].strip()
        ]
        if not univs:
            st.error("大学名を入力してください")
            st.stop()

        suffix = pref_suffix(pref_name)
        base_name = f"{pref_num:02d}_{pref_name}{suffix}_oc2026"

        with st.spinner("生成中... しばらくお待ちください"):
            with tempfile.TemporaryDirectory() as tmp:
                # Fall back to an auto pick only if nothing was explicitly selected/uploaded
                campus_path = selected_campus_path or find_best_image(univs[0]['name'])

                template_path, _ = resolve_template_path(num_univ, tmp, use_drive_template)

                docx_out = os.path.join(tmp, f'{base_name}.docx')
                try:
                    generate_chirashi(
                        pref_num, pref_name, univs, campus_path, docx_out,
                        template_path_override=template_path,
                    )
                    with open(docx_out, 'rb') as f:
                        docx_bytes = f.read()

                    st.success("✅ 生成完了！")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.download_button(
                            "📄 Word ダウンロード (.docx)", data=docx_bytes,
                            file_name=f'{base_name}.docx',
                            mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                            use_container_width=True,
                        )
                    with col2:
                        if do_pdf:
                            pdf_front = os.path.join(tmp, f'{base_name}_front.pdf')
                            docx_to_pdf(docx_out, pdf_front)
                            if do_back and os.path.exists(BACK_PDF):
                                pdf_out = os.path.join(tmp, f'{base_name}.pdf')
                                merge_pdfs(pdf_front, BACK_PDF, pdf_out)
                                label = "📄 PDF ダウンロード（表裏合体）"
                            else:
                                pdf_out = pdf_front
                                label = "📄 PDF ダウンロード（表面のみ）"
                            with open(pdf_out, 'rb') as f:
                                pdf_bytes = f.read()
                            st.download_button(
                                label, data=pdf_bytes, file_name=f'{base_name}.pdf',
                                mime='application/pdf', use_container_width=True,
                            )
                except Exception as e:
                    st.error(f"生成エラー: {e}")
                    import traceback
                    st.code(traceback.format_exc())

    with st.expander("📚 写真ライブラリ（利用可能な大学一覧）"):
        names = sorted(img_dict.keys())
        cols = st.columns(4)
        for i, name in enumerate(names):
            cols[i % 4].caption(f"• {name}（{len(img_dict[name])}枚）")


# ════════════════════════════════════════════════════════════
# TAB 2: まとめて作成（複数都道府県を一括生成し、ZIPでダウンロード）
# ════════════════════════════════════════════════════════════
with tab_batch:
    st.subheader("複数の都道府県を一度に生成する")
    st.caption(
        "一括生成では写真をその場でアップロードできないため、"
        "各大学の写真はローカルの写真ライブラリ（および設定していればGoogle Drive）"
        "から自動で選ばれます。見つからない場合は警告に一覧が出ます。"
    )

    pref_options_b = df.apply(lambda r: f"{int(r['番号']):02d}  {r['都道府県']}", axis=1).tolist()
    selected_prefs = st.multiselect(
        "生成する都道府県を選択（複数選択可）", pref_options_b, key="batch_prefs",
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        batch_do_pdf = st.checkbox("PDF版も生成する", value=True, key="batch_do_pdf")
    with col2:
        batch_do_back = st.checkbox("裏面PDFと結合する", value=True, key="batch_do_back")
    with col3:
        batch_use_drive_photo = False
        if DRIVE_OK:
            batch_use_drive_photo = st.checkbox(
                "写真の自動検索にGoogle Driveも含める", value=True, key="batch_use_drive_photo",
            )

    batch_use_drive_template = False
    if dh.templates_from_drive_enabled():
        batch_use_drive_template = st.checkbox(
            "テンプレートをGoogle Driveから読み込む", key="batch_tmpl_drive",
        )

    st.caption(
        "各都道府県の掲載大学・大学数はマスタデータ（都道府県×大学）の並び順をそのまま使います。"
        "日程はサイドバーに貼り付けたデータから大学名で自動的に引き当てます。"
    )

    run_batch = st.button(
        "🚀 選択した都道府県をまとめて生成する", type="primary",
        use_container_width=True, key="batch_generate", disabled=not selected_prefs,
    )

    if run_batch:
        jobs = []
        preview_rows = []
        with tempfile.TemporaryDirectory() as tmp:
            for sel in selected_prefs:
                p_num = int(sel.split()[0])
                p_name = sel.split()[1]
                row = df[df['番号'] == p_num].iloc[0]
                raw_list = [u.strip().strip('（）()') for u in str(row['掲載大学']).replace('、', ',').split(',')]
                names = [u for u in raw_list if u]
                if not names:
                    continue

                univs = [{'name': n, 'schedule': oc_schedule.get(n, '')} for n in names]
                suffix = pref_suffix(p_name)
                base_name = f"{p_num:02d}_{p_name}{suffix}_oc2026"

                campus_path = resolve_campus_image(names[0], None, tmp, batch_use_drive_photo)
                template_path, tmpl_key = resolve_template_path(len(univs), tmp, batch_use_drive_template)

                jobs.append({
                    'base_name': base_name,
                    'pref_num': p_num,
                    'pref_name': p_name,
                    'universities': univs,
                    'campus_image_path': campus_path,
                    'template_path_override': template_path,
                })
                preview_rows.append({
                    '都道府県': f"{p_num:02d} {p_name}",
                    '大学数': len(univs),
                    'テンプレート': f"{tmpl_key}大学",
                    '写真': '✅' if campus_path else '❓ 見つかりません',
                })

            st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)

            with st.spinner(f"{len(jobs)}件のチラシを生成中... しばらくお待ちください"):
                back_pdf_path = BACK_PDF if (batch_do_back and os.path.exists(BACK_PDF)) else None
                zip_bytes, warnings = generate_batch_zip(jobs, batch_do_pdf, batch_do_back, back_pdf_path)

            st.success(f"✅ {len(jobs)}件のうち生成完了しました！")
            st.download_button(
                "📦 まとめてダウンロード (.zip)", data=zip_bytes,
                file_name="oc_chirashi_batch.zip", mime="application/zip",
                use_container_width=True,
            )
            if warnings:
                with st.expander(f"⚠️ 警告（{len(warnings)}件）", expanded=True):
                    for w in warnings:
                        st.write(f"- {w}")


# ════════════════════════════════════════════════════════════
# TAB 3: Google Drive 連携（オプション機能・設定案内）
# ════════════════════════════════════════════════════════════
with tab_drive:
    st.subheader("Google Drive 連携について")
    st.write(
        "この機能を設定すると、写真ライブラリやテンプレートをGitHubに含めずに"
        "共有のGoogle Driveフォルダから直接読み込めるようになります。"
        "**設定は任意で、設定していない場合は今まで通りローカルの `images/` `templates/` フォルダが使われます。**"
    )

    if DRIVE_OK:
        st.success("✅ Google Drive 連携が有効です。")
        images_folder = st.secrets.get("drive_images_folder_id")
        templates_folder = st.secrets.get("drive_templates_folder_id")

        st.write(f"📁 写真フォルダ ID: `{images_folder}`")
        if templates_folder:
            st.write(f"📁 テンプレートフォルダ ID: `{templates_folder}`")
        else:
            st.caption("テンプレートフォルダは未設定です（ローカルの templates/ が使われます）")

        if st.button("接続テスト（フォルダの中身を確認）"):
            with st.spinner("Driveに接続中..."):
                try:
                    names = dh.list_drive_image_names(images_folder)
                    st.write(f"写真フォルダから **{len(names)}件** の大学名を検出しました：")
                    st.write("、".join(names[:30]) + ("…" if len(names) > 30 else ""))
                except Exception as e:
                    st.error(f"接続に失敗しました: {e}")
    else:
        st.info("未設定です。以下の手順で設定できます。")
        st.markdown(
            """
**設定手順（1回だけでOK）**

1. Google Cloud Console で新しいプロジェクトを作成し、「Google Drive API」を有効化する。
2. 「APIとサービス」→「認証情報」→「サービスアカウントを作成」。作成後、鍵タブから
   **JSON形式のキーをダウンロード**する。
3. 写真を入れたGoogle Driveのフォルダ（大学写真用）を、サービスアカウントの
   メールアドレス（`xxxx@xxxx.iam.gserviceaccount.com`）に**閲覧者として共有**する。
   フォルダのURL末尾の文字列がフォルダIDです。
   （例: `https://drive.google.com/drive/folders/`**`1AbCdEfGhIjKlMnOpQrStUvWxYz`**）
4. アプリの `.streamlit/secrets.toml`（Streamlit Community Cloudの場合は
   「Settings → Secrets」）に、ダウンロードしたJSONの中身を貼り付ける：

```toml
[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n"
client_email = "xxxx@xxxx.iam.gserviceaccount.com"
client_id = "..."
token_uri = "https://oauth2.googleapis.com/token"

drive_images_folder_id = "1AbCdEfGhIjKlMnOpQrStUvWxYz"
drive_templates_folder_id = "1AbCdEfGhIjKlMnOpQrStUvWxYz"   # テンプレートも共有するなら
```

5. 保存するとアプリが自動的に再起動し、この画面が「✅ 有効」になります。

設定した人（管理者）だけがこのシークレットを持っているので、他のメンバーは
何もせずにそのままDrive連携の恩恵を受けられます。
"""
        )

    st.divider()
    st.caption("東進ハイスクール / 東進衛星予備校 | OC チラシ自動生成ツール v2.0")
