import streamlit as st
import pandas as pd
import altair as alt
from typing import List, Dict, Any

# ==============================================================================
# 設定・定数 (Configuration & Constants)
# ==============================================================================
APP_TITLE = "ユロっとシミュレーター Ver1.0"
PASSWORD = "2030fire"
DEFAULT_CAPITAL = 5000000  # 初期資金 500万
DEFAULT_YEARS = 5          # 期間 5年
DEFAULT_CAGR = 118.0       # 想定年利 118%

st.set_page_config(page_title=APP_TITLE, layout="wide")

# ==============================================================================
# 認証機能 (Authentication)
# ==============================================================================
def check_auth():
    """簡易パスワード認証を行う"""
    if "auth" not in st.session_state:
        st.session_state.auth = False

    def _auth_callback():
        if st.session_state.password_input == PASSWORD:
            st.session_state.auth = True
            del st.session_state.password_input
        else:
            st.error("パスワードが間違っています")

    if not st.session_state.auth:
        st.title("🔒 認証が必要です")
        st.text_input("パスワードを入力してください", type="password", key="password_input", on_change=_auth_callback)
        st.stop()

# ==============================================================================
# 計算ロジック (Simulation Logic)
# ==============================================================================
def run_simulation(start_capital: int, cagr: float, tax_rate: float, period_mode: str, years: int) -> pd.DataFrame:
    """
    指定された条件で複利運用シミュレーションを実行する
    """
    if period_mode == "月ごと":
        steps_per_year = 12
    elif period_mode == "半年ごと":
        steps_per_year = 2
    else:
        steps_per_year = 1

    step_yield = (1 + cagr / 100) ** (1 / steps_per_year) - 1
    
    data = []
    current_capital = start_capital
    year_start_capital = start_capital
    
    data.append({
        "年数": 0.0,
        "経過期間": "開始時",
        "資産残高": int(current_capital),
        "期間利益": 0,
        "年間利益(累積)": 0,
        "納税額": 0,
        "is_year_end": True
    })

    total_steps = years * steps_per_year
    
    for i in range(1, total_steps + 1):
        current_year_float = i / steps_per_year
        is_year_end = (i % steps_per_year == 0)
        
        prev_capital = current_capital
        current_capital_gross = prev_capital * (1 + step_yield)
        period_profit = current_capital_gross - prev_capital
        year_cumulative_profit = current_capital_gross - year_start_capital
        
        tax_amount = 0
        if is_year_end:
            tax_amount = year_cumulative_profit * (tax_rate / 100)
            current_capital = current_capital_gross - tax_amount
            year_start_capital = current_capital
        else:
            current_capital = current_capital_gross

        if period_mode == "月ごと":
            label = f"{int((i-1)/12)+1}年目 {(i-1)%12+1}月"
        elif period_mode == "半年ごと":
            year_num = int((i-1)/2)+1
            half_label = "上期" if i % 2 != 0 else "決算"
            label = f"{year_num}年目 {half_label}"
        else:
            label = f"{i}年目"

        data.append({
            "年数": current_year_float,
            "経過期間": label,
            "資産残高": int(current_capital),
            "期間利益": int(period_profit),
            "年間利益(累積)": int(year_cumulative_profit),
            "納税額": int(tax_amount),
            "is_year_end": is_year_end
        })
        
    return pd.DataFrame(data)

# ==============================================================================
# UIコンポーネント: サイドバー (Sidebar UI)
# ==============================================================================
def render_sidebar() -> Dict[str, Any]:
    """サイドバーを描画し、設定値を辞書で返す"""
    with st.sidebar:
        st.header("シミュレーション条件")
        
        # 期間選択 (最大10年に変更)
        years = st.selectbox(
            "シミュレーション期間 (年)",
            options=list(range(1, 11)), # 1年〜10年
            index=DEFAULT_YEARS - 1     # デフォルト5年
        )

        period_option = st.radio("表示・計算の単位", ("月ごと", "半年ごと", "年ごと"), index=0)
        st.divider()
        
        # 初期資金
        if "initial_capital_input" not in st.session_state:
            st.session_state.initial_capital_input = f"{DEFAULT_CAPITAL:,}"

        def _format_capital():
            val = st.session_state.initial_capital_input.replace(',', '')
            val = val.translate(str.maketrans({chr(0xFF10 + i): chr(0x30 + i) for i in range(10)}))
            if val.isnumeric():
                st.session_state.initial_capital_input = "{:,}".format(int(val))

        capital_str = st.text_input(
            "初期資金 (円)",
            key="initial_capital_input",
            on_change=_format_capital,
            help="数値を入力してEnterを押すとカンマがつきます"
        )
        
        try:
            initial_capital = int(capital_str.replace(',', ''))
        except ValueError:
            st.error("有効な数値を入力してください")
            st.stop()

        user_cagr = st.number_input("想定年利 (CAGR) %", min_value=1.0, value=DEFAULT_CAGR, step=1.0, format="%.1f")
        tax_rate = st.number_input("税率 (%)", min_value=0.0, value=20.315, step=0.1, format="%.3f")
        
        st.divider()
        st.subheader("ベンチマーク設定")
        min_cagr = st.number_input("Min 年利 (%)", value=68.0, step=1.0, format="%.1f")
        max_cagr = st.number_input("Max 年利 (%)", value=145.9, step=1.0, format="%.1f")
        show_range = st.checkbox("実績レンジを表示", value=True)

    return {
        "years": years,
        "period_option": period_option,
        "initial_capital": initial_capital,
        "user_cagr": user_cagr,
        "tax_rate": tax_rate,
        "min_cagr": min_cagr,
        "max_cagr": max_cagr,
        "show_range": show_range
    }

# ==============================================================================
# チャート生成ロジック (Chart Logic)
# ==============================================================================
def create_chart(df_user: pd.DataFrame, df_range: pd.DataFrame, config: Dict[str, Any]) -> alt.Chart:
    """Altairチャートを作成する"""
    years = config["years"]
    initial_capital = config["initial_capital"]
    show_range = config["show_range"]

    if show_range and not df_range.empty:
        y_max = df_range['max_balance'].max()
    else:
        y_max = df_user['資産残高'].max()

    # --- 1. ベースチャート ---
    base = alt.Chart(df_user).encode(
        x=alt.X('年数', title='経過年数', scale=alt.Scale(domain=[0, years])),
        y=alt.Y('資産残高', title='資産残高 (円)'),
    )

    # --- 2. 各レイヤー ---
    line_chart = base.mark_line(size=3, color='#1f77b4').encode(
        tooltip=[alt.Tooltip('年数'), alt.Tooltip('資産残高', format=',')]
    )

    area_chart = alt.Chart(df_range).mark_area(opacity=0.2, color='gray').encode(
        x='年数', y='min_balance', y2='max_balance',
        tooltip=[alt.Tooltip('min_balance', format=','), alt.Tooltip('max_balance', format=',')]
    )

    points_chart = base.transform_filter(alt.datum.is_year_end == True).mark_circle(size=80, color='#1f77b4', opacity=1)
    
    text_chart = base.transform_filter(alt.datum.is_year_end == True).mark_text(
        align='left', baseline='bottom', dy=-10, dx=5, color='#1f77b4'
    ).encode(text=alt.Text('資産残高', format='.2s'))

    # --- 3. モチベーションマイルストーン (1年ごと) ---
    # 1年〜設定年数までのリストを作成
    milestones = list(range(1, years + 1))
        
    label_data = []
    for i, target_year in enumerate(milestones):
        row = df_user.iloc[(df_user['年数'] - target_year).abs().argsort()[:1]]
        if not row.empty:
            amt = row['資産残高'].values[0]
            mult = amt / initial_capital
            
            label_text = f"{target_year}年後: {amt:,.0f}円 ({mult:.1f}倍)"
            if target_year == years: 
                 label_text += " 🚀"
            
            # 最大10行になるため、行間を少し狭める(0.06)
            y_pos = y_max * (0.95 - (i * 0.06))
            label_data.append({'x': years * 0.02, 'y': y_pos, 'label': label_text})

    motivation_text = alt.Chart(pd.DataFrame(label_data)).mark_text(
        align='left', size=16, fontWeight='bold', color='#ff7f0e'
    ).encode(x='x', y='y', text='label')

    # --- 4. 合成 ---
    layers = [line_chart, points_chart, text_chart, motivation_text]
    if show_range and not df_range.empty:
        layers.insert(0, area_chart)

    return alt.layer(*layers)

# ==============================================================================
# メイン実行ブロック
# ==============================================================================
def main():
    check_auth()
    
    st.title(APP_TITLE)
    st.markdown("実績レンジ（帯）と比較しながら、納税を考慮した資産推移をシミュレーションします。")

    config = render_sidebar()

    df_user = run_simulation(
        config["initial_capital"], 
        config["user_cagr"], 
        config["tax_rate"], 
        config["period_option"], 
        config["years"]
    )

    df_range = pd.DataFrame()
    if config["show_range"]:
        df_min = run_simulation(config["initial_capital"], config["min_cagr"], config["tax_rate"], config["period_option"], config["years"])
        df_max = run_simulation(config["initial_capital"], config["max_cagr"], config["tax_rate"], config["period_option"], config["years"])
        df_range = pd.DataFrame({
            "年数": df_min["年数"],
            "min_balance": df_min["資産残高"],
            "max_balance": df_max["資産残高"]
        })

    over_100m = df_user[df_user["資産残高"] >= 100000000]
    first_reach_idx = over_100m.index[0] if not over_100m.empty else None

    st.subheader("🏁 1億円到達予測")
    if not over_100m.empty:
        first_reach = over_100m.iloc[0]
        st.success(f"あなたの設定 ({config['user_cagr']}%) では、**{first_reach['経過期間']}** (約{first_reach['年数']:.1f}年後) に資産が **1億円** を突破します！")
    else:
        st.warning(f"設定された期間内({config['years']}年)では1億円に到達しませんでした。")

    st.subheader("📈 資産推移シミュレーション")
    chart = create_chart(df_user, df_range, config)
    st.altair_chart(chart, use_container_width=True)

    st.subheader(f"📋 詳細シミュレーション表 ({config['period_option']})")
    
    def highlight_target_row(row):
        if first_reach_idx is not None and row.name == first_reach_idx:
            return ['background-color: #ffffcc; color: black'] * len(row)
        else:
            return [''] * len(row)

    display_cols = ["経過期間", "資産残高", "期間利益", "年間利益(累積)", "納税額"]
    st.dataframe(
        df_user[display_cols].style
        .format({
            "資産残高": "{:,.0f} 円", "期間利益": "{:,.0f} 円", 
            "年間利益(累積)": "{:,.0f} 円", "納税額": "{:,.0f} 円"
        })
        .apply(highlight_target_row, axis=1),
        height=500,
        use_container_width=True
    )

if __name__ == "__main__":

    main()
