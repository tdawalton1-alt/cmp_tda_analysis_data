
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
    "finding counts and Pareto analysis"
)


# --------------------------------------------------
# DATA CLEANING AND LOADING
# --------------------------------------------------
def clean(value):
    if pd.isna(value):
        return ""

    value = unicodedata.normalize("NFKC", str(value))
    value = re.sub(r"[\u200b-\u200d\ufeff]", "", value)
    value = value.replace("\xa0", " ").strip()

    if value.casefold() in {"nan", "none", "null", "nat"}:
        return ""

    return value


@st.cache_data(ttl=600, show_spinner="Loading Google Sheets data...")
def load_data():
    raw = pd.read_csv(
        CSV_URL,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
    )

    raw.columns = [clean(column) for column in raw.columns]
    raw = raw.loc[:, ~raw.columns.duplicated()].copy()

    column_mapping = {
        column.casefold(): column
        for column in raw.columns
    }

    # Normalize column names and create missing optional columns.
    for column in RECORD_COLS:
        actual = column_mapping.get(column.casefold())

        if actual and actual != column:
            raw = raw.rename(columns={actual: column})
        elif not actual:
            raw[column] = ""

    for column in RECORD_COLS:
        raw[column] = raw[column].map(clean)

    # Remove rows that are completely empty across the dashboard fields.
    raw = raw.loc[
        ~raw[RECORD_COLS].eq("").all(axis=1)
    ].copy()

    # Parse dates for date filters.
    for column in [
        *DATE_FILTERS,
        "Compressor Market Return Date",
    ]:
        raw[f"__date_{column}"] = pd.to_datetime(
            raw[column],
            errors="coerce",
            dayfirst=True,
        )

    return raw.reset_index(drop=True)


try:
    source = load_data()
except Exception as exc:
    st.error(f"Unable to read the Google Sheet: {exc}")
    st.info(
        "Make sure the sheet is accessible for CSV export. "
        "If the sheet is private, configure authenticated access."
    )
    st.stop()

if source.empty:
    st.warning("No records found in the Database tab.")
    st.stop()


# --------------------------------------------------
# CATEGORICAL FILTERS
# --------------------------------------------------
def distinct_options(df, column):
    values = {
        value if value else BLANK
        for value in df[column]
    }

    return sorted(
        values,
        key=lambda value: (
            value == BLANK,
            value.casefold(),
        ),
    )


def categorical_filter(df, column):
    options = distinct_options(df, column)
    state_key = f"filter_{column}"
    previous_key = f"prev_options_{column}"

    if state_key not in st.session_state:
        st.session_state[state_key] = options.copy()
    else:
        old_selection = st.session_state[state_key]
        previous_options = st.session_state.get(previous_key)

        if (
            previous_options is not None
            and set(old_selection) == set(previous_options)
        ):
            st.session_state[state_key] = options.copy()
        else:
            st.session_state[state_key] = [
                value
                for value in old_selection
                if value in options
            ]

    st.session_state[previous_key] = options.copy()

    selected = st.multiselect(
        column,
        options,
        key=state_key,
        placeholder="Choose values",
    )

    normalized = df[column].map(
        lambda value: value if value else BLANK
    )

    return df[normalized.isin(selected)]


# --------------------------------------------------
# DATE FILTERS
# --------------------------------------------------
def date_filter(df, column):
    st.markdown(f"**{column}**")

    parsed = df[f"__date_{column}"]

    mode = st.radio(
        f"{column} mode",
        [
            "All dates",
            "Date range",
            "Blank dates",
            "Date range + blank dates",
        ],
        horizontal=True,
        key=f"date_mode_{column}",
        label_visibility="collapsed",
    )

    if mode == "All dates":
        return df

    if mode == "Blank dates":
        return df[parsed.isna()]

    valid_dates = parsed.dropna()

    if valid_dates.empty:
        st.caption("No valid dates in the current selection.")

        if mode == "Date range + blank dates":
            return df[parsed.isna()]

        return df.iloc[0:0]

    start_date = valid_dates.min().date()
    end_date = valid_dates.max().date()

    chosen = st.date_input(
        f"{column} range",
        value=(start_date, end_date),
        min_value=start_date,
        max_value=end_date,
        key=f"range_{column}",
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

    for column in columns:
        values.update(
            value
            for value in df[column]
            if value
        )

    # Blank is available as a filter option only.
    # It is excluded from finding counts and charts.
    if df[columns].eq("").any(axis=1).any():
        values.add(BLANK)

    return sorted(
        values,
        key=lambda value: (
            value == BLANK,
            value.casefold(),
        ),
    )


def finding_filter(df, columns, title, key):
    options = finding_options(df, columns)
    state_key = f"finding_{key}"
    previous_key = f"previous_finding_options_{key}"

    if state_key not in st.session_state:
        # Select all findings automatically on initial loading.
        st.session_state[state_key] = options.copy()
    else:
        old_selection = st.session_state[state_key]
        previous_options = st.session_state.get(previous_key, [])

        if set(old_selection) == set(previous_options):
            st.session_state[state_key] = options.copy()
        else:
            st.session_state[state_key] = [
                value
                for value in old_selection
                if value in options
            ]

    st.session_state[previous_key] = options.copy()

    selected = st.multiselect(
        title,
        options,
        key=state_key,
    )

    if not selected:
        return df.iloc[0:0]

    actual_selected = [
        value
        for value in selected
        if value != BLANK
    ]

    # Include rows matching any selected nonblank finding.
    mask = df[columns].isin(actual_selected).any(axis=1)

    # Selecting Blank can also include records with a blank finding cell.
    # Blank cells are still never counted as a finding.
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

    # Sequential cascading categorical filters.
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
    "Blank finding cells are excluded from finding counts and charts."
)


# --------------------------------------------------
# FINDING COUNT CALCULATION
# --------------------------------------------------
def finding_counts(df, columns, selected, unique=False):
    """
    Count selected nonblank findings only.

    Occurrences:
        Count every appearance across the four finding columns.

    Unique compressors per finding:
        Count a compressor no more than once per finding.
    """
    if df.empty or not selected:
        return pd.DataFrame(columns=["Finding", "Count"])

    actual_selected = [
        value
        for value in selected
        if value not in (BLANK, "")
    ]

    if not actual_selected:
        return pd.DataFrame(columns=["Finding", "Count"])

    # Empty cells become NA and are excluded from counts.
    working = df[columns].replace("", pd.NA)

    if unique:
        counts = {}

        for _, row in working.iterrows():
            findings_for_compressor = set(row.dropna())

            for finding in findings_for_compressor:
                if finding in actual_selected:
                    counts[finding] = counts.get(finding, 0) + 1

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
metric1, metric2, metric3 = st.columns(3)

metric1.metric(
    "Total compressors",
    f"{len(source):,}",
)

metric2.metric(
    "Filtered compressors",
    f"{len(filtered):,}",
)

metric3.metric(
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
    "Blank cells are not counted. Occurrences are counted by default."
)

count_mode = st.radio(
    "Counting method",
    [
        "Occurrences",
        "Unique compressors per finding",
    ],
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
    st.dataframe(
        effects,
        use_container_width=True,
        hide_index=True,
    )

with right:
    if not effects.empty:
        st.plotly_chart(
            pareto_chart(effects),
            use_container_width=True,
        )
    else:
        st.info("No selected nonblank effects in the filtered data.")


# --------------------------------------------------
# FINAL FINDING ANALYSIS
# --------------------------------------------------
st.subheader("Final Finding Analysis")

left, right = st.columns([1, 2])

with left:
    st.dataframe(
        finals,
        use_container_width=True,
        hide_index=True,
    )

with right:
    if not finals.empty:
        st.plotly_chart(
            pareto_chart(finals),
            use_container_width=True,
        )
    else:
        st.info(
            "No selected nonblank final findings in the filtered data."
        )


# --------------------------------------------------
# FINDING SOURCE AUDIT
# --------------------------------------------------
with st.expander("Finding Source Audit"):
    audit = pd.DataFrame(
        [
            {
                "Source column": column,
                "Non-blank cells": int(filtered[column].ne("").sum()),
            }
            for column in EFFECT_COLS + FINAL_COLS
        ]
    )

    st.dataframe(
        audit,
        use_container_width=True,
        hide_index=True,
    )

    st.caption(
        "Blank Effect and Final Finding cells are excluded from count "
        "tables and Pareto charts. The (Blank) filter option can still "
        "be used to locate records with missing findings. "
        "Occurrence counts may exceed the number of compressors."
    )


# --------------------------------------------------
# FILTERED COMPRESSOR RECORDS
# --------------------------------------------------
st.subheader("Filtered Compressor Records")

st.dataframe(
    filtered[RECORD_COLS],
    use_container_width=True,
    hide_index=True,
)

st.download_button(
    "Download filtered records (CSV)",
    data=filtered[RECORD_COLS].to_csv(
        index=False
    ).encode("utf-8-sig"),
    file_name="filtered_compressor_tda.csv",
    mime="text/csv",
)


# --------------------------------------------------
# DATA SOURCE — AT THE END OF THE DASHBOARD
# --------------------------------------------------
st.divider()
st.subheader("Data Source")

st.markdown(
    f"[Updated Data Logger]({DATA_SOURCE_URL})"
)
