
import re
import unicodedata

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# --------------------------------------------------
# GOOGLE SHEETS CONFIGURATION
# --------------------------------------------------
SHEET_ID = "1-Tqv5bH51dCTFxa9UMvLTBGr7zM0v1LpSZEN9GwM5OU"
SHEET_GID = "243879173"

CSV_URL = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/"
    f"export?format=csv&gid={SHEET_GID}"
)

DATA_SOURCE_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1-Tqv5bH51dCTFxa9UMvLTBGr7zM0v1LpSZEN9GwM5OU/edit?usp=sharing"
)

CATEGORICAL_FILTERS = [
    "Compressor Model",
    "Compressor type",
    "Compressor Condition",
    "Field Findings",
    "TDA Preliminary Findings",
]

DATE_FILTERS = [
    "Inspection Date",
    "Compressor Production Date",
]

EFFECT_COLS = [f"Effect {i}" for i in range(1, 5)]
FINAL_COLS = [f"Final Findings {i}" for i in range(1, 5)]

RECORD_COLS = [
    "SI No",
    "SR No",
    "Compressor Barcode",
    "Compressor Model",
    "Compressor type",
    "Compressor Condition",
    "Inspection Date",
    "Compressor Production Date",
    "Compressor Market Return Date",
    "Compressor Lifetime",
    "Field Findings",
    "TDA Preliminary Findings",
    *EFFECT_COLS,
    *FINAL_COLS,
    "Other comments",
    "Measurement data",
]

BLANK = "(Blank)"

st.set_page_config(
    page_title="Compressor TDA Dashboard",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Compressor TDA Dashboard")
st.caption(
    "Google Sheets · Database | Multi-level filters, "
    "occurrence counts and Pareto analysis"
)


# --------------------------------------------------
# DATA CLEANING
# --------------------------------------------------
def clean(value):
    if pd.isna(value):
        return ""

    s = unicodedata.normalize("NFKC", str(value))
    s = re.sub(r"[\u200b-\u200d\ufeff]", "", s)
    s = s.replace("\xa0", " ")

    # Convert literal backslash+n sequences into actual new lines.
    # This fixes values such as:
    # 1.Piston Colliding with Valve Leaf\n2.Rust at discharge chamber
    s = s.replace(r"\n", "\n").strip()

    if s.casefold() in {"nan", "none", "null", "nat"}:
        return ""

    return s


# --------------------------------------------------
# LOAD GOOGLE SHEETS DATA
# --------------------------------------------------
@st.cache_data(ttl=600, show_spinner="Loading Google Sheets data...")
def load_data():
    raw = pd.read_csv(
        CSV_URL,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
    )

    raw.columns = [clean(c) for c in raw.columns]
    raw = raw.loc[:, ~raw.columns.duplicated()].copy()

    mapping = {c.casefold(): c for c in raw.columns}

    # Normalize column names and create missing optional columns.
    for col in RECORD_COLS:
        actual = mapping.get(col.casefold())

        if actual and actual != col:
            raw = raw.rename(columns={actual: col})
        elif not actual:
            raw[col] = ""

    for col in RECORD_COLS:
        raw[col] = raw[col].map(clean)

    raw = raw.loc[
        ~raw[RECORD_COLS].eq("").all(axis=1)
    ].copy()

    for col in [
        *DATE_FILTERS,
        "Compressor Market Return Date",
    ]:
        raw[f"__date_{col}"] = pd.to_datetime(
            raw[col],
            errors="coerce",
            dayfirst=True,
        )

    return raw.reset_index(drop=True)


try:
    source = load_data()
except Exception as exc:
    st.error(f"Unable to read the Google Sheet: {exc}")
    st.info(
        "Make sure the sheet is accessible for CSV export, "
        "or configure authenticated access for a private sheet."
    )
    st.stop()

if source.empty:
    st.warning("No records found in the Database tab.")
    st.stop()


# --------------------------------------------------
# CATEGORICAL FILTERS
# --------------------------------------------------
def distinct_options(df, col):
    values = {v if v else BLANK for v in df[col]}

    return sorted(
        values,
        key=lambda x: (x == BLANK, x.casefold()),
    )


def categorical_filter(df, col):
    opts = distinct_options(df, col)
    key = f"filter_{col}"
    previous_key = f"prev_options_{col}"

    if key not in st.session_state:
        st.session_state[key] = opts.copy()

    old = st.session_state[key]
    previous = st.session_state.get(previous_key)

    # Preserve selections unless all previous options were selected.
    if previous is not None and set(old) == set(previous):
        st.session_state[key] = opts.copy()
    else:
        st.session_state[key] = [
            x for x in old if x in opts
        ]

    st.session_state[previous_key] = opts.copy()

    selected = st.multiselect(
        col,
        opts,
        key=key,
        placeholder="Choose values",
    )

    normalized = df[col].map(
        lambda v: v if v else BLANK
    )

    return df[normalized.isin(selected)]


# --------------------------------------------------
# DATE FILTERS
# --------------------------------------------------
def date_filter(df, col):
    st.markdown(f"**{col}**")
    parsed = df[f"__date_{col}"]

    mode = st.radio(
        f"{col} mode",
        [
            "All dates",
            "Date range",
            "Blank dates",
            "Date range + blank dates",
        ],
        horizontal=True,
        key=f"date_mode_{col}",
        label_visibility="collapsed",
    )

    if mode == "All dates":
        return df

    if mode == "Blank dates":
        return df[parsed.isna()]

    valid = parsed.dropna()

    if valid.empty:
        st.caption("No valid dates in the current selection.")

        if mode == "Date range + blank dates":
            return df[parsed.isna()]

        return df.iloc[0:0]

    start = valid.min().date()
    end = valid.max().date()

    chosen = st.date_input(
        f"{col} range",
        value=(start, end),
        min_value=start,
        max_value=end,
        key=f"range_{col}",
    )

    if not isinstance(chosen, (tuple, list)) or len(chosen) != 2:
        st.info("Choose both the start and end dates.")
        return df.iloc[0:0]

    low, high = chosen
    in_range = parsed.dt.date.between(low, high)

    if mode == "Date range + blank dates":
        in_range = in_range | parsed.isna()

    return df[in_range]


# --------------------------------------------------
# EFFECT AND FINAL FINDING FILTERS
# --------------------------------------------------
def finding_options(df, columns):
    values = set()

    for col in columns:
        values.update(v for v in df[col] if v)

    if df[columns].eq("").any(axis=1).any():
        values.add(BLANK)

    return sorted(
        values,
        key=lambda x: (x == BLANK, x.casefold()),
    )


def finding_filter(df, columns, title, key):
    options = finding_options(df, columns)
    state_key = f"finding_{key}"
    old_opts_key = f"previous_finding_options_{key}"

    if state_key not in st.session_state:
        # Select all options on initial dashboard loading.
        st.session_state[state_key] = options.copy()
    else:
        old = st.session_state[state_key]
        previous = st.session_state.get(old_opts_key, [])

        if set(old) == set(previous):
            st.session_state[state_key] = options.copy()
        else:
            st.session_state[state_key] = [
                x for x in old if x in options
            ]

    st.session_state[old_opts_key] = options.copy()

    selected = st.multiselect(
        title,
        options,
        key=state_key,
    )

    if not selected:
        return df.iloc[0:0]

    actual = [x for x in selected if x != BLANK]
    mask = df[columns].isin(actual).any(axis=1)

    # Blank is a filter option only; it is never counted as a finding.
    if BLANK in selected:
        mask = mask | df[columns].eq("").any(axis=1)

    return df[mask]


# --------------------------------------------------
# APPLY FILTERS
# --------------------------------------------------
with st.sidebar:
    st.header("🔎 Filters")

    if st.button("Reset all filters", use_container_width=True):
        prefixes = (
            "filter_",
            "prev_options_",
            "date_mode_",
            "range_",
            "finding_",
            "previous_finding_options_",
        )

        for key in list(st.session_state):
            if key.startswith(prefixes):
                del st.session_state[key]

        st.rerun()

    filtered = source.copy()

    # Sequential cascading filters.
    for column in CATEGORICAL_FILTERS:
        filtered = categorical_filter(filtered, column)

    st.divider()

    for column in DATE_FILTERS:
        filtered = date_filter(filtered, column)

    st.divider()

    filtered = finding_filter(
        filtered,
        EFFECT_COLS,
        "Effect",
        "effects",
    )

    filtered = finding_filter(
        filtered,
        FINAL_COLS,
        "Final Finding",
        "final",
    )


st.caption(
    "Filters are applied sequentially from top to bottom. "
    "Effect and Final Finding selections filter compressor records. "
    "Blank finding cells are excluded from counts and charts."
)


# --------------------------------------------------
# REUSABLE WRAPPED HTML TABLE
# --------------------------------------------------
def render_wrapped_table(
    df,
    table_class,
    max_height=520,
    column_widths=None,
):
    """
    Render a scrollable HTML table.

    pre-wrap preserves actual newlines.
    overflow-wrap allows long text to wrap inside cells.
    column_widths controls individual column widths.
    """
    if df.empty:
        st.info("No data to display.")
        return

    html_table = df.to_html(
        index=False,
        escape=True,
        classes=table_class,
        border=0,
    )

    widths_css = ""

    if column_widths:
        for column_name, width in column_widths.items():
            if column_name in df.columns:
                position = list(df.columns).index(column_name) + 1

                widths_css += (
                    f"\n.{table_class} th:nth-child({position}), "
                    f".{table_class} td:nth-child({position}) "
                    f"{{ min-width: {width}px; max-width: {width}px; }}"
                )

    st.markdown(
        f"""
        <style>
        .{table_class}-wrap {{
            width: 100%;
            max-height: {max_height}px;
            overflow: auto;
            border: 1px solid #d6d6d6;
            border-radius: 6px;
        }}

        table.{table_class} {{
            border-collapse: collapse;
            width: max-content;
            min-width: 100%;
            table-layout: auto;
            font-size: 13px;
        }}

        table.{table_class} th,
        table.{table_class} td {{
            border: 1px solid #d6d6d6;
            padding: 8px 10px;
            text-align: left;
            vertical-align: top;

            /* Preserve line breaks and wrap long text. */
            white-space: pre-wrap !important;
            overflow-wrap: anywhere !important;
            word-break: normal;

            min-width: 120px;
            max-width: 420px;
            line-height: 1.45;
        }}

        table.{table_class} th {{
            position: sticky;
            top: 0;
            z-index: 2;
            background: #f0f2f6;
            color: #111111;
            font-weight: 700;
        }}

        table.{table_class} tr:nth-child(even) td {{
            background: #fafafa;
        }}

        {widths_css}
        </style>

        <div class="{table_class}-wrap">
            {html_table}
        </div>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------
# FINDING COUNTS
# --------------------------------------------------
def finding_counts(df, columns, selected, unique=False):
    if df.empty or not selected:
        return pd.DataFrame(columns=["Finding", "Count"])

    # Exclude blanks and the filter-only (Blank) option.
    actual_selected = [
        value
        for value in selected
        if value not in (BLANK, "")
    ]

    if not actual_selected:
        return pd.DataFrame(columns=["Finding", "Count"])

    working = df[columns].replace("", pd.NA)

    if unique:
        counts = {}

        for _, row in working.iterrows():
            for value in set(row.dropna()):
                if value in actual_selected:
                    counts[value] = counts.get(value, 0) + 1

        series = pd.Series(counts, dtype="int64")
    else:
        series = working.stack().value_counts()
        series = series[series.index.isin(actual_selected)]

    if series.empty:
        return pd.DataFrame(columns=["Finding", "Count"])

    result = series.rename_axis("Finding").reset_index(name="Count")

    return result.sort_values(
        ["Count", "Finding"],
        ascending=[False, True],
    ).reset_index(drop=True)


# --------------------------------------------------
# CHART FORMATTING
# --------------------------------------------------
def chart_style(fig, x_title, y_title):
    fig.update_layout(
        template="plotly_white",
        height=440,
        margin=dict(l=35, r=50, t=35, b=115),
        xaxis=dict(
            title=dict(
                text=x_title,
                font=dict(
                    color="black",
                    size=14,
                    family="Arial Black",
                ),
            ),
            tickfont=dict(
                color="black",
                size=11,
                family="Arial Black",
            ),
            tickangle=-35,
        ),
        yaxis=dict(
            title=dict(
                text=y_title,
                font=dict(
                    color="black",
                    size=14,
                    family="Arial Black",
                ),
            ),
            tickfont=dict(
                color="black",
                size=11,
                family="Arial Black",
            ),
        ),
    )

    return fig


def bar_chart(counts, label):
    fig = go.Figure(
        go.Bar(
            x=counts[label],
            y=counts["Count"],
            text=counts["Count"],
            textposition="outside",
            textfont=dict(
                color="black",
                size=12,
                family="Arial Black",
            ),
            cliponaxis=False,
        )
    )

    chart_style(fig, label, "Compressor count")

    fig.update_yaxes(
        range=[0, max(1, counts["Count"].max()) * 1.22]
    )

    return fig


def pareto_chart(counts):
    if counts.empty:
        return go.Figure()

    total = counts["Count"].sum()

    if total <= 0:
        return go.Figure()

    cumulative = counts["Count"].cumsum() / total * 100

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=counts["Finding"],
            y=counts["Count"],
            name="Count",
            text=counts["Count"],
            textposition="outside",
            textfont=dict(
                color="black",
                size=12,
                family="Arial Black",
            ),
            cliponaxis=False,
        )
    )

    fig.add_trace(
        go.Scatter(
            x=counts["Finding"],
            y=cumulative,
            mode="lines+markers",
            name="Cumulative %",
            yaxis="y2",
            line=dict(width=2),
        )
    )

    chart_style(fig, "Finding", "Occurrence count")

    fig.update_layout(
        yaxis=dict(
            range=[0, max(1, counts["Count"].max()) * 1.25]
        ),
        yaxis2=dict(
            title=dict(
                text="Cumulative %",
                font=dict(
                    color="black",
                    family="Arial Black",
                ),
            ),
            tickfont=dict(
                color="black",
                family="Arial Black",
            ),
            overlaying="y",
            side="right",
            range=[0, 105],
            ticksuffix="%",
        ),
        legend=dict(
            orientation="h",
            y=1.13,
            x=0,
        ),
    )

    return fig


# --------------------------------------------------
# KPI METRICS
# --------------------------------------------------
m1, m2, m3 = st.columns(3)

m1.metric("Total compressors", f"{len(source):,}")
m2.metric("Filtered compressors", f"{len(filtered):,}")
m3.metric(
    "Filtered share",
    f"{len(filtered) / len(source) * 100:.1f}%",
)

if filtered.empty:
    st.warning(
        "No compressor records match the current filters. "
        "Adjust the sidebar selections."
    )
    st.stop()


# --------------------------------------------------
# COMPRESSOR MODEL SUMMARY
# --------------------------------------------------
st.subheader("Compressor Model Summary")

models = (
    filtered["Compressor Model"]
    .replace("", BLANK)
    .value_counts()
    .rename_axis("Compressor Model")
    .reset_index(name="Count")
)

left, right = st.columns([1, 2])

with left:
    st.dataframe(
        models,
        use_container_width=True,
        hide_index=True,
    )

with right:
    st.plotly_chart(
        bar_chart(models, "Compressor Model"),
        use_container_width=True,
    )


# --------------------------------------------------
# EFFECT ANALYSIS
# --------------------------------------------------
st.subheader("Effect Analysis")

st.caption(
    "A compressor can have up to four effects. "
    "Blank cells are excluded from counts and charts."
)

count_mode = st.radio(
    "Counting method",
    ["Occurrences", "Unique compressors per finding"],
    horizontal=True,
)

unique = count_mode == "Unique compressors per finding"

effect_selected = st.session_state.get("finding_effects", [])
final_selected = st.session_state.get("finding_final", [])

effects = finding_counts(
    filtered,
    EFFECT_COLS,
    effect_selected,
    unique,
)

finals = finding_counts(
    filtered,
    FINAL_COLS,
    final_selected,
    unique,
)

left, right = st.columns([1, 2])

with left:
    render_wrapped_table(
        effects,
        "effects-count-table",
        max_height=520,
        column_widths={
            "Finding": 360,
            "Count": 100,
        },
    )

with right:
    if not effects.empty:
        st.plotly_chart(
            pareto_chart(effects),
            use_container_width=True,
        )
    else:
        st.info("No selected effects in the filtered data.")


# --------------------------------------------------
# FINAL FINDING ANALYSIS
# --------------------------------------------------
st.subheader("Final Finding Analysis")

left, right = st.columns([1, 2])

with left:
    render_wrapped_table(
        finals,
        "final-count-table",
        max_height=520,
        column_widths={
            "Finding": 360,
            "Count": 100,
        },
    )

with right:
    if not finals.empty:
        st.plotly_chart(
            pareto_chart(finals),
            use_container_width=True,
        )
    else:
        st.info("No selected final findings in the filtered data.")


# --------------------------------------------------
# FINDING SOURCE AUDIT
# --------------------------------------------------
with st.expander("Finding Source Audit"):
    audit = pd.DataFrame([
        {
            "Source column": col,
            "Non-blank cells": int(filtered[col].ne("").sum()),
        }
        for col in EFFECT_COLS + FINAL_COLS
    ])

    st.dataframe(
        audit,
        use_container_width=True,
        hide_index=True,
    )

    st.caption(
        "Blank Effect and Final Finding cells are excluded from count "
        "tables and Pareto charts. The (Blank) filter option can still "
        "locate records with missing findings. Occurrence counts may "
        "exceed the number of compressors."
    )


# --------------------------------------------------
# FILTERED COMPRESSOR RECORDS
# --------------------------------------------------
st.subheader("Filtered Compressor Records")

st.caption(
    "All columns wrap long text. Effect columns are 260 px wide, "
    "Final Finding columns are 300 px wide. Scroll horizontally to view "
    "all columns. The table shows 100 rows per page; the CSV download "
    "contains every filtered record."
)

records = filtered[RECORD_COLS].copy()

page_size = 100
page_count = max(1, (len(records) + page_size - 1) // page_size)

page_number = st.number_input(
    "Table page",
    min_value=1,
    max_value=page_count,
    value=1,
    step=1,
    key="filtered_records_page",
    help=f"{page_count} page(s), {page_size} rows per page.",
)

start_index = (int(page_number) - 1) * page_size
end_index = min(start_index + page_size, len(records))
page_records = records.iloc[start_index:end_index]

st.caption(
    f"Showing rows {start_index + 1:,}–{end_index:,} "
    f"of {len(records):,}"
)

render_wrapped_table(
    page_records,
    "records-table",
    max_height=720,
    column_widths={
        "Effect 1": 260,
        "Effect 2": 260,
        "Effect 3": 260,
        "Effect 4": 260,
        "Final Findings 1": 300,
        "Final Findings 2": 300,
        "Final Findings 3": 300,
        "Final Findings 4": 300,
        "Field Findings": 280,
        "TDA Preliminary Findings": 300,
        "Other comments": 280,
        "Measurement data": 280,
    },
)

st.download_button(
    "Download filtered records (CSV)",
    data=records.to_csv(index=False).encode("utf-8-sig"),
    file_name="filtered_compressor_tda.csv",
    mime="text/csv",
)


# --------------------------------------------------
# DATA SOURCE
# --------------------------------------------------
st.divider()
st.subheader("Data Source")

st.markdown(
    f"[Updated Data Logger]({DATA_SOURCE_URL})"
)
