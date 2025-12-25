import streamlit as st
import pandas as pd
import altair as alt
import os
import calendar
from datetime import timedelta

# ============================================================================
# 1. PAGE CONFIGURATION
# ============================================================================

st.set_page_config(
    page_title="Toss Transactions Analysis Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Colors
COLOR_DEP = '#0b5394'  # Deep Blue
COLOR_WTH = '#990000'  # Deep Red

# ============================================================================
# 2. DATA LOADING & PROCESSING
# ============================================================================

INPUT_FILE = "latest_transactions.xlsx"
CSV_OUTPUT = "transactions.csv"

@st.cache_data
def load_and_clean_data(uploaded_file):
    if uploaded_file is None:
        return None

    df = pd.read_excel(uploaded_file, sheet_name=0, skiprows=8)
    
    # Rename & Standardize
    df = df.rename(columns={
        '거래 일시': 'Date', '적요': 'Remarks', '거래 유형': 'Transaction_Type',
        '거래 기관': 'Bank_Name', '계좌번호': 'Account_Number',
        '거래 금액': 'Transaction_Amount', '거래 후 잔액': 'Balance', '메모': 'Memo'
    })
    
    df = df.drop(columns=['Unnamed: 0', 'Memo'])
    df["Account_Number"] = df["Account_Number"].fillna(0).astype(int)
    
    # Translate
    df['Transaction_Type'] = df['Transaction_Type'].replace({
        '체크카드결제': 'Check Card', '입금': 'Deposit', '출금': 'Withdrawal',
        '프로모션입금': 'Cashback', '오픈뱅킹': 'Open Banking', '이자입금': 'Interest Deposit',
        'ATM출금': 'ATM Withdrawal', 'KB국민은행': 'KB Bank', 'BC카드': 'ATM Deposit'
    })
    
    # Datetime Processing
    df['Date'] = pd.to_datetime(df['Date'], format='%Y.%m.%d %H:%M:%S')
    df['Time'] = df['Date'].dt.time
    df['DateOnly'] = df['Date'].dt.date
    df['Month'] = df['Date'].dt.to_period('M').astype(str)
    
    return df

@st.cache_data
def get_kpi_metrics(df):
    """
    Calculates 6 simple metrics for the provided dataframe.
    """
    if df.empty:
        return {k: 0 for k in ['deposit', 'withdrawal', 'balance', 'count', 'cashback', 'interest']}

    dep = df[df['Transaction_Amount'] > 0]['Transaction_Amount'].sum()
    withd = abs(df[df['Transaction_Amount'] < 0]['Transaction_Amount'].sum())
    count = len(df)
    
    # Cashback and Interest
    cashback = df[df['Transaction_Type'] == 'Cashback']['Transaction_Amount'].sum()
    interest = df[df['Transaction_Type'] == 'Interest Deposit']['Transaction_Amount'].sum()
    
    # Balance (Latest snapshot)
    bal = df.sort_values('Date', ascending=False)['Balance'].iloc[0] if not df.empty else 0
    
    return {
        'deposit': dep,
        'withdrawal': withd,
        'balance': bal,
        'count': count,
        'cashback': cashback,
        'interest': interest
    }

# ============================================================================
# 3. ALTAIR PLOTTING FUNCTIONS
# ============================================================================

def make_donut_chart(df):
    """Income vs Expense Donut Chart with ₩ Labels"""
    inc = df[df['Transaction_Amount'] > 0]['Transaction_Amount'].sum()
    exp = abs(df[df['Transaction_Amount'] < 0]['Transaction_Amount'].sum())
    
    # Ensure COLORS are defined
    c_dep = COLOR_DEP if 'COLOR_DEP' in globals() else '#2E86C1'
    c_wth = COLOR_WTH if 'COLOR_WTH' in globals() else '#E74C3C'

    source = pd.DataFrame({
        'Category': ['Income', 'Expenses'],
        'Value': [inc, exp],
    })
    
    # --- NEW: Create a formatted label column ---
    source['Label'] = source['Value'].apply(lambda x: f"₩{x:,.0f}")
    
    base = alt.Chart(source).encode(
        theta=alt.Theta("Value", stack=True)
    )
    
    pie = base.mark_arc(innerRadius=60).encode(
        color=alt.Color("Category", scale=alt.Scale(domain=['Income', 'Expenses'], range=[c_dep, c_wth])),
        order=alt.Order("Value", sort="descending"),
        tooltip=["Category", alt.Tooltip("Label", title="Amount")] # Updated tooltip to use formatted label
    )
    
    text = base.mark_text(radius=100, size=14, fontWeight="bold", align="center").encode(
        text=alt.Text("Label"), # Use the pre-formatted 'Label' column here
        order=alt.Order("Value", sort="descending"),
        color=alt.value("white")  
    )
    
    return (pie + text).properties(title="").configure_view(strokeWidth=0).configure_axis(grid=False)

def make_bar_trend(df):
    """Monthly Income vs Expense Grouped Bar"""
    monthly = df.groupby([df['Date'].dt.to_period('M').astype(str), 'Transaction_Type'])['Transaction_Amount'].sum().reset_index()
    monthly.columns = ['Month', 'Type', 'Amount']
    
    inc = df[df['Transaction_Amount'] > 0].groupby(df['Date'].dt.to_period('M').astype(str))['Transaction_Amount'].sum()
    exp = df[df['Transaction_Amount'] < 0].groupby(df['Date'].dt.to_period('M').astype(str))['Transaction_Amount'].sum().abs()
    
    trend_df = pd.DataFrame({'Month': inc.index, 'Income': inc.values})
    trend_df = trend_df.merge(pd.DataFrame({'Month': exp.index, 'Expense': exp.values}), on='Month', how='outer').fillna(0)
    trend_melted = trend_df.melt('Month', var_name='Category', value_name='Amount')
    
    base = alt.Chart(trend_melted).encode(
        y=alt.Y('Month', axis=alt.Axis(title='Month', labelAngle=0, grid=False)),
        x=alt.X('Amount', axis=alt.Axis(title='Amount (KRW)', grid=False)),
        color=alt.Color('Category', scale=alt.Scale(domain=['Income', 'Expense'], range=[COLOR_DEP, COLOR_WTH])),
        tooltip=['Month', alt.Tooltip('Amount', format=',.0f')],
        yOffset='Category:N'
    )

    bars = base.mark_bar()

    text = base.mark_text(align='left', dx=2).encode(
        text=alt.Text('Amount', format=',.0f')
    )
    
    return (bars + text).configure_view(strokeWidth=0)

def make_net_income_chart(df):
    """Diverging Bar Chart for Net Income"""
    inc = df[df['Transaction_Amount'] > 0].groupby(df['Date'].dt.to_period('M').astype(str))['Transaction_Amount'].sum()
    exp = df[df['Transaction_Amount'] < 0].groupby(df['Date'].dt.to_period('M').astype(str))['Transaction_Amount'].sum().abs()
    
    net = (inc - exp).reset_index(name='NetIncome')
    net.columns = ['Month', 'NetIncome']
    
    base = alt.Chart(net).encode(
        x=alt.X('Month', axis=alt.Axis(labelAngle=-0, grid=False, title="Month")),
        y=alt.Y('NetIncome', axis=alt.Axis(title='Net Income (KRW)', grid=False)),
        tooltip=['Month', alt.Tooltip('NetIncome', format=',.0f')],
        color=alt.condition(
            alt.datum.NetIncome > 0,
            alt.value(COLOR_DEP),
            alt.value(COLOR_WTH)
        )
    )

    bars = base.mark_bar()

    text_pos = base.mark_text(
        baseline='middle',
        dy=-10  # Above bar
    ).encode(
        text=alt.Text('NetIncome', format=',.0f')
    ).transform_filter(
        alt.datum.NetIncome > 0
    )

    text_neg = base.mark_text(
        baseline='middle',
        dy=10  # Below bar
    ).encode(
        text=alt.Text('NetIncome', format=',.0f')
    ).transform_filter(
        alt.datum.NetIncome <= 0
    )

    return (bars + text_pos + text_neg).configure_view(strokeWidth=0)

def make_heatmap(df):
    """Hourly Activity Histogram"""
    df['Hour'] = df['Date'].dt.hour
    hourly = df['Hour'].value_counts().reset_index()
    hourly.columns = ['Hour', 'Count']
    
    base = alt.Chart(hourly).encode(
        x=alt.X('Hour', bin=False, scale=alt.Scale(domain=[0, 23]), axis=alt.Axis(grid=False)),
        y=alt.Y('Count', title='Transactions', axis=alt.Axis(grid=False)),
        tooltip=['Hour', 'Count']
    )

    bars = base.mark_bar(color='#351c75')

    text = base.mark_text(align='center', baseline='bottom', dy=-5).encode(
        text='Count'
    )
    
    return (bars + text).configure_view(strokeWidth=0)

def make_remarks_chart(df, is_negative=True):
    """Top 15 Remarks Bar Chart"""
    if is_negative:
        # Withdrawals
        subset = df[df['Transaction_Amount'] < 0]
        color = COLOR_WTH
        # title_text = "Top 15 Withdrawals by Remarks"
    else:
        # Deposits
        subset = df[df['Transaction_Amount'] > 0]
        color = COLOR_DEP
        # title_text = "Top 15 Deposits by Remarks"

    if subset.empty:
        return alt.Chart(pd.DataFrame({'a':[]})).mark_bar()

    grouped = subset.groupby('Remarks')['Transaction_Amount'].sum().abs().reset_index()
    grouped = grouped.sort_values('Transaction_Amount', ascending=False).head(15)
    
    base = alt.Chart(grouped).encode(
        x=alt.X('Transaction_Amount', title='Amount (KRW)', axis=alt.Axis(grid=False)),
        y=alt.Y('Remarks', sort='-x', title=None, axis=alt.Axis(grid=False)), # Sorted by amount desc
        tooltip=['Remarks', alt.Tooltip('Transaction_Amount', format=',.0f')]
    )

    bars = base.mark_bar(color=color)

    text = base.mark_text(align='left', dx=2).encode(
        text=alt.Text('Transaction_Amount', format=',.0f')
    )
    
    return (bars + text).configure_view(strokeWidth=0)

def make_transaction_type_chart(df):
    """Total Amount by Transaction Type Bar Chart"""
    # Group and Sum
    stats = df.groupby('Transaction_Type')['Transaction_Amount'].sum().reset_index()
    stats['Abs_Amount'] = stats['Transaction_Amount'].abs()
    
    # Sort by Abs Amount descending
    stats = stats.sort_values('Abs_Amount', ascending=False)
    
    # Define Colors
    type_colors = {
        'Deposit': '#0b5394', 'Withdrawal': '#990000', 'Check Card': '#FF6347',
        'ATM Deposit': '#3CB371', 'KB Bank': '#66CDAA', 'ATM Withdrawal': '#CD5C5C',
        'Open Banking': '#20B2AA', 'Cashback': '#FFD700', 'Interest Deposit': '#48D1CC'
    }
    
    # Create the chart
    base = alt.Chart(stats).encode(
        x=alt.X('Transaction_Type', sort='-y', axis=alt.Axis(labelAngle=-90, grid=False, title=None)),
        y=alt.Y('Abs_Amount', title='Total Amount (KRW)', axis=alt.Axis(grid=False)),
        color=alt.Color('Transaction_Type', 
                        scale=alt.Scale(domain=list(type_colors.keys()), range=list(type_colors.values())),
                        legend=None)
    )
    
    bars = base.mark_bar()
    
    text = base.mark_text(dy=-10).encode(
        text=alt.Text('Abs_Amount', format=',.0f')
    )
    
    return (bars + text ).properties().configure_view(strokeWidth=0)

# ============================================================================
# 4. MAIN LAYOUT
# ============================================================================

def main():
    # Header
    st.markdown("# Financial Dashboard")
    st.markdown("### Overview of your personal finances with **interactive** insights.")
    st.write("") 

    # File Uploader
    uploaded_file = st.file_uploader("Upload your recent transactions (.xlsx)", type=['xlsx'])

    if uploaded_file is None:
        st.info("👋 Please upload your Transaction History Excel file to begin.")
        st.stop()

    # Load Data
    raw_df = load_and_clean_data(uploaded_file)

    if raw_df is None:
        st.error("Failed to load data. Please check the file format.")
        return

    # --- Filters ---
    st.write("### Date Filters")
    
    # 1. Year Filter
    available_years = sorted(raw_df['Date'].dt.year.unique())
    # Default to latest year if available, else all
    default_years = [available_years[-1]] if available_years else available_years
    
    selected_years = st.pills(
        "Years to compare", 
        available_years, 
        default=default_years, 
        selection_mode="multi"
    )
    
    if not selected_years:
        st.warning("Please select at least one year.")
        return

    # Filter by Year
    year_filtered_df = raw_df[raw_df['Date'].dt.year.isin(selected_years)]
    
    # 2. Month Filter
    # Get available months from the year-filtered data
    available_months_int = sorted(year_filtered_df['Date'].dt.month.unique())
    # Map to names or keep as int? Let's use names for better UI
    month_map = {m: calendar.month_name[m] for m in available_months_int}
    month_options = [month_map[m] for m in available_months_int]
    
    selected_months_str = st.pills(
        "Months to view",
        month_options,
        default=month_options,
        selection_mode="multi"
    )
    
    # Back to ints
    reverse_month_map = {v: k for k, v in month_map.items()}
    selected_months_int = [reverse_month_map[m] for m in selected_months_str]
    
    if not selected_months_int:
        st.warning("Please select at least one month.")
        filtered_df = year_filtered_df # Fallback? Or empty? let's show empty
        filtered_df = year_filtered_df[year_filtered_df['Date'].dt.month.isin([])]
    else:
        filtered_df = year_filtered_df[year_filtered_df['Date'].dt.month.isin(selected_months_int)]

    # --- KPI Section (Top Row) ---
    metrics = get_kpi_metrics(filtered_df)
    
    st.markdown(f"### Financial Summary")
    # Row 1 KPIs
    kpi1 = st.columns(3)
    kpi1[0].metric("Total Deposits", f"₩{metrics['deposit']:,.0f}")
    kpi1[1].metric("Total Withdrawals", f"₩{metrics['withdrawal']:,.0f}")
    kpi1[2].metric("Current Balance", f"₩{metrics['balance']:,.0f}")
    
    # Row 2 KPIs
    kpi2 = st.columns(3)
    kpi2[0].metric("Transaction Count", f"{metrics['count']:,}")
    kpi2[1].metric("Cashback", f"₩{metrics['cashback']:,.0f}")
    kpi2[2].metric("Interest Deposit", f"₩{metrics['interest']:,.0f}")

    st.write("---")

    # --- Charts Grid ---
    
    # --- Privacy Mode ---
    privacy_mode = st.sidebar.checkbox("Privacy Mode", value=True, help="Hide sensitive transaction details.")

    # --- Charts Grid ---
    
    # Row 1: Trends & Cash Flow
    r1_cols = st.columns([1.5, 1])
    with r1_cols[0].container(border=True, height=450):
        st.markdown("### Monthly Income vs Expenses")
        st.altair_chart(make_bar_trend(filtered_df), use_container_width=True)

    with r1_cols[1].container(border=True, height=450):
        st.markdown("### Overall Cash Flow Distribution")
        st.altair_chart(make_donut_chart(filtered_df), use_container_width=True)

    # Row 2: Net Income & Heatmap
    r2_cols = st.columns(2)
    with r2_cols[0].container(border=True, height=450):
        st.markdown("### Net Income Analysis")
        st.altair_chart(make_net_income_chart(filtered_df), use_container_width=True)

    with r2_cols[1].container(border=True, height=450):
        st.markdown("### Transactions Count by Hours. 24 hours")
        st.altair_chart(make_heatmap(filtered_df), use_container_width=True)

    # Row 3: Remarks Analysis (Top 15)
    r3_cols = st.columns(2)
    with r3_cols[0].container(border=True, height=480): # Taller for 15 bars
        st.markdown("### Top 15 Withdrawals")
        st.altair_chart(make_remarks_chart(filtered_df, is_negative=True), use_container_width=True)
    
    with r3_cols[1].container(border=True, height=480): 
        st.markdown("### Top 15 Deposits")
        st.altair_chart(make_remarks_chart(filtered_df, is_negative=False), use_container_width=True)

    # Row 4: Transaction Types & Raw Data
    st.write("")
    r4_cols = st.columns(2)
    
    with r4_cols[0].container(border=True, height=450):
        st.markdown("### Total Amount by Transaction Types")
        st.altair_chart(make_transaction_type_chart(filtered_df), use_container_width=True)

    with r4_cols[1].container(border=True, height=450):
        st.markdown("### Raw Transaction Data")
        
        display_df = filtered_df[['Date', 'Transaction_Type', 'Remarks', 'Transaction_Amount', 'Balance', 'Bank_Name']].copy()
        
        if privacy_mode:
            # Mask sensitive columns
            display_df['Remarks'] = "****"
            display_df['Transaction_Amount'] = 0 # or "****" but numeric column might need number for config? 
            # Actually st.dataframe handles mixed types, but let's be safe and stringify if we want strict masking, 
            # OR just hide the values. 
            # Let's stringify specific columns for display to allow "****"
            display_df['Transaction_Amount'] = "****"
            display_df['Balance'] = "****"
            display_df['Bank_Name'] = "****"
            
            # Since we changed types to string for masking, column_config number formatting might break or be ignored.
            # That's fine, security first.
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                 column_config={
                    "Date": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
                }
            )
        else:
            # Normal Display
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Date": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm"),
                    "Transaction_Amount": st.column_config.NumberColumn(format="₩%d"),
                    "Balance": st.column_config.NumberColumn(format="₩%d"),
                }
            )

if __name__ == "__main__":
    main()