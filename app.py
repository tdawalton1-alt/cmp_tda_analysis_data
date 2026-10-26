import os
import re
import unicodedata

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# ============================================================
# CONFIGURATION
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
    "Compressor type",
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

PREVIEW_COLUMNS = [
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
    "Effect 1",
    "Effect 2",
    "Effect 3",
    "Effect 4",
    "Final Findings 1",
    "Final Findings 2",
    "Final Findings 3",
    "Final Findings 4",
    "Other comments",
    "Measurement data",
]

REQUIRED_COLUMNS = (
    FILTER_COLUMNS
    + DATE_COLUMNS
    + EFFECT_COLUMNS
    + FINAL_COLUMNS
)


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
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    value = unicodedata.normalize("NFKC", str(value))

    for character in ("\u200b", "\u200c", "\u200d", "\ufeff"):
        value = value.replace(character, "")

    value = re.sub(r"\s+", " ", value).strip()

    if value.casefold() in {"nan", "none", "nat"}:
        return ""

    return value


def normalize_header(value):
    return normalize_text(value).casefold()


def find_column_mapping(df):
    lookup = {
        normalize_header(column): column
        for column in df.columns
    }

    mapping = {}

    for name in set(REQUIRED_COLUMNS + PREVIEW_COLUMNS):
        actual = lookup.get(normalize_header(name))

        if actual is not None:
            mapping[name] = actual

    return mapping


# ============================================================
# GOOGLE SHEETS DATA LOADING
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


def load_service_account_sheet():
    import gspread
    from google.oauth2.service_account import Credentials

    credentials_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

    if not credentials_path:
        raise RuntimeError(
            "Set GOOGLE_SERVICE_ACCOUNT_JSON to your service-account JSON path."
        )

    credentials = Credentials.from_service_account_file(
        credentials_path,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets.readonly"
        ],
    )

    client = gspread.authorize(credentials)

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

    rows = []

    for source_row in values[1:]:
        row = list(source_row[:len(headers)])
        row += [""] * (len(headers) - len(row))
        rows.append(row)

    return pd.DataFrame(rows, columns=headers)


@st.cache_data(ttl=300, show_spinner=False)
def load_data():
    if os.getenv("USE_SERVICE_ACCOUNT", "0") == "1":
        return load_service_account_sheet()

    return load_public_sheet()


# ============================================================
# DATE HANDLING
# ============================================================

def parse_date_series(series):
    values = series.map(normalize_text)

    parsed = pd.to_datetime(
        values,
        errors="coerce",
    )

    remaining = parsed.isna() & values.ne("")

    if remaining.any():
        parsed.loc[remaining] = pd.to_datetime(
            values.loc[remaining],
            errors="coerce",
            dayfirst=True,
        )

    return parsed


def render_date_filter(df, column, key):
    st.sidebar.markdown(f"**{column}**")

    valid_dates = df[column].dropna()

    if valid_dates.empty:
        mode = st.sidebar.radio(
            "Date filter",
            ["All dates", "Blank dates"],
            key=f"{key}_mode",
        )

        return mode, None, None

    minimum = valid_dates.min().date()
    maximum = valid_dates.max().date()

    mode = st.sidebar.radio(
        "Date filter",
        [
            "All dates",
            "Date range",
            "Blank dates",
            "Date range + blank dates",
        ],
        key=f"{key}_mode",
    )

    if mode in ("All dates", "Blank dates"):
        return mode, None, None

    selected_range = st.sidebar.date_input(
        "Select date range",
        value=(minimum, maximum),
        min_value=minimum,
        max_value=maximum,
        key=f"{key}_range",
    )

    if isinstance(selected_range, (tuple, list)):
        if len(selected_range) == 2:
            start_date, end_date = selected_range
        elif len(selected_range) == 1:
            start_date = end_date = selected_range[0]
        else:
            start_date, end_date = minimum, maximum
    else:
        start_date = end_date = selected_range

    return mode, start_date, end_date


def apply_date_filter(df, column, mode, start_date, end_date):
    if mode == "All dates":
        return df

    blank_mask = df[column].isna()

    if mode == "Blank dates":
        return df.loc[blank_mask].copy()

    valid_mask = (
        df[column].notna()
        & df[column].dt.date.between(start_date, end_date)
    )

    if mode == "Date range + blank dates":
        return df.loc[valid_mask | blank_mask].copy()

    return df.loc[valid_mask].copy()


# ============================================================
# CASCADING FILTERS
# ============================================================

def render_column_filter(df, column, key):
    if column not in df.columns:
        return df

    options = sorted({
        normalize_text(value)
        for value in df[column].tolist()
        if normalize_text(value)
    })

    selected = st.sidebar.multiselect(
        column,
        options=options,
        default=[],
        key=key,
        help="Options depend on the selections made in the filters above.",
    )

    if selected:
        mask = df[column].map(normalize_text).isin(selected)
        return df.loc[mask].copy()

    return df


def render_finding_filter(df, columns, label, key):
    options = set()

    for column in columns:
        options.update(
            value
            for value in df[column].map(normalize_text)
            if value
        )

    selected = st.sidebar.multiselect(
        label,
        options=sorted(options),
        default=[],
        key=key,
        help="Options depend on the selections made in the filters above.",
    )

    if not selected:
        return df

    mask = pd.Series(False, index=df.index)

    for column in columns:
        mask |= df[column].map(normalize_text).isin(selected)

    return df.loc[mask].copy()


# ============================================================
# FINDING COUNTS
# ============================================================

def build_finding_records(df, columns):
    records = []

    for _, row in df.iterrows():
        row_id = row["_row_id"]

        for source_column in columns:
            finding = normalize_text(row[source_column])

            if finding:
                records.append({
                    "_row_id": row_id,
                    "Finding": finding,
                    "Source Column": source_column,
                })

    return pd.DataFrame(
        records,
        columns=["_row_id", "Finding", "Source Column"],
    )


def count_finding_records(records, count_mode):
    if records.empty:
        return pd.DataFrame(columns=["Finding", "Count"])

    if count_mode == "Unique Compressor":
        result = (
            records.groupby("Finding")["_row_id"]
            .nunique()
            .reset_index(name="Count")
        )
    else:
        result = (
            records.groupby("Finding")
            .size()
            .reset_index(name="Count")
        )

    return result.sort_values(
        ["Count", "Finding"],
        ascending=[False, True],
        ignore_index=True,
    )


def add_percentages(df):
    result = df.copy()

    if result.empty:
        result["Percentage"] = pd.Series(dtype=float)
        result["Cumulative %"] = pd.Series(dtype=float)
        return result

    total = result["Count"].sum()

    result["Percentage"] = (
        result["Count"] / total * 100 if total else 0.0
    )

    result["Cumulative %"] = result["Percentage"].cumsum()

    return result


# ============================================================
# COMPRESSOR MODEL COUNT
# ============================================================

def create_model_counts(df):
    values = df["Compressor Model"].map(normalize_text)
    values = values[values != ""]

    result = (
        values.value_counts()
        .rename_axis("Compressor Model")
        .reset_index(name="Count")
    )

    result = result.sort_values(
        ["Count", "Compressor Model"],
        ascending=[False, True],
        ignore_index=True,
    )

    return add_percentages(result)


# ============================================================
# GRAPH FORMATTING
# ============================================================

def style_chart_axes(fig, x_title, y_title):
    """
    Apply bold black axis titles and black tick labels.
    """

    fig.update_xaxes(
        title=dict(
            text=x_title,
            font=dict(
                color="black",
                size=15,
                family="Arial Black, Arial, sans-serif",
            ),
        ),
        tickfont=dict(
            color="black",
            size=11,
            family="Arial, sans-serif",
        ),
        showline=True,
        linecolor="black",
        linewidth=1,
        mirror=False,
    )

    fig.update_yaxes(
        title=dict(
            text=y_title,
            font=dict(
                color="black",
                size=15,
                family="Arial Black, Arial, sans-serif",
            ),
        ),
        tickfont=dict(
            color="black",
            size=11,
            family="Arial, sans-serif",
        ),
        showline=True,
        linecolor="black",
        linewidth=1,
        rangemode="tozero",
    )

    fig.update_layout(
        font=dict(
            family="Arial, sans-serif",
            color="black",
            size=12,
        ),
        title_font=dict(
            family="Arial Black, Arial, sans-serif",
            color="black",
            size=17,
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )

    return fig


def create_pareto(df, category_column, title):
    if df.empty:
        return None

    chart_df = df.copy()
    total = chart_df["Count"].sum()

    chart_df["Cumulative Count"] = (
        chart_df["Cumulative %"] * total / 100
    )

    fig = go.Figure()

    # Count bars with black, bold labels outside bar ends.
    fig.add_trace(
        go.Bar(
            x=chart_df[category_column],
            y=chart_df["Count"],
            text=chart_df["Count"].astype(int).astype(str),
            textposition="outside",
            textfont=dict(
                color="black",
                size=12,
                family="Arial Black, Arial, sans-serif",
            ),
            cliponaxis=False,
            name="Count",
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Count: %{y}<extra></extra>"
            ),
        )
    )

    # Cumulative percentage line uses a true percentage axis.
    fig.add_trace(
        go.Scatter(
            x=chart_df[category_column],
            y=chart_df["Cumulative %"],
            mode="lines+markers",
            name="Cumulative %",
            yaxis="y2",
            line=dict(width=2),
            marker=dict(size=7),
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Cumulative: %{y:.2f}%<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        title=dict(
            text=title,
            font=dict(
                color="black",
                size=17,
                family="Arial Black, Arial, sans-serif",
            ),
        ),
        xaxis=dict(
            title="Finding",
            tickangle=-45,
            automargin=True,
        ),
        yaxis=dict(
            title="Count",
            rangemode="tozero",
            automargin=True,
        ),
        yaxis2=dict(
            title=dict(
                text="Cumulative %",
                font=dict(
                    color="black",
                    size=15,
                    family="Arial Black, Arial, sans-serif",
                ),
            ),
            overlaying="y",
            side="right",
            range=[0, 105],
            ticksuffix="%",
            tickmode="array",
            tickvals=[0, 20, 40, 60, 80, 100],
            tickfont=dict(
                color="black",
                size=11,
                family="Arial, sans-serif",
            ),
            showline=True,
            linecolor="black",
            linewidth=1,
        ),
        height=560,
        margin=dict(
            l=65,
            r=75,
            t=80,
            b=165,
        ),
        hovermode="x unified",
        bargap=0.25,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(color="black"),
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(
            family="Arial, sans-serif",
            color="black",
        ),
    )

    style_chart_axes(
        fig,
        "Finding",
        "Count",
    )

    # Reapply secondary-axis title styling after the common axis styling.
    fig.update_layout(
        yaxis2=dict(
            title=dict(
                text="Cumulative %",
                font=dict(
                    color="black",
                    size=15,
                    family="Arial Black, Arial, sans-serif",
                ),
            ),
            overlaying="y",
            side="right",
            range=[0, 105],
            ticksuffix="%",
            tickmode="array",
            tickvals=[0, 20, 40, 60, 80, 100],
            tickfont=dict(color="black", size=11),
        )
    )

    # Add headroom so outside bar labels are not clipped.
    maximum = chart_df["Count"].max()

    if maximum > 0:
        fig.update_yaxes(range=[0, maximum * 1.18])

    return fig


def create_model_chart(model_counts):
    if model_counts.empty:
        return None

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=model_counts["Compressor Model"],
            y=model_counts["Count"],
            text=model_counts["Count"].astype(int).astype(str),
            textposition="outside",
            textfont=dict(
                color="black",
                size=12,
                family="Arial Black, Arial, sans-serif",
            ),
            cliponaxis=False,
            name="Compressor Count",
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Compressor Count: %{y}<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        title=dict(
            text="Compressor Model Distribution",
            font=dict(
                color="black",
                size=17,
                family="Arial Black, Arial, sans-serif",
            ),
        ),
        height=520,
        margin=dict(
            l=65,
            r=30,
            t=70,
            b=140,
        ),
        showlegend=False,
        bargap=0.25,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(
            family="Arial, sans-serif",
            color="black",
        ),
    )

    style_chart_axes(
        fig,
        "Compressor Model",
        "Compressor Count",
    )

    maximum = model_counts["Count"].max()

    if maximum > 0:
        fig.update_yaxes(range=[0, maximum * 1.18])

    return fig


# ============================================================
# LOAD AND VALIDATE DATA
# ============================================================

st.title("📊 Compressor TDA — Effects & Final Findings Dashboard")
st.caption("Source: Google Sheets → Database")

if st.button("🔄 Refresh Google Sheet Data"):
    st.cache_data.clear()
    st.rerun()

try:
    source_df = load_data()
except Exception as error:
    st.error("Unable to load Google Sheet.")
    st.code(str(error))
    st.stop()

if source_df.empty:
    st.warning("The Database sheet contains no records.")
    st.stop()

column_mapping = find_column_mapping(source_df)

missing = [
    column
    for column in REQUIRED_COLUMNS
    if column not in column_mapping
]

if missing:
    st.error("Required columns not found in the Database sheet:")
    st.write(missing)
    st.write("Available columns:", list(source_df.columns))
    st.stop()

df = source_df.rename(
    columns={
        actual: logical
        for logical, actual in column_mapping.items()
    }
).copy()

# Create absent optional columns as blank values.
for column in PREVIEW_COLUMNS:
    if column not in df.columns:
        df[column] = ""

df["_row_id"] = range(len(df))


# ============================================================
# CLEAN DATA
# ============================================================

TEXT_COLUMNS = (
    FILTER_COLUMNS
    + EFFECT_COLUMNS
    + FINAL_COLUMNS
    + [
        "SI No",
        "SR No",
        "Compressor Barcode",
        "Compressor Lifetime",
        "Other comments",
        "Measurement data",
    ]
)

for column in TEXT_COLUMNS:
    if column in df.columns:
        df[column] = df[column].map(normalize_text)

for column in DATE_COLUMNS:
    df[column] = parse_date_series(df[column])

if "Compressor Market Return Date" in df.columns:
    df["Compressor Market Return Date"] = parse_date_series(
        df["Compressor Market Return Date"]
    )


# ============================================================
# CASCADING FILTERS
# ============================================================

st.sidebar.header("🔎 Filters")

working = df.copy()

working = render_column_filter(
    working,
    "Compressor Model",
    "filter_model",
)

working = render_column_filter(
    working,
    "Compressor type",
    "filter_compressor_type",
)

working = render_column_filter(
    working,
    "Compressor Condition",
    "filter_condition",
)

working = render_column_filter(
    working,
    "Field Findings",
    "filter_field_findings",
)

working = render_column_filter(
    working,
    "TDA Preliminary Findings",
    "filter_tda_preliminary",
)

st.sidebar.markdown("---")

inspection_mode, inspection_start, inspection_end = render_date_filter(
    working,
    "Inspection Date",
    "inspection_date",
)

working = apply_date_filter(
    working,
    "Inspection Date",
    inspection_mode,
    inspection_start,
    inspection_end,
)

production_mode, production_start, production_end = render_date_filter(
    working,
    "Compressor Production Date",
    "production_date",
)

working = apply_date_filter(
    working,
    "Compressor Production Date",
    production_mode,
    production_start,
    production_end,
)

working = render_finding_filter(
    working,
    EFFECT_COLUMNS,
    "Effect",
    "filter_effect",
)

working = render_finding_filter(
    working,
    FINAL_COLUMNS,
    "Final Finding",
    "filter_final_finding",
)

filtered = working.copy()


# ============================================================
# COUNTING METHOD
# ============================================================

st.sidebar.divider()

count_mode = st.sidebar.radio(
    "Counting Method",
    ["Occurrence", "Unique Compressor"],
    index=0,
    help=(
        "Occurrence counts every non-empty finding cell. "
        "Unique Compressor counts a finding once per source row."
    ),
)


# ============================================================
# FINDING COUNTS
# ============================================================

effect_records = build_finding_records(
    filtered,
    EFFECT_COLUMNS,
)

final_records = build_finding_records(
    filtered,
    FINAL_COLUMNS,
)

effect_counts = add_percentages(
    count_finding_records(effect_records, count_mode)
)

final_counts = add_percentages(
    count_finding_records(final_records, count_mode)
)


# ============================================================
# DISPLAY CONTROLS
# ============================================================

st.sidebar.divider()
st.sidebar.subheader("👁️ Display Controls")

selected_effects = st.sidebar.multiselect(
    "Effects to Show",
    options=effect_counts["Finding"].tolist(),
    default=effect_counts["Finding"].tolist(),
    key="display_effects",
)

selected_final_findings = st.sidebar.multiselect(
    "Final Findings to Show",
    options=final_counts["Finding"].tolist(),
    default=final_counts["Finding"].tolist(),
    key="display_final_findings",
)

effect_display = effect_counts.loc[
    effect_counts["Finding"].isin(selected_effects),
    ["Finding", "Count"],
].copy()

effect_display = add_percentages(
    effect_display.sort_values(
        "Count",
        ascending=False,
        ignore_index=True,
    )
)

final_display = final_counts.loc[
    final_counts["Finding"].isin(selected_final_findings),
    ["Finding", "Count"],
].copy()

final_display = add_percentages(
    final_display.sort_values(
        "Count",
        ascending=False,
        ignore_index=True,
    )
)


# ============================================================
# KPI CARDS
# ============================================================

k1, k2, k3, k4 = st.columns(4)

k1.metric("Filtered Compressors", f"{len(filtered):,}")
k2.metric("Effect Records", f"{len(effect_records):,}")
k3.metric("Final Finding Records", f"{len(final_records):,}")
k4.metric("Unique Effects", f"{effect_counts['Finding'].nunique():,}")


# ============================================================
# COMPRESSOR MODEL COUNT
# ============================================================

st.divider()
st.header("📦 Compressor Model Count")

model_counts = create_model_counts(filtered)

model_left, model_right = st.columns([1, 2])

with model_left:
    st.subheader("Model Count Table")

    if model_counts.empty:
        st.info("No Compressor Model data found.")
    else:
        model_table = model_counts.copy()

        model_table["Percentage"] = (
            model_table["Percentage"].round(2)
        )

        model_table["Cumulative %"] = (
            model_table["Cumulative %"].round(2)
        )

        st.dataframe(
            model_table,
            use_container_width=True,
            hide_index=True,
        )

with model_right:
    st.subheader("Model Distribution")

    if model_counts.empty:
        st.info("No Compressor Model data found.")
    else:
        fig = create_model_chart(model_counts)

        st.plotly_chart(
            fig,
            use_container_width=True,
        )


# ============================================================
# EFFECTS TABLE AND PARETO
# ============================================================

st.divider()
st.header("1. Effects")

left, right = st.columns([1, 2])

with left:
    st.subheader("Effects Count")

    if effect_display.empty:
        st.info("No Effects found for the current filters.")
    else:
        table = effect_display.rename(
            columns={"Finding": "Effect"}
        ).copy()

        table["Percentage"] = table["Percentage"].round(2)
        table["Cumulative %"] = table["Cumulative %"].round(2)

        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True,
        )

with right:
    st.subheader("Effects Pareto Chart")

    if effect_display.empty:
        st.info("No Effects found for the current filters.")
    else:
        fig = create_pareto(
            effect_display,
            "Finding",
            "Effects Pareto Chart",
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
        )


# ============================================================
# FINAL FINDINGS TABLE AND PARETO
# ============================================================

st.divider()
st.header("2. Final Findings")

left, right = st.columns([1, 2])

with left:
    st.subheader("Final Findings Count")

    if final_display.empty:
        st.info("No Final Findings found for the current filters.")
    else:
        table = final_display.rename(
            columns={"Finding": "Final Finding"}
        ).copy()

        table["Percentage"] = table["Percentage"].round(2)
        table["Cumulative %"] = table["Cumulative %"].round(2)

        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True,
        )

with right:
    st.subheader("Final Findings Pareto Chart")

    if final_display.empty:
        st.info("No Final Findings found for the current filters.")
    else:
        fig = create_pareto(
            final_display,
            "Finding",
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
    preview_columns = [
        column
        for column in PREVIEW_COLUMNS
        if column in filtered.columns
    ]

    preview = filtered[preview_columns].copy()

    st.dataframe(
        preview,
        use_container_width=True,
        hide_index=True,
        height=550,
    )


# ============================================================
# FINDING SOURCE AUDIT
# ============================================================

st.divider()

with st.expander("🔍 Finding Source Audit"):
    audit_rows = []

    for column in EFFECT_COLUMNS:
        values = filtered[column].map(normalize_text)

        audit_rows.append({
            "Type": "Effect",
            "Source Column": column,
            "Non-empty Cells": int((values != "").sum()),
            "Unique Values": int(values[values != ""].nunique()),
        })

    for column in FINAL_COLUMNS:
        values = filtered[column].map(normalize_text)

        audit_rows.append({
            "Type": "Final Finding",
            "Source Column": column,
            "Non-empty Cells": int((values != "").sum()),
            "Unique Values": int(values[values != ""].nunique()),
        })

    st.dataframe(
        pd.DataFrame(audit_rows),
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# FOOTER
# ============================================================

st.caption(
    f"Source records: {len(df):,} | "
    f"Filtered records: {len(filtered):,} | "
    "Data cache: 5 minutes"
)