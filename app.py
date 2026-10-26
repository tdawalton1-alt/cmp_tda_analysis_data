import os
import re
import unicodedata

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# ============================================================
# CONFIG
# ============================================================

SHEET_ID = "1-Tqv5bH51dCTFxa9UMvLTBGr7zM0v1LpSZEN9GwM5OU"
SHEET_GID = "243879173"
SHEET_NAME = "Database"

CSV_URL = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export"
    f"?format=csv&gid={SHEET_GID}"
)

FILTER_COLUMNS = [
    "Compressor Model",
    "Compressor Condition",
    "Field Findings",
    "TDA Preliminary Findings",
]

DATE_COLUMNS = [
    "Inspection Date",
    "Compressor Production Date",
]

EFFECT_COLUMNS = [
    "Effect 1",
    "Effect 2",
    "Effect 3",
    "Effect 4",
]

FINAL_COLUMNS = [
    "Final Findings 1",
    "Final Findings 2",
    "Final Findings 3",
    "Final Findings 4",
]

# Columns that should appear in filtered records
RECORD_ID_COLUMNS = [
    "SI No",
    "SR No",
    "Compressor Barcode",
]


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Compressor TDA Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 2rem;
    }

    div[data-testid="stMetric"] {
        border: 1px solid rgba(128,128,128,.25);
        border-radius: 12px;
        padding: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(value):
    """
    Normalize Google Sheets text.

    Handles:
    - blank values
    - NaN / None
    - non-breaking spaces
    - zero-width spaces
    - BOM
    - tabs/newlines
    - repeated spaces
    - Unicode normalization
    """

    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    text = str(value)

    text = unicodedata.normalize(
        "NFKC",
        text,
    )

    text = (
        text.replace("\u200b", "")
        .replace("\u200c", "")
        .replace("\u200d", "")
        .replace("\ufeff", "")
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================
# LOAD PUBLIC GOOGLE SHEET
# ============================================================

@st.cache_data(ttl=300, show_spinner=False)
def load_public_sheet():

    df = pd.read_csv(
        CSV_URL,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
    )

    df.columns = [
        normalize_text(column)
        for column in df.columns
    ]

    return df


# ============================================================
# LOAD PRIVATE GOOGLE SHEET
# ============================================================

def load_service_account_sheet():

    import gspread
    from google.oauth2.service_account import Credentials

    credentials_path = os.getenv(
        "GOOGLE_SERVICE_ACCOUNT_JSON"
    )

    if not credentials_path:
        raise RuntimeError(
            "GOOGLE_SERVICE_ACCOUNT_JSON is not configured."
        )

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly"
    ]

    credentials = Credentials.from_service_account_file(
        credentials_path,
        scopes=scopes,
    )

    client = gspread.authorize(
        credentials
    )

    worksheet = (
        client
        .open_by_key(SHEET_ID)
        .worksheet(SHEET_NAME)
    )

    values = worksheet.get_all_values()

    if not values:
        return pd.DataFrame()

    headers = [
        normalize_text(value)
        for value in values[0]
    ]

    rows = values[1:]

    fixed_rows = []

    for row in rows:

        row = list(row)

        if len(row) < len(headers):

            row += [
                ""
            ] * (
                len(headers) - len(row)
            )

        if len(row) > len(headers):

            row = row[
                :len(headers)
            ]

        fixed_rows.append(row)

    return pd.DataFrame(
        fixed_rows,
        columns=headers,
    )


# ============================================================
# LOAD DATA
# ============================================================

@st.cache_data(ttl=300, show_spinner=False)
def load_data():

    if os.getenv(
        "USE_SERVICE_ACCOUNT",
        "0",
    ) == "1":

        return load_service_account_sheet()

    return load_public_sheet()


# ============================================================
# COLUMN MATCHING
# ============================================================

def find_columns(
    df,
    required_columns,
):

    lookup = {}

    for column in df.columns:

        key = normalize_text(
            column
        ).lower()

        lookup[key] = column

    mapping = {}
    missing = []

    for requested in required_columns:

        key = requested.lower()

        if key in lookup:

            mapping[
                requested
            ] = lookup[key]

        else:

            missing.append(
                requested
            )

    return mapping, missing


# ============================================================
# DATE PARSING
# ============================================================

def parse_date_series(series):

    result = pd.to_datetime(
        series,
        errors="coerce",
    )

    remaining = result.isna()

    if remaining.any():

        retry = pd.to_datetime(
            series[remaining],
            errors="coerce",
            dayfirst=True,
        )

        result.loc[
            remaining
        ] = retry

    return result


# ============================================================
# DATE FILTER UI
# ============================================================

def date_filter(
    df,
    column,
):

    st.sidebar.markdown(
        f"**{column}**"
    )

    valid = df[
        column
    ].dropna()

    if valid.empty:

        mode = st.sidebar.radio(
            "Date filter",
            [
                "All dates",
                "Blank dates",
            ],
            key=f"{column}_mode",
        )

        return (
            mode,
            None,
            None,
        )

    min_date = (
        valid.min().date()
    )

    max_date = (
        valid.max().date()
    )

    mode = st.sidebar.radio(
        "Date filter",
        [
            "All dates",
            "Date range",
            "Blank dates",
            "Date range + blank dates",
        ],
        key=f"{column}_mode",
    )

    if mode == "All dates":

        return (
            mode,
            None,
            None,
        )

    if mode == "Blank dates":

        return (
            mode,
            None,
            None,
        )

    selected_range = st.sidebar.date_input(
        "Select date range",
        value=(
            min_date,
            max_date,
        ),
        min_value=min_date,
        max_value=max_date,
        key=f"{column}_range",
    )

    if isinstance(
        selected_range,
        (tuple, list),
    ):

        if len(selected_range) == 2:

            start_date = (
                selected_range[0]
            )

            end_date = (
                selected_range[1]
            )

        else:

            start_date = (
                selected_range[0]
            )

            end_date = (
                selected_range[0]
            )

    else:

        start_date = selected_range
        end_date = selected_range

    return (
        mode,
        start_date,
        end_date,
    )


# ============================================================
# APPLY DATE FILTER
# ============================================================

def apply_date_filter(
    df,
    column,
    mode,
    start_date,
    end_date,
):

    if mode == "All dates":

        return df

    blank_mask = (
        df[column].isna()
    )

    if mode == "Blank dates":

        return df[
            blank_mask
        ].copy()

    date_mask = (
        df[column].notna()
        &
        df[column].dt.date.between(
            start_date,
            end_date,
        )
    )

    if mode == "Date range + blank dates":

        return df[
            date_mask
            |
            blank_mask
        ].copy()

    return df[
        date_mask
    ].copy()


# ============================================================
# APPLY ALL FILTERS
# ============================================================

def apply_filters(df):

    filtered = df.copy()

    # --------------------------------------------------------
    # MULTISELECT FILTERS
    # --------------------------------------------------------

    for column in FILTER_COLUMNS:

        options = sorted(
            [
                value
                for value
                in (
                    filtered[column]
                    .drop_duplicates()
                    .tolist()
                )
                if value != ""
            ]
        )

        selected = st.sidebar.multiselect(
            column,
            options=options,
            default=[],
            key=f"filter_{column}",
        )

        if selected:

            filtered = filtered[
                filtered[column].isin(
                    selected
                )
            ].copy()

    # --------------------------------------------------------
    # INSPECTION DATE
    # --------------------------------------------------------

    mode, start, end = date_filter(
        filtered,
        "Inspection Date",
    )

    filtered = apply_date_filter(
        filtered,
        "Inspection Date",
        mode,
        start,
        end,
    )

    # --------------------------------------------------------
    # COMPRESSOR PRODUCTION DATE
    # --------------------------------------------------------

    mode, start, end = date_filter(
        filtered,
        "Compressor Production Date",
    )

    filtered = apply_date_filter(
        filtered,
        "Compressor Production Date",
        mode,
        start,
        end,
    )

    return filtered


# ============================================================
# BUILD FINDING RECORDS
# ============================================================

def build_finding_records(
    filtered,
    columns,
):

    records = []

    for _, row in filtered.iterrows():

        compressor_row_id = (
            row["_row_id"]
        )

        for source_column in columns:

            raw_value = row[
                source_column
            ]

            value = normalize_text(
                raw_value
            )

            if value == "":
                continue

            records.append(
                {
                    "_row_id":
                        compressor_row_id,

                    "Finding":
                        value,

                    "Source Column":
                        source_column,
                }
            )

    return pd.DataFrame(
        records,
        columns=[
            "_row_id",
            "Finding",
            "Source Column",
        ],
    )


# ============================================================
# COUNT FINDINGS
# ============================================================

def count_finding_records(
    finding_records,
    count_mode,
):

    if finding_records.empty:

        return pd.DataFrame(
            columns=[
                "Finding",
                "Count",
            ]
        )

    if count_mode == "Unique Compressor":

        counts = (
            finding_records
            .groupby(
                "Finding"
            )["_row_id"]
            .nunique()
            .reset_index(
                name="Count"
            )
        )

    else:

        counts = (
            finding_records
            .groupby(
                "Finding"
            )
            .size()
            .reset_index(
                name="Count"
            )
        )

    counts = counts.sort_values(
        [
            "Count",
            "Finding",
        ],
        ascending=[
            False,
            True,
        ],
        ignore_index=True,
    )

    return counts


# ============================================================
# MODEL COUNT TABLE
# ============================================================

def create_model_count_table(
    filtered,
):

    if filtered.empty:

        return pd.DataFrame(
            columns=[
                "Compressor Model",
                "Count",
                "Percentage",
                "Cumulative %",
            ]
        )

    model_data = (
        filtered[
            "Compressor Model"
        ]
        .map(normalize_text)
    )

    model_data = model_data[
        model_data != ""
    ]

    model_counts = (
        model_data
        .value_counts()
        .rename_axis(
            "Compressor Model"
        )
        .reset_index(
            name="Count"
        )
    )

    model_counts = model_counts.sort_values(
        [
            "Count",
            "Compressor Model",
        ],
        ascending=[
            False,
            True,
        ],
        ignore_index=True,
    )

    total = model_counts[
        "Count"
    ].sum()

    if total > 0:

        model_counts[
            "Percentage"
        ] = (
            model_counts[
                "Count"
            ]
            / total
            * 100
        )

    else:

        model_counts[
            "Percentage"
        ] = 0.0

    model_counts[
        "Cumulative %"
    ] = (
        model_counts[
            "Percentage"
        ].cumsum()
    )

    return model_counts


# ============================================================
# PERCENTAGE
# ============================================================

def add_percentages(df):

    result = df.copy()

    if result.empty:

        result[
            "Percentage"
        ] = pd.Series(
            dtype=float
        )

        result[
            "Cumulative %"
        ] = pd.Series(
            dtype=float
        )

        return result

    total = (
        result["Count"].sum()
    )

    if total == 0:

        result[
            "Percentage"
        ] = 0.0

    else:

        result[
            "Percentage"
        ] = (
            result["Count"]
            / total
            * 100
        )

    result[
        "Cumulative %"
    ] = (
        result["Percentage"]
        .cumsum()
    )

    return result


# ============================================================
# PARETO CHART
# ============================================================

def make_pareto(
    df,
    title,
):

    if df.empty:

        return None

    chart_df = df.copy()

    total = (
        chart_df["Count"].sum()
    )

    chart_df[
        "Cumulative Count"
    ] = (
        chart_df[
            "Cumulative %"
        ]
        * total
        / 100
    )

    fig = go.Figure()

    # Bars
    fig.add_trace(
        go.Bar(
            x=chart_df[
                "Finding"
            ],
            y=chart_df[
                "Count"
            ],
            text=chart_df[
                "Count"
            ],
            textposition="inside",
            name="Count",
        )
    )

    # Cumulative line
    fig.add_trace(
        go.Scatter(
            x=chart_df[
                "Finding"
            ],
            y=chart_df[
                "Cumulative Count"
            ],
            mode="lines+markers",
            name="Cumulative %",
            yaxis="y2",
        )
    )

    fig.update_layout(

        title=title,

        xaxis=dict(
            title="",
            tickangle=-45,
        ),

        yaxis=dict(
            title="Count",
        ),

        yaxis2=dict(
            title="Cumulative %",
            overlaying="y",
            side="right",
            range=[
                0,
                max(
                    total,
                    1,
                ),
            ],
            tickmode="array",
            tickvals=[
                total * 0.0,
                total * 0.2,
                total * 0.4,
                total * 0.6,
                total * 0.8,
                total * 1.0,
            ],
            ticktext=[
                "0%",
                "20%",
                "40%",
                "60%",
                "80%",
                "100%",
            ],
        ),

        height=520,

        margin=dict(
            l=30,
            r=50,
            t=70,
            b=140,
        ),

        hovermode="x unified",
    )

    return fig


# ============================================================
# MAIN HEADER
# ============================================================

st.title(
    "📊 Compressor TDA — Effects & Final Findings Dashboard"
)

st.caption(
    "Source: Google Sheets → Database"
)


# ============================================================
# REFRESH BUTTON
# ============================================================

if st.button(
    "🔄 Refresh Google Sheet Data"
):

    st.cache_data.clear()

    st.rerun()


# ============================================================
# LOAD DATA
# ============================================================

try:

    df = load_data()

except Exception as error:

    st.error(
        "Unable to load Google Sheet."
    )

    st.code(
        str(error)
    )

    st.stop()


# ============================================================
# REQUIRED COLUMN VALIDATION
# ============================================================

required_columns = (
    FILTER_COLUMNS
    + DATE_COLUMNS
    + EFFECT_COLUMNS
    + FINAL_COLUMNS
)

mapping, missing = find_columns(
    df,
    required_columns,
)

if missing:

    st.error(
        "Missing required columns:"
    )

    st.write(
        missing
    )

    st.write(
        "Columns found in Google Sheet:"
    )

    st.write(
        list(df.columns)
    )

    st.stop()


# ============================================================
# OPTIONAL COLUMN DETECTION
# ============================================================

optional_mapping, _ = find_columns(
    df,
    RECORD_ID_COLUMNS,
)


# ============================================================
# RENAME REQUIRED COLUMNS
# ============================================================

rename_required = {
    actual: requested
    for requested, actual
    in mapping.items()
}

df = df.rename(
    columns=rename_required
).copy()


# ============================================================
# RENAME OPTIONAL COLUMNS
# ============================================================

rename_optional = {
    actual: requested
    for requested, actual
    in optional_mapping.items()
    if actual != requested
}

if rename_optional:

    df = df.rename(
        columns=rename_optional
    )


# ============================================================
# ROW ID
# ============================================================

df["_row_id"] = range(
    len(df)
)


# ============================================================
# CLEAN TEXT COLUMNS
# ============================================================

for column in (
    FILTER_COLUMNS
    +
    EFFECT_COLUMNS
    +
    FINAL_COLUMNS
):

    df[column] = (
        df[column]
        .map(normalize_text)
    )


# ============================================================
# CLEAN OPTIONAL RECORD COLUMNS
# ============================================================

for column in RECORD_ID_COLUMNS:

    if column in df.columns:

        df[column] = (
            df[column]
            .map(normalize_text)
        )


# ============================================================
# PARSE DATES
# ============================================================

for column in DATE_COLUMNS:

    df[column] = parse_date_series(
        df[column]
    )


# ============================================================
# SIDEBAR FILTERS
# ============================================================

st.sidebar.header(
    "🔎 Filters"
)

filtered = apply_filters(
    df
)


# ============================================================
# COUNT MODE
# ============================================================

st.sidebar.divider()

count_mode = st.sidebar.radio(
    "Counting Method",
    [
        "Occurrence",
        "Unique Compressor",
    ],
    index=0,
)


# ============================================================
# BUILD FINDING RECORDS
# ============================================================

effect_records = (
    build_finding_records(
        filtered,
        EFFECT_COLUMNS,
    )
)

final_records = (
    build_finding_records(
        filtered,
        FINAL_COLUMNS,
    )
)


# ============================================================
# FINDING COUNTS
# ============================================================

effect_counts = count_finding_records(
    effect_records,
    count_mode,
)

final_counts = count_finding_records(
    final_records,
    count_mode,
)

effect_counts = add_percentages(
    effect_counts
)

final_counts = add_percentages(
    final_counts
)


# ============================================================
# DISPLAY CONTROLS
# ============================================================

st.sidebar.divider()

st.sidebar.subheader(
    "👁️ Display Controls"
)


selected_effects = (
    st.sidebar.multiselect(
        "Effects to Show",
        options=effect_counts[
            "Finding"
        ].tolist(),
        default=effect_counts[
            "Finding"
        ].tolist(),
    )
)


selected_final = (
    st.sidebar.multiselect(
        "Final Findings to Show",
        options=final_counts[
            "Finding"
        ].tolist(),
        default=final_counts[
            "Finding"
        ].tolist(),
    )
)


# ============================================================
# DISPLAY DATA
# ============================================================

effect_display = (
    effect_counts[
        effect_counts[
            "Finding"
        ].isin(
            selected_effects
        )
    ]
    .copy()
    .sort_values(
        "Count",
        ascending=False,
        ignore_index=True,
    )
)


final_display = (
    final_counts[
        final_counts[
            "Finding"
        ].isin(
            selected_final
        )
    ]
    .copy()
    .sort_values(
        "Count",
        ascending=False,
        ignore_index=True,
    )
)


# Recalculate percentages after
# hiding selected findings.

effect_display = add_percentages(
    effect_display[
        [
            "Finding",
            "Count",
        ]
    ]
)

final_display = add_percentages(
    final_display[
        [
            "Finding",
            "Count",
        ]
    ]
)


# ============================================================
# MODEL COUNT
# ============================================================

model_counts = (
    create_model_count_table(
        filtered
    )
)


# ============================================================
# KPI
# ============================================================

c1, c2, c3, c4 = (
    st.columns(4)
)

c1.metric(
    "Filtered Compressors",
    f"{len(filtered):,}",
)

c2.metric(
    "Effect Records",
    f"{len(effect_records):,}",
)

c3.metric(
    "Final Finding Records",
    f"{len(final_records):,}",
)

c4.metric(
    "Unique Effects",
    f"{effect_counts['Finding'].nunique():,}",
)


# ============================================================
# COMPRESSOR MODEL COUNT
# ============================================================

st.divider()

st.header(
    "📦 Compressor Model Count"
)

model_col1, model_col2 = st.columns(
    [1, 2]
)


with model_col1:

    st.subheader(
        "Model Count Table"
    )

    if model_counts.empty:

        st.info(
            "No Compressor Model data found."
        )

    else:

        model_table = model_counts[
            [
                "Compressor Model",
                "Count",
                "Percentage",
                "Cumulative %",
            ]
        ].copy()

        model_table[
            "Percentage"
        ] = (
            model_table[
                "Percentage"
            ].round(2)
        )

        model_table[
            "Cumulative %"
        ] = (
            model_table[
                "Cumulative %"
            ].round(2)
        )

        st.dataframe(
            model_table,
            use_container_width=True,
            hide_index=True,
        )


with model_col2:

    st.subheader(
        "Model Distribution"
    )

    if model_counts.empty:

        st.info(
            "No Compressor Model data found."
        )

    else:

        model_chart = go.Figure()

        model_chart.add_trace(
            go.Bar(
                x=model_counts[
                    "Compressor Model"
                ],
                y=model_counts[
                    "Count"
                ],
                text=model_counts[
                    "Count"
                ],
                textposition="inside",
                name="Count",
            )
        )

        model_chart.update_layout(
            xaxis=dict(
                title="",
                tickangle=-45,
            ),
            yaxis=dict(
                title="Compressor Count",
            ),
            height=500,
            margin=dict(
                l=30,
                r=30,
                t=30,
                b=130,
            ),
            showlegend=False,
        )

        st.plotly_chart(
            model_chart,
            use_container_width=True,
        )


# ============================================================
# EFFECTS
# ============================================================

st.divider()

st.header(
    "1. Effects"
)

left, right = st.columns(
    [1, 2]
)


with left:

    st.subheader(
        "Effects Count"
    )

    if effect_display.empty:

        st.info(
            "No Effects found."
        )

    else:

        table = effect_display[
            [
                "Finding",
                "Count",
                "Percentage",
                "Cumulative %",
            ]
        ].copy()

        table.columns = [
            "Effect",
            "Count",
            "Percentage",
            "Cumulative %",
        ]

        table[
            "Percentage"
        ] = (
            table[
                "Percentage"
            ].round(2)
        )

        table[
            "Cumulative %"
        ] = (
            table[
                "Cumulative %"
            ].round(2)
        )

        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True,
        )


with right:

    st.subheader(
        "Effects Pareto Chart"
    )

    if effect_display.empty:

        st.info(
            "No Effects found."
        )

    else:

        fig = make_pareto(
            effect_display,
            "Effects Pareto Chart",
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
        )


# ============================================================
# FINAL FINDINGS
# ============================================================

st.divider()

st.header(
    "2. Final Findings"
)

left, right = st.columns(
    [1, 2]
)


with left:

    st.subheader(
        "Final Findings Count"
    )

    if final_display.empty:

        st.info(
            "No Final Findings found."
        )

    else:

        table = final_display[
            [
                "Finding",
                "Count",
                "Percentage",
                "Cumulative %",
            ]
        ].copy()

        table.columns = [
            "Final Finding",
            "Count",
            "Percentage",
            "Cumulative %",
        ]

        table[
            "Percentage"
        ] = (
            table[
                "Percentage"
            ].round(2)
        )

        table[
            "Cumulative %"
        ] = (
            table[
                "Cumulative %"
            ].round(2)
        )

        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True,
        )


with right:

    st.subheader(
        "Final Findings Pareto Chart"
    )

    if final_display.empty:

        st.info(
            "No Final Findings found."
        )

    else:

        fig = make_pareto(
            final_display,
            "Final Findings Pareto Chart",
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
        )


# ============================================================
# FILTERED COMPRESSOR RECORDS
# ============================================================

st.divider()

with st.expander(
    "📋 View Filtered Compressor Records",
    expanded=False,
):

    # --------------------------------------------------------
    # FIRST: SI NO, SR NO, COMPRESSOR BARCODE
    # --------------------------------------------------------

    preview_columns = []

    if "SI No" in filtered.columns:

        preview_columns.append(
            "SI No"
        )

    if "SR No" in filtered.columns:

        preview_columns.append(
            "SR No"
        )

    if "Compressor Barcode" in filtered.columns:

        preview_columns.append(
            "Compressor Barcode"
        )

    # --------------------------------------------------------
    # BASIC COMPRESSOR INFORMATION
    # --------------------------------------------------------

    preview_columns += [
        "Compressor Model",
        "Compressor Condition",
        "Inspection Date",
        "Compressor Production Date",
        "Field Findings",
        "TDA Preliminary Findings",
    ]

    # --------------------------------------------------------
    # EFFECTS
    # --------------------------------------------------------

    preview_columns += (
        EFFECT_COLUMNS
    )

    # --------------------------------------------------------
    # FINAL FINDINGS
    # --------------------------------------------------------

    preview_columns += (
        FINAL_COLUMNS
    )

    # Keep only columns that exist.
    preview_columns = [
        column
        for column in preview_columns
        if column in filtered.columns
    ]

    preview = filtered[
        preview_columns
    ].copy()

    st.dataframe(
        preview,
        use_container_width=True,
        hide_index=True,
        height=500,
    )


# ============================================================
# FINDING SOURCE AUDIT
# ============================================================

st.divider()

with st.expander(
    "🔍 Finding Source Audit"
):

    st.caption(
        "This section verifies how many non-empty values "
        "are being read from each Effect and Final Finding column."
    )

    audit_rows = []

    for column in EFFECT_COLUMNS:

        values = (
            filtered[column]
            .map(normalize_text)
        )

        audit_rows.append(
            {
                "Type": "Effect",
                "Source Column": column,
                "Non-empty Cells": int(
                    (
                        values != ""
                    ).sum()
                ),
                "Unique Values": int(
                    values[
                        values != ""
                    ].nunique()
                ),
            }
        )

    for column in FINAL_COLUMNS:

        values = (
            filtered[column]
            .map(normalize_text)
        )

        audit_rows.append(
            {
                "Type": "Final Finding",
                "Source Column": column,
                "Non-empty Cells": int(
                    (
                        values != ""
                    ).sum()
                ),
                "Unique Values": int(
                    values[
                        values != ""
                    ].nunique()
                ),
            }
        )

    st.dataframe(
        pd.DataFrame(
            audit_rows
        ),
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# FOOTER
# ============================================================

st.caption(
    f"Source records: {len(df):,} | "
    f"Filtered records: {len(filtered):,} | "
    f"Cache: 5 minutes"
)